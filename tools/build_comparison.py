#!/usr/bin/env python3
"""Build a deck-upgrade comparison page from a spec JSON file.

Usage:
    python3 tools/build_comparison.py comparisons/<name>.json [--refresh] [--max-age-days 7]
    python3 tools/build_comparison.py --refresh        # only (re)download the Scryfall data

Reads the spec, loads the deck list it points at, looks up every card in a
local index built from Scryfall's `default_cards` bulk file (images, mana
value, type, cheapest paper price in USD and EUR), computes the mana curve
for the stock deck and each upgrade direction, and writes
comparisons/<name>.html next to the spec.

Only the standard library is used. The bulk file (~80 MB gzipped) is
streamed once and reduced to .cache/card-index.json; it is re-downloaded
when the index is older than --max-age-days, or with --refresh. Prices are
therefore up to a week old, which is fine for deck planning.
"""

import argparse
import gzip
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "tools" / "comparison_template.html"
INDEX_FILE = ROOT / ".cache" / "card-index.json"
BULK_META = "https://api.scryfall.com/bulk-data/default_cards"
HEADERS = {"User-Agent": "mtg-deck-building/0.1", "Accept": "application/json"}
CURVE_BUCKETS = ["0", "1", "2", "3", "4", "5", "6", "7+"]
SKIP_LAYOUTS = {"token", "double_faced_token", "art_series", "emblem", "vanguard", "scheme", "planar"}
GOOD_SET_TYPES = {"core", "expansion", "commander", "masters", "draft_innovation", "starter"}


def key(name):
    return name.strip().lower()


# ---------------------------------------------------------------- card index

def image_score(card):
    """Prefer a normal, recent, high-res printing for the picture."""
    return (card.get("set_type") in GOOD_SET_TYPES, not card.get("promo", False),
            card.get("highres_image", False), card.get("released_at", ""))


def build_index():
    """Stream Scryfall's default_cards bulk file into a compact name -> card index."""
    with urllib.request.urlopen(urllib.request.Request(BULK_META, headers=HEADERS), timeout=30) as r:
        meta = json.load(r)
    url = meta.get("jsonl_download_uri") or meta["download_uri"]
    print(f"downloading Scryfall bulk data ({meta.get('updated_at', '?')}) …", file=sys.stderr)
    index, best = {}, {}
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=300) as r:
        stream = gzip.GzipFile(fileobj=r) if url.endswith(".gz") else r
        for raw in stream:
            line = raw.strip().rstrip(b",")
            if not line.startswith(b"{"):
                continue
            card = json.loads(line)
            if card.get("layout") in SKIP_LAYOUTS or card.get("lang", "en") != "en":
                continue
            k = key(card["name"])
            entry = index.get(k)
            if entry is None:
                faces = card.get("card_faces") or []
                entry = index[k] = {
                    "name": card["name"],
                    "cmc": card.get("cmc", 0),
                    "type_line": card.get("type_line") or (faces[0].get("type_line", "") if faces else ""),
                    "mana_cost": card.get("mana_cost") or (faces[0].get("mana_cost", "") if faces else ""),
                    "game_changer": card.get("game_changer", False),
                    "usd": None, "eur": None, "usd_set": None, "eur_set": None,
                }
            # Picture and Scryfall link from the best-looking printing
            score = image_score(card)
            if k not in best or score > best[k]:
                faces = card.get("card_faces") or []
                imgs = [card["image_uris"]] if "image_uris" in card else \
                    [f["image_uris"] for f in faces if "image_uris" in f]
                if imgs:
                    best[k] = score
                    entry["images"] = [{"normal": i.get("normal"), "large": i.get("large"), "art_crop": i.get("art_crop")} for i in imgs]
                    entry["scryfall_uri"] = card.get("scryfall_uri", "").split("?")[0]
            # Cheapest paper price in each currency, across all printings and finishes
            if "paper" in card.get("games", []):
                p = card.get("prices") or {}
                for cur, fields in (("usd", ("usd", "usd_foil", "usd_etched")), ("eur", ("eur", "eur_foil"))):
                    vals = [float(p[f]) for f in fields if p.get(f)]
                    if vals and (entry[cur] is None or min(vals) < entry[cur]):
                        entry[cur] = min(vals)
                        entry[cur + "_set"] = card.get("set_name")
    # Face-name aliases ("Find" -> "Find // Finality")
    for k, entry in list(index.items()):
        if " // " in entry["name"]:
            for face in entry["name"].split(" // "):
                index.setdefault(key(face), entry)
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(json.dumps({"bulk_updated": meta.get("updated_at"), "cards": index}))
    print(f"indexed {len(index)} cards -> {INDEX_FILE.relative_to(ROOT)}", file=sys.stderr)


