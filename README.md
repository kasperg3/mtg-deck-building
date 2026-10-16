# MTG Collection

Tracks the Magic: The Gathering decks and singles I own.

## Decks

| Deck | Commander | Colours | Source |
|------|-----------|---------|--------|
| [World Shaper](decks/world-shaper.md) | Hearthhull, the Worldseed | BRG | Edge of Eternities precon (2025) |
| [Mutant Menace](decks/mutant-menace.md) | The Wise Mothman | UBG | Fallout precon (2024) |
| [Counter Blitz](decks/counter-blitz.md) | Tidus, Yuna's Guardian | WUG | Final Fantasy X precon (2025) |

## Layout

- `decks/` — one file per deck. Card lines use `<qty> <name>` so each section can be pasted into Moxfield/Archidekt import. Record swaps in the deck's changelog.
- `inventory.csv` — every card I own, one row per card and source: `Count, Name, Set, Source, Acquired, Notes`. Source is where it came from (e.g. `World Shaper precon`, `Cardmarket`). Cards not in a deck file are my loose singles. The first three columns import into Moxfield/ManaBox collections.
- `comparisons/` — upgrade proposals. `<deck>-upgrades.json` is the spec; `<deck>-upgrades.html` is the generated viewer (open in a browser).
- `tools/build_comparison.py` — builds a comparison page: `python3 tools/build_comparison.py comparisons/<deck>-upgrades.json`. Card images and cheapest paper prices (USD/EUR) come from Scryfall bulk data, cached locally in `.cache/` (not in git) and downloaded automatically when missing or a week old. `python3 tools/build_comparison.py --refresh` downloads it up front.
- `buylists/` — buy lists for chosen directions (`README.md` has the overall total). Build with `python3 tools/build_buylist.py comparisons/<deck>-upgrades.json:<direction-id> ...`.
- `.claude/skills/deck-comparison/` — the workflow Claude follows for upgrade comparisons, so they all share the same format.
