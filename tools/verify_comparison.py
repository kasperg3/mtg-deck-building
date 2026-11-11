#!/usr/bin/env python3
"""Mechanically verify a comparison spec: does every direction still make a legal 100?

Usage:
    python3 tools/verify_comparison.py comparisons/<deck>-upgrades.json [--offline]

Checks, per direction, with the core package applied first:
  * every cut is in the deck, every addition is not, no duplicates, nothing both ways
  * the post-swap list is exactly 100 cards
  * colour identity and Commander legality of every added card
  * Game Changers (from the cached index, no network) in each direction
  * budget_eur against the cards coming in
  * recomputes the metrics that can be derived from rules text and flags drift:
    Lands, Different land names, Extra land drops, Landfall payoffs
  * win conditions: a direction may not end with fewer than stock (the hand-counted
    "Win conditions" metric) unless it sets "win_conditions_note" saying why;
    warns when the spec doesn't count them at all

Rules text comes from one Scryfall /cards/collection call (<=75 names) and is
cached in .cache/oracle.json, so repeat runs are offline. --offline uses only
that cache and skips whatever it is missing.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from build_comparison import key, parse_deck  # noqa: E402

CACHE = ROOT / ".cache" / "oracle.json"
UA = {"User-Agent": "mtg-deck-building/1.0", "Accept": "application/json",
      "Content-Type": "application/json"}

# Hand-counted finishers; a direction may not end below the stock count.
WIN_KEY = "Win conditions"

# Metrics derived from rules text: key -> predicate over the lowercased text.
TEXT_METRICS = {
    "Extra land drops": lambda t: "additional land" in t,
    "Landfall payoffs": lambda t: "landfall" in t
    or re.search(r"whenever a land (you control )?enters", t) is not None,
}


def load_oracle(names, offline=False):
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    todo = sorted({n for n in names if key(n) not in cache})
    if todo and not offline:
        for i in range(0, len(todo), 75):
            batch = todo[i:i + 75]
            body = json.dumps({"identifiers": [{"name": n} for n in batch]}).encode()
            try:
                r = json.load(urllib.request.urlopen(
                    urllib.request.Request("https://api.scryfall.com/cards/collection",
                                           data=body, headers=UA), timeout=90))
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
                print(f"warning: scryfall unavailable ({e}); using cache only", file=sys.stderr)
                break
            for c in r["data"]:
                cache[key(c["name"])] = {
                    "name": c["name"], "cmc": c["cmc"], "type_line": c["type_line"],
                    "oracle_text": c.get("oracle_text") or "",
                    "color_identity": c.get("color_identity") or [],
                    "commander": c["legalities"].get("commander"),
                }
            CACHE.parent.mkdir(exist_ok=True)
            CACHE.write_text(json.dumps(cache))
    return cache


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("--offline", action="store_true", help="cache only, no Scryfall call")
    args = ap.parse_args()

    spec_path = Path(args.spec)
    spec = json.loads(spec_path.read_text())
    deck_path = ROOT / spec["deck"]
    commanders, cards = parse_deck(deck_path)

    core = (spec.get("core") or {}).get("swaps") or []
    swaps = core + [s for d in spec["directions"] for s in d["swaps"]]
    oracle = load_oracle([s["in"] for s in swaps] + [s["out"] for s in swaps]
                         + commanders + [n for _, n in cards], offline=args.offline)
    index = json.loads((ROOT / ".cache" / "card-index.json").read_text())["cards"]

    def info(n):
        return oracle.get(key(n)) or {}

    allowed = set().union(*(set(info(c).get("color_identity") or []) for c in commanders)) \
        if commanders else set("WUBRG")

    def is_land(n):
        # "Land", "Basic Land — Forest" and "Land Creature" all count.
        return re.search(r"\bland\b", info(n).get("type_line", "").lower()) is not None

    fails, warns = [], []

    # --- swap integrity ----------------------------------------------------
    deck_names = {n for _, n in cards} | set(commanders)
    for s in swaps:
        if not info(s["in"]):
            fails.append(f"cannot read rules text for '{s['in']}'")
        if s["out"] not in deck_names:
            fails.append(f"cut card not in {spec['deck']}: {s['out']}")
        if s["in"] in deck_names:
            fails.append(f"card already in the deck: {s['in']}")
        card = info(s["in"])
        if card:
            ident = set(card["color_identity"]) - allowed
            if ident:
                fails.append(f"{s['in']} is outside the deck's colour identity ({''.join(card['color_identity'])})")
            if card["commander"] not in ("legal", "not_legal"):
                fails.append(f"{s['in']} is '{card['commander']}' in Commander")

    # --- apply each direction ---------------------------------------------
    def metrics_of(pool):
        lands = [(q, n) for q, n in pool if is_land(n)]
        spells = [(q, n) for q, n in pool if not is_land(n)]
        out = {"Lands": sum(q for q, _ in lands),
               "Different land names": len({n for _, n in lands}),
               "Cards": sum(q for q, _ in pool) + len(commanders)}
        for label, pred in TEXT_METRICS.items():
            out[label] = sum(1 for _, n in spells + [(1, c) for c in commanders]
                             if pred((info(n).get("oracle_text") or "").lower()))
        out["Game Changers"] = sum(q for q, n in pool if (index.get(key(n)) or {}).get("game_changer"))
        gc = sorted({n for q, n in pool if (index.get(key(n)) or {}).get("game_changer")})
        return out, gc

    base, base_gc = metrics_of(list(cards))
    sm = (spec.get("analysis") or {}).get("stock_metrics") or {}
    print(f"stock: {base['Cards']} cards · "
          f"{base['Lands']} lands · {base['Different land names']} names · "
          f"{base['Extra land drops']} extra drops · {base['Landfall payoffs']} landfall payoffs · "
          f"{len(base_gc)} Game Changers")
    for k in ("Lands", "Different land names", *TEXT_METRICS, "Game Changers"):
        if k in sm and sm[k] != base[k]:
            fails.append(f"stock_metrics['{k}'] = {sm[k]}, rules text says {base[k]}")
    stock_wins = sm.get(WIN_KEY)
    if stock_wins is None:
        warns.append(f"stock_metrics has no '{WIN_KEY}': count the finishers (see the skill)")

    print()
    for d in spec["directions"]:
        pool = list(cards)
        applied = 0
        for s in core + d["swaps"]:
            for i, (q, n) in enumerate(pool):
                if n == s["out"]:
                    pool[i] = (q, s["in"])
                    applied += 1
                    break
            else:
                fails.append(f"{d['name']}: cannot apply {s['out']} -> {s['in']} (already swapped?)")
        m, gc = metrics_of(pool)
        cost_eur = sum((index.get(key(s["in"])) or {}).get("eur") or 0
                       for s in core + d["swaps"])
        budget = spec.get("budget_eur")
        flag = ""
        if budget and cost_eur > budget:
            flag = "  OVER BUDGET"
            fails.append(f"{d['name']}: €{cost_eur:.2f} over budget €{budget}")
        print(f"{d['name']:<22} {m['Cards']:>3} cards · {applied} swaps · "
              f"{m['Lands']} lands · {m['Different land names']} names · "
              f"{m['Extra land drops']} drops · {m['Landfall payoffs']} payoffs · "
              f"€{cost_eur:.2f}{flag}")
        if m["Cards"] != 100:
            fails.append(f"{d['name']}: {m['Cards']} cards")
        for k, v in d.get("metrics", {}).items():
            if k in m and m[k] != v:
                fails.append(f"{d['name']}: metric '{k}' = {v}, rules text says {m[k]}")
        if gc:
            warns.append(f"{d['name']} adds Game Changers: {', '.join(sorted(set(gc)))}")
        wins = d.get("metrics", {}).get(WIN_KEY)
        if stock_wins is not None:
            if wins is None:
                fails.append(f"{d['name']}: no '{WIN_KEY}' metric")
            elif wins < stock_wins and not d.get("win_conditions_note"):
                fails.append(f"{d['name']}: {WIN_KEY} drop from {stock_wins} to {wins}; "
                             "add a finisher back, cut a different card, or explain it "
                             "in \"win_conditions_note\"")
            elif wins < stock_wins:
                warns.append(f"{d['name']}: {WIN_KEY} {stock_wins} -> {wins} (explained in win_conditions_note)")

    print()
    print(f"=== {len(fails)} problem(s) ===")
    for f in fails:
        print("  !", f)
    for w in warns:
        print("  ~", w)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
