# Buy lists

Updated 2026-10-16 · prices from Scryfall bulk data of 2026-10-16.

| Deck | Direction | Cards | USD | EUR |
|---|---|---|---|---|
| [World Shaper](world-shaper.md) | Scorched Earth Drain | 10 | $37.34 | €29.63 |
| [Counter Blitz](counter-blitz.md) | Cheer Every Turn | 10 | $36.42 | €28.42 |
| [Mutant Menace](mutant-menace.md) | Counter Engine | 10 | $41.13 | €31.91 |
| **Total** | | **30** | **$114.89** | **€89.96** |

To order everything at once, paste [`cardmarket-all.txt`](cardmarket-all.txt) into one Cardmarket Wants list (**Add Deck List**), then run the **Shopping Wizard**. Per-deck files: [`world-shaper.cardmarket.txt`](world-shaper.cardmarket.txt), [`counter-blitz.cardmarket.txt`](counter-blitz.cardmarket.txt), [`mutant-menace.cardmarket.txt`](mutant-menace.cardmarket.txt).

Regenerate: `python3 tools/build_buylist.py comparisons/world-shaper-upgrades.json:drain comparisons/counter-blitz-upgrades.json:cheer comparisons/mutant-menace-upgrades.json:counters`