def load_index(refresh, max_age_days):
    stale = not INDEX_FILE.exists() or time.time() - INDEX_FILE.stat().st_mtime > max_age_days * 86400
    if refresh or stale:
        build_index()
    return json.loads(INDEX_FILE.read_text())


# ---------------------------------------------------------------- deck

def parse_deck(path):
    """Return (commander_names, [(qty, name)]) from a decks/*.md file."""
    commanders, cards = [], []
    section = None
    for line in Path(path).read_text().splitlines():
        if line.startswith("## "):
            section = line[3:].split("(")[0].strip().lower()
            continue
        m = re.match(r"^(\d+)\s+(.+?)\s*$", line)
        if not m or section in (None, "changelog"):
            continue
        qty, name = int(m.group(1)), m.group(2)
        if section == "commander":
            commanders.append(name)
        else:
            cards.append((qty, name))
    return commanders, cards


def curve(cards, cards_by_name):
    """Mana curve of nonland cards plus average mana value."""
    buckets = dict.fromkeys(CURVE_BUCKETS, 0)
    total = count = 0
    for qty, name in cards:
        info = cards_by_name.get(key(name))
        if not info or "Land" in info["type_line"].split("//")[0]:
            continue
        cmc = int(info["cmc"])
        buckets["7+" if cmc >= 7 else str(cmc)] += qty
        total += cmc * qty
        count += qty
    return {"buckets": buckets, "average": round(total / count, 2) if count else 0,
            "nonland": count}


def apply_swaps(cards, swaps):
    result = {key(n): [q, n] for q, n in cards}
    problems = []
    for s in swaps:
        out_k = key(s["out"])
        if out_k not in result:
            problems.append(f"'{s['out']}' is not in the deck")
        else:
            result[out_k][0] -= 1
            if result[out_k][0] <= 0:
                del result[out_k]
        if key(s["in"]) in result:
            problems.append(f"'{s['in']}' is already in the deck")
        result.setdefault(key(s["in"]), [0, s["in"]])[0] += 1
    return [(q, n) for q, n in result.values()], problems


# ---------------------------------------------------------------- build

