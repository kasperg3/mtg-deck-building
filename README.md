# MTG Collection

Published at **https://mtg.grontved.xyz**: a front page, the full decklists (upgrades marked against the precons) and the upgrade comparisons. GitHub Actions (`.github/workflows/pages.yml`) rebuilds it on every push to `main` and weekly for fresh prices.

Tracks the Magic: The Gathering decks and singles I own.

## Decks

| Deck | Commander | Colours | Source |
|------|-----------|---------|--------|
| [World Shaper](decks/world-shaper.md) | Hearthhull, the Worldseed | BRG | Edge of Eternities precon (2025) |
| [Mutant Menace](decks/mutant-menace.md) | The Wise Mothman | UBG | Fallout precon (2024) |
| [Counter Blitz](decks/counter-blitz.md) | Tidus, Yuna's Guardian | WUG | Final Fantasy X precon (2025) |

## Layout

- `decks/` — one file per deck as I play it. Card lines use `<qty> <name>` so each section can be pasted into Moxfield/Archidekt import. The changelog records every swap.
- `decks/precon/` — stock precon snapshots; upgrade comparisons are computed against these.
- `inventory.csv` — every card I own (decks and loose singles in one list): `Count, Name, Set, Deck, Source, Acquired, Notes`. **Deck** is the deck the card is in, or `Loose`; **Source** is where it came from (e.g. `World Shaper precon`, `Cardmarket`). Keep Deck in sync with `python3 tools/sync_inventory.py` after any deck change.
- `comparisons/` — upgrade proposals. `<deck>-upgrades.json` is the spec; `<deck>-upgrades.html` is the generated viewer (open in a browser).
- `tools/build_comparison.py` — builds a comparison page: `python3 tools/build_comparison.py comparisons/<deck>-upgrades.json`. Card images and cheapest paper prices (USD/EUR) come from Scryfall bulk data, cached locally in `.cache/` (not in git) and downloaded automatically when missing or a week old. `python3 tools/build_comparison.py --refresh` downloads it up front.
- `buylists/` — buy lists for chosen directions (`README.md` has the overall total). Build with `python3 tools/build_buylist.py comparisons/<deck>-upgrades.json:<direction-id> ...`.
- `tools/apply_direction.py` — applies a picked direction to `decks/<deck>.md` (regrouped list + changelog): `python3 tools/apply_direction.py comparisons/<deck>-upgrades.json <direction-id>`.
- `tools/build_site.py` — builds the website into `_site/` (front page, `decks/<deck>.html`, `comparisons/<deck>.html`). Preview locally with `python3 tools/build_site.py && xdg-open _site/index.html`.
- `.claude/skills/deck-comparison/` — the workflow Claude follows for upgrade comparisons, so they all share the same format.
- `.mcp.json` — registers the [mtg-search](https://github.com/kasperg3/mtg-search) MCP server (card search, rules text, deck checks) that the skill uses. Needs [uv](https://docs.astral.sh/uv/); download its card index once (~1.9 GB, into `~/.cache/mtg-search`) with `uvx mtg-search-mcp --download` before starting Claude Code.
