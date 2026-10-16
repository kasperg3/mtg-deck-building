#!/usr/bin/env python3
"""Apply a picked upgrade direction to its deck file.

Usage:
    python3 tools/apply_direction.py comparisons/<deck>-upgrades.json <direction-id> [--date YYYY-MM-DD]

Applies the core package and the direction's swaps to the spec's `deck` list
(usually the stock snapshot in decks/precon/) and writes the result to
decks/<deck>.md,
regroups the list by card type, sets the Status line, and appends a
changelog entry listing every swap. Run the deck-comparison review first,
and only once the user has the cards. Afterwards run
tools/sync_inventory.py so the inventory's Deck column matches.
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from build_comparison import apply_swaps, key, load_index, parse_deck  # noqa: E402

SECTIONS = ["Creatures", "Planeswalkers", "Instants", "Sorceries", "Artifacts", "Enchantments", "Battles", "Lands"]


def section_for(type_line):
    front = type_line.split("//")[0]
    for word, sec in (("Land", "Lands"), ("Creature", "Creatures"), ("Planeswalker", "Planeswalkers"),
                      ("Instant", "Instants"), ("Sorcery", "Sorceries"), ("Battle", "Battles"),
                      ("Artifact", "Artifacts"), ("Enchantment", "Enchantments")):
        if word in front:
            return sec
    return "Other"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("direction")
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text())
    stock_path = ROOT / spec["deck"]                     # list the swaps are relative to (e.g. decks/precon/x.md)
    deck_path = ROOT / "decks" / Path(spec["deck"]).name  # the deck file that gets updated
    d = next((x for x in spec["directions"] if x["id"] == args.direction), None)
    if d is None:
        sys.exit(f"no direction '{args.direction}'")
    swaps = (spec.get("core") or {"swaps": []})["swaps"] + d["swaps"]
    commanders, stock = parse_deck(stock_path)
    after, problems = apply_swaps(stock, swaps)
    if problems:
        sys.exit("refusing to apply: " + "; ".join(problems))

    cards = load_index(refresh=False, max_age_days=7)["cards"]
    groups = {}
    for q, n in after:
        info = cards.get(key(n))
        if not info:
            sys.exit(f"card not in Scryfall index: {n}")
        groups.setdefault(section_for(info["type_line"]), []).append((q, n, info["cmc"]))

    text = deck_path.read_text()
    header, _, rest = text.partition("\n## ")
    changelog = rest[rest.index("## Changelog"):] if "## Changelog" in rest else "## Changelog\n"
    if not changelog.startswith("## Changelog"):
        changelog = "## Changelog\n"
    header = re.sub(r"- \*\*Status:\*\*.*", f"- **Status:** Owned · upgraded: {d['name']} ({args.date})", header)

    out = [header.rstrip(), "", f"## Commander ({len(commanders)})", *[f"1 {c}" for c in commanders], ""]
    for sec in SECTIONS + ["Other"]:
        items = groups.get(sec)
        if not items:
            continue
        # basics last within lands; otherwise by mana value, then name
        items.sort(key=lambda x: ("Basic" in cards[key(x[1])]["type_line"], x[2], x[1]))
        out += [f"## {sec} ({sum(q for q, *_ in items)})", *[f"{q} {n}" for q, n, _ in items], ""]
    entry = [f"- {args.date} — Applied **{d['name']}** from `{Path(args.spec).name}` ({len(swaps)} swaps):",
             *[f"  - +{s['in']} / −{s['out']}" for s in swaps]]
    if f"Applied **{d['name']}** from `{Path(args.spec).name}`" in changelog:
        entry = []  # already recorded; re-running only refreshes the list
    out += [changelog.rstrip(), *entry, ""]
    deck_path.write_text("\n".join(out))
    total = len(commanders) + sum(q for q, _ in after)
    print(f"updated {deck_path.relative_to(ROOT)}: {total} cards, {len(swaps)} swaps")


if __name__ == "__main__":
    main()
