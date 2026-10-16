#!/usr/bin/env python3
"""Fill inventory.csv's Deck column from the deck files.

Usage:
    python3 tools/sync_inventory.py

For every deck in decks/*.md, assigns the copies it needs to inventory rows,
preferring rows bought for that deck (Notes "for <Deck>"), then rows from
that deck's precon, then any other free copy. Rows are split when only part
of a stack is in a deck (e.g. 8 of 10 Forests). Copies not in any deck get
Deck = "Loose". Warns about cards a deck needs that the inventory lacks.
"""

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from build_comparison import key, parse_deck  # noqa: E402

INV = ROOT / "inventory.csv"
FIELDS = ["Count", "Name", "Set", "Deck", "Source", "Acquired", "Notes"]


def deck_name(path):
    m = re.match(r"#\s*(.+)", path.read_text().splitlines()[0])
    return m.group(1).strip() if m else path.stem


def main():
    rows = list(csv.DictReader(INV.open()))
    # Merge previously split rows back together before re-assigning
    merged = {}
    for r in rows:
        k = (key(r["Name"]), r.get("Set", ""), r["Source"], r.get("Acquired", ""), r.get("Notes", ""))
        if k in merged:
            merged[k]["Count"] = str(int(merged[k]["Count"]) + int(r["Count"]))
        else:
            merged[k] = {**{f: r.get(f, "") for f in FIELDS}, "Deck": ""}
    pool = list(merged.values())
    for r in pool:
        r["_free"] = int(r["Count"])
        r["_alloc"] = {}

    missing = []
    for path in sorted((ROOT / "decks").glob("*.md")):
        name = deck_name(path)
        commanders, cards = parse_deck(path)
        for q, n in [(1, c) for c in commanders] + cards:
            cands = [r for r in pool if key(r["Name"]) == key(n) and r["_free"] > 0]
            cands.sort(key=lambda r: (f"for {name}".lower() not in r["Notes"].lower(),
                                      not r["Source"].lower().startswith(name.lower())))
            need = q
            for r in cands:
                take = min(need, r["_free"])
                r["_free"] -= take
                r["_alloc"][name] = r["_alloc"].get(name, 0) + take
                need -= take
                if not need:
                    break
            if need:
                missing.append(f"{name}: {need}× {n}")

    out = []
    for r in pool:
        base = {f: r[f] for f in FIELDS}
        for deck, n in r["_alloc"].items():
            out.append({**base, "Count": n, "Deck": deck})
        if r["_free"]:
            out.append({**base, "Count": r["_free"], "Deck": "Loose"})
    with INV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out)

    by_deck = {}
    for r in out:
        by_deck[r["Deck"]] = by_deck.get(r["Deck"], 0) + int(r["Count"])
    print("inventory:", ", ".join(f"{d} {n}" for d, n in sorted(by_deck.items())), f"(total {sum(by_deck.values())})")
    for m in missing:
        print(f"warning: not in inventory — {m}", file=sys.stderr)


if __name__ == "__main__":
    main()
