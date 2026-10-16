#!/usr/bin/env python3
"""Build buy lists for chosen upgrade directions.

Usage:
    python3 tools/build_buylist.py comparisons/<deck>-upgrades.json:<direction-id> [...]

For each spec:direction pair, writes buylists/<deck>.md with the cards to buy
(core package + direction swaps), the cheapest paper price in USD and EUR and
which printing it comes from, and what each card replaces. Also writes
buylists/<deck>.cardmarket.txt and buylists/cardmarket-all.txt, one
"1 Card Name" per line, which is the format Cardmarket's Wants list
"Add Deck List" accepts (any printing, so the Shopping Wizard can pick the
cheapest offers), and buylists/README.md with the combined total.

Prices come from the same local Scryfall index as build_comparison.py
(.cache/card-index.json); run that script first if the index is missing.
"""

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from build_comparison import key, load_index  # noqa: E402

OUT_DIR = ROOT / "buylists"


def money(v, sym):
    return "—" if v is None else f"{sym}{v:.2f}"


def cardmarket_text(names):
    """One '<qty> <name>' per line, quantities merged (Cardmarket Wants 'Add Deck List' format)."""
    counts = {}
    for n in names:
        counts[n] = counts.get(n, 0) + 1
    return "".join(f"{q} {n}\n" for n, q in counts.items())


def build(spec_path, direction_id, cards, bulk_date):
    spec = json.loads(Path(spec_path).read_text())
    direction = next((d for d in spec["directions"] if d["id"] == direction_id), None)
    if direction is None:
        ids = ", ".join(d["id"] for d in spec["directions"])
        sys.exit(f"{spec_path}: no direction '{direction_id}' (have: {ids})")
    core = (spec.get("core") or {}).get("swaps", [])
    swaps = [(s, "core") for s in core] + [(s, direction["name"]) for s in direction["swaps"]]

    rows, total_usd, total_eur, missing = [], 0.0, 0.0, []
    for s, group in swaps:
        c = cards.get(key(s["in"])) or {}
        usd, eur = c.get("usd"), c.get("eur")
        if usd is None and eur is None:
            missing.append(s["in"])
        total_usd += usd or 0
        total_eur += eur or 0
        rows.append((s, group, c, usd, eur))
    rows.sort(key=lambda r: -(r[3] or 0))

    deck_name = spec["title"].split(" — ")[0]
    deck_slug = Path(spec["deck"]).stem
    lines = [
        f"# Buy list — {deck_name}",
        "",
        f"- **Direction:** {direction['name']}" + (f" + {spec['core']['name']}" if core else ""),
        f"- **Cards to buy:** {len(rows)}",
        f"- **Total (cheapest printings):** {money(total_usd, '$')} · {money(total_eur, '€')}"
        + (f" (budget €{spec['budget_eur']})" if spec.get("budget_eur") else f" (budget ${spec['budget_usd']})" if spec.get("budget_usd") else ""),
        f"- **Prices:** Scryfall bulk data of {bulk_date}; USD = TCGplayer, EUR = Cardmarket. "
        "The cheapest USD and EUR printings can differ.",
        f"- **Comparison page:** [`{Path(spec_path).with_suffix('.html').name}`](../{Path(spec_path).with_suffix('.html').as_posix()})",
        "",
        "| ✓ | Card | MV | USD | cheapest USD printing | EUR | cheapest EUR printing | Replaces | Part of |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s, group, c, usd, eur in rows:
        name = f"[{s['in']}]({c['scryfall_uri']})" if c.get("scryfall_uri") else s["in"]
        lines.append(f"| ☐ | {name} | {int(c.get('cmc', 0))} | {money(usd, '$')} | {c.get('usd_set') or '—'} "
                     f"| {money(eur, '€')} | {c.get('eur_set') or '—'} | {s['out']} | {group} |")
    lines += [
        "",
        "## Import into Cardmarket",
        f"1. On Cardmarket, create a Wants list (Wants → Create list → Magic) named e.g. \"{deck_name} upgrades\".",
        f"2. Paste the contents of [`{deck_slug}.cardmarket.txt`]({deck_slug}.cardmarket.txt) (below) into **Add Deck List** and press **Add**.",
        "3. Open the list and use **Shopping Wizard** to find the cheapest combination of sellers.",
        "",
        "The same text also works for TCGplayer Mass Entry.",
        "",
        "```",
        *[f"1 {s['in']}" for s, *_ in rows],
        "```",
        "",
        "## Cards coming out of the deck",
        "",
        *[f"- {s['out']} → {s['in']}" for s, *_ in swaps],
        "",
    ]
    if missing:
        lines += ["> No price found for: " + ", ".join(missing), ""]
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"{deck_slug}.md"
    out.write_text("\n".join(lines))
    (OUT_DIR / f"{deck_slug}.cardmarket.txt").write_text(cardmarket_text(s["in"] for s, *_ in rows))
    return {"cards": [s["in"] for s, *_ in rows], "deck": deck_name, "slug": deck_slug, "direction": direction["name"], "count": len(rows),
            "usd": round(total_usd, 2), "eur": round(total_eur, 2), "file": out}


def main():
    if len(sys.argv) < 2 or any(":" not in a for a in sys.argv[1:]):
        sys.exit(__doc__)
    index = load_index(refresh=False, max_age_days=7)
    bulk_date = (index.get("bulk_updated") or "")[:10]
    results = [build(*arg.rsplit(":", 1), index["cards"], bulk_date) for arg in sys.argv[1:]]

    lines = [
        "# Buy lists",
        "",
        f"Updated {date.today().isoformat()} · prices from Scryfall bulk data of {bulk_date}.",
        "",
        "| Deck | Direction | Cards | USD | EUR |",
        "|---|---|---|---|---|",
        *[f"| [{r['deck']}]({r['slug']}.md) | {r['direction']} | {r['count']} | ${r['usd']:.2f} | €{r['eur']:.2f} |" for r in results],
        f"| **Total** | | **{sum(r['count'] for r in results)}** | **${sum(r['usd'] for r in results):.2f}** "
        f"| **€{sum(r['eur'] for r in results):.2f}** |",
        "",
        "To order everything at once, paste [`cardmarket-all.txt`](cardmarket-all.txt) into one Cardmarket Wants list "
        "(**Add Deck List**), then run the **Shopping Wizard**. Per-deck files: "
        + ", ".join(f"[`{r['slug']}.cardmarket.txt`]({r['slug']}.cardmarket.txt)" for r in results) + ".",
        "",
        "Regenerate: `python3 tools/build_buylist.py " + " ".join(sys.argv[1:]) + "`",
        "",
    ]
    (OUT_DIR / "README.md").write_text("\n".join(lines))
    (OUT_DIR / "cardmarket-all.txt").write_text(cardmarket_text(n for r in results for n in r["cards"]))
    for r in results:
        print(f"wrote {r['file'].relative_to(ROOT)}: {r['count']} cards, ${r['usd']:.2f} / €{r['eur']:.2f}")


if __name__ == "__main__":
    main()