def total(names, cards, cur):
    return round(sum((cards.get(key(n)) or {}).get(cur) or 0 for n in names), 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", nargs="?", help="comparison spec JSON (omit with --refresh to only update Scryfall data)")
    ap.add_argument("--refresh", action="store_true", help="re-download Scryfall bulk data now")
    ap.add_argument("--max-age-days", type=float, default=7, help="re-download bulk data older than this")
    ap.add_argument("-o", "--output", help="output HTML (default: spec path with .html)")
    ap.add_argument("--after", metavar="DIRECTION_ID",
                    help="print the deck list after that direction's swaps (core included) instead of building; "
                         "paste it into mcp__mtg-search__get_deck for a legality check")
    args = ap.parse_args()
    if not args.spec:
        if not args.refresh:
            ap.error("give a spec file, or --refresh to only download Scryfall data")
        build_index()
        return

    spec_path = Path(args.spec)
    spec = json.loads(spec_path.read_text())
    commanders, stock = parse_deck(ROOT / spec["deck"])

    if args.after:
        d = next((x for x in spec["directions"] if x["id"] == args.after), None)
        if d is None:
            sys.exit(f"no direction '{args.after}' (have: {', '.join(x['id'] for x in spec['directions'])})")
        deck_after, probs = apply_swaps(stock, (spec.get("core") or {"swaps": []})["swaps"] + d["swaps"])
        for p in probs:
            print(f"warning: {p}", file=sys.stderr)
        print("Commander\n" + "".join(f"1 {c}\n" for c in commanders) + "\nDeck\n"
              + "".join(f"{q} {n}\n" for q, n in sorted(deck_after, key=lambda x: x[1])), end="")
        return

    core = spec.get("core") or {"swaps": []}
    swap_names = [n for s in core["swaps"] for n in (s["in"], s["out"])]
    for d in spec["directions"]:
        swap_names += [n for s in d["swaps"] for n in (s["in"], s["out"])]

    index = load_index(args.refresh, args.max_age_days)
    cards = index["cards"]
    problems = [f"card not found on Scryfall: {n}" for n in
                dict.fromkeys(commanders + [n for _, n in stock] + swap_names) if key(n) not in cards]

    directions = []
    for d in spec["directions"]:
        all_swaps = core["swaps"] + d["swaps"]
        deck_after, probs = apply_swaps(stock, all_swaps)
        problems += [f"{d['name']}: {p}" for p in probs]
        ins = [s["in"] for s in all_swaps]
        outs = [s["out"] for s in all_swaps]
        directions.append({
            **d,
            "curve": curve(deck_after, cards),
            "cost_usd": total(ins, cards, "usd"), "cost_eur": total(ins, cards, "eur"),
            "out_value_usd": total(outs, cards, "usd"), "out_value_eur": total(outs, cards, "eur"),
            "game_changers": [n for n in ins if (cards.get(key(n)) or {}).get("game_changer")],
        })
    if core["swaps"]:
        core_ins = [s["in"] for s in core["swaps"]]
        core = {**core, "cost_usd": total(core_ins, cards, "usd"), "cost_eur": total(core_ins, cards, "eur")}

    for cur, sym in (("usd", "$"), ("eur", "€")):
        budget = spec.get(f"budget_{cur}")
        if budget is not None:
            problems += [f"{d['name']}: cards in cost {sym}{d['cost_' + cur]:.2f}, over the {sym}{budget} budget"
                         for d in directions if d["cost_" + cur] > budget]

    for p in dict.fromkeys(problems):
        print(f"warning: {p}", file=sys.stderr)

    used = set(map(key, swap_names + commanders))
    page_cards = {k: v for k, v in cards.items() if k in used}
    payload = {
        **spec,
        "core": core,
        "directions": directions,
        "commanders": commanders,
        "stock_curve": curve(stock, cards),
        "cards": page_cards,
        "prices": {k: {f: v.get(f) for f in ("usd", "eur", "usd_set", "eur_set")} for k, v in page_cards.items()},
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "prices_as_of": (index.get("bulk_updated") or "")[:10],
        "curve_buckets": CURVE_BUCKETS,
    }
    html = TEMPLATE.read_text().replace(
        "__COMPARISON_DATA__", json.dumps(payload).replace("</", "<\\/"))
    out = Path(args.output) if args.output else spec_path.with_suffix(".html")
    out.write_text(html)
    print(f"wrote {out}")
    for d in directions:
        gc = f" · Game Changers in: {', '.join(d['game_changers'])}" if d["game_changers"] else ""
        print(f"  {d['name']}: avg MV {d['curve']['average']} · "
              f"cards in ${d['cost_usd']:.2f} / €{d['cost_eur']:.2f}{gc}")


if __name__ == "__main__":
    main()
