---
name: deck-comparison
description: Analyse one of the user's decks (mana curve, removal and other interaction, card draw, ramp) and propose upgrade directions as card swaps, rendered as a reusable HTML comparison page with Scryfall card images and prices. Use when the user asks to upgrade, improve, compare directions for, or find swaps for a deck in decks/.
---

# Deck upgrade comparison

Produces `comparisons/<deck>-upgrades.json` (the spec, written by you) and
`comparisons/<deck>-upgrades.html` (generated, self-contained viewer). The page
shows card faces for every swap instead of rules text, so keep prose short.

## Every direction is an engine, not a list of swaps

Ten defensible one-for-ones can still be a bad deck. Judge a direction by what
it does once all ten cards are on the table, not by whether each cut is fair.

Keep a ledger for the stock list **before** choosing cards, and again after the
swaps. Every direction needs all three columns:

- **Enablers** — cards that make the engine fire: extra land drops for a
  landfall deck, sacrifice outlets for a death-trigger deck, top-deck control
  for a "cast from the top" commander, mana accelerants, recursion.
- **Payoffs** — cards that convert those triggers into advantage.
- **Support** — what keeps the engine alive: protection, evasion, card
  selection, graveyard hate for your own plan.

Rules that came out of getting this wrong:

1. **Buy the thin column.** Landing Party had ten landfall payoffs and one card
   that plays an extra land (Exploration), so the payoffs fired once a turn.
   Adding five *more* payoffs changed nothing; the direction had to buy land
   drops. If one column is at 8+ and the other at 1, more of the fat column is
   win-more, however good the individual cards are.
2. **Ask what the commander needs and whether the direction supplies it.**
   Spock needs the top card to be known, needs to survive, and needs to connect
   — the stock list gave him none of the three. A direction whose plan dies to
   one removal spell or one blocker is not a plan.
3. **Cards that fill two columns are the best slots.** Mole Man, Moloid Master
   is a land-drop enabler *and* a landfall payoff; Penance is top-deck control
   *and* a free cast.
4. **Check the package against itself.** Whispersilk Cloak grants shroud, which
   locks out your own Aqueous Form — Swiftfoot Boots (hexproof) was correct. A
   second "cast from the top" effect competes with the commander for the same
   card rather than supporting him.
5. **Say how it loses.** If a direction folds when the commander is answered
   twice, put that in the `pitch` and only recommend it to a user who wants a
   commander-centric build.

### Search by role, never by memory

Name the role you need, then search for it. Card names recalled from memory
skew to famous cards that don't fit the curve or the budget.

- `mcp__mtg-search__search_cards` when it is running; otherwise Scryfall search
  with `order=edhrec`, filtered to the commander's identity and your budget:
  - extra land drops: `f:commander id<=WUG o:"additional land" -t:land`
  - land recursion: `f:commander id<=WUG o:"play lands from your graveyard"`
  - top control: `f:commander id<=WUG o:"top card of your library" -t:instant -t:sorcery`
  - protection: `f:commander id<=WUG t:artifact (o:"hexproof" or o:"shroud") cmc<=3`
  - evasion: `f:commander id<=WUG o:"can't be blocked" cmc<=3`
  - putting a card back on top: `o:"on top of your library" owner:"its owner's library"`
    — then read the **cost**: Penance's is free, Conch Horn's sacrifices itself.
- Price every candidate from `.cache/card-index.json` before it goes in a spec.
- Say in the review which search produced a non-obvious pick, so the reasoning
  is checkable later.

## Scryfall data (local only)

Card images, mana values and prices come from Scryfall's `default_cards` bulk
file, reduced to `.cache/card-index.json`. The cache is **not in git**
(`.gitignore`), so a fresh clone won't have it.

- **Before pricing candidates or building**, check `.cache/card-index.json`.
  If it's missing or older than 7 days, download it first:
  `python3 tools/build_comparison.py --refresh`. That's an ~80 MB download,
  ~10 s, and leaves a ~20 MB index.
- Both build scripts also download it automatically when it's missing or
  stale, so `--refresh` is only needed up front or to force fresh prices.
- Never commit `.cache/`.
- `tools/verify_comparison.py` caches the rules text it fetches in
  `.cache/oracle.json` (also ignored), so repeated review runs work offline.

## Steps

1. **Load the deck.** Read `decks/<deck>.md`. Also call `mcp__mtg-search__get_deck`
   with the deck's card list or precon name; its output gives roles for each card.

2. **Analyse the stock list.** The build script computes the curve; you supply
   the judgement:
   - Curve: count nonland cards by mana value, note dead or clunky slots and the top end.
   - Interaction, counted against these targets for a casual or upgraded-precon table:

     | Category | Target |
     |---|---|
     | Spot removal | 8–10 |
     | Board wipes | 2–3 (fewer for go-wide decks) |
     | Instant-speed answers | 5+ |
     | Protection | 2–3 |
     | Card draw / advantage | 8–10 |
     | Ramp | 8–10 (plus 36–38 lands) |
   - Flag categories below target with `"low": true`.
   - Count Game Changers and note the bracket.

3. **Pick directions.** Propose **three** directions that fit the commander. Each
   direction has **10 swaps in total** (the user's standing request).
   - If interaction is short in every direction, put a shared **core package**
     (usually 3–5 cheap removal spells, preferably instants) in `core`. Each
     direction then gets `10 − len(core)` swaps of its own.
   - Cut the weakest cards first: cards that cost too much for their effect,
     do nothing on the board, or work against the direction.
   - Design each direction as one engine first (see **Every direction is an
     engine** above): write down the enablers, the payoffs and the support it
     needs, then choose cards that fill the gaps in the stock ledger. If the
     six direction cards don't reference each other, it's still a card list.
   - Lower or hold the average mana value. Never add a board wipe that hurts
     the deck's own plan.

4. **Respect the budget.** The user buys on Cardmarket. The default is
   **up to €20 per deck**, counting the core package. Set `budget_eur` in the
   spec (`budget_usd` also works). To price candidates before choosing, look
   them up in `.cache/card-index.json` (fields `eur` and `usd`, cheapest paper
   printing). Real Cardmarket totals have come in below these estimates
   (€26 actual against €35 estimated), but still keep about €1–2 of margin
   because prices drift between the weekly refreshes. Prefer cheap
   functional reprints, e.g. Ramunap Excavator over Crucible of Worlds.

5. **Find cards with the tools, not from memory.** Search by role (see **Search
   by role** above). With `mcp__mtg-search__search_cards`, set `color_identity`
   and `format="commander"` and send 2–4 queries worded like rules text; without
   it, use Scryfall search syntax. Check any card you name from memory against
   Scryfall before it reaches the spec.
   Don't add Game Changers unless the user wants a higher bracket. Avoid cards
   already in the deck. The build script warns about both problems.

6. **Write the spec** at `comparisons/<deck>-upgrades.json` using the schema below.
   Card names must match Scryfall exactly. Each `why` is one or two sentences
   covering what the new card does for the plan and why the old card is weaker.

7. **Build** (stdlib only, no installs):
   ```
   python3 tools/build_comparison.py comparisons/<deck>-upgrades.json
   ```
   - Prices and images come from Scryfall's `default_cards` bulk file, cached in
     `.cache/card-index.json`. The script re-downloads it automatically when it is
     older than 7 days; `--refresh` forces a re-download.
   - Fix every `warning:` line (unknown name, card not in deck, card already in
     deck) and rebuild.
   - The script prints the average mana value and the cost of the cards coming
     in for each direction.

8. **Report** in chat: a short table per direction with average MV, cost
   (USD/EUR) and plan, your recommendation, and the path to the HTML file.
   Don't repeat the swap list in prose; the page shows it. Offer to apply the
   chosen direction to `decks/<deck>.md`, adding a changelog entry.

## Review before the list is final

Mandatory. Run it **after the user picks a direction and before writing buy
lists, committing, or changing `decks/<deck>.md`**. Run it again whenever the
picked list changes (budget change, swapped card). It exists because the first
World Shaper list cut its own key creatures: Hearthhull's drain only works at
8+ charge counters, and Juri grows from *any* sacrificed permanent, not just
creatures.

1. **Read the exact rules text, never from memory or role tags.** Use
   `mcp__mtg-search__get_card` or the Scryfall API (`/cards/named?exact=`) for
   the commander and for **every card going in and every card coming out**.
   Watch for:
   - Station or level boxes: lines printed under `N+ |` belong to that box
     and only work at that level.
   - "Permanent" vs "creature" vs "land", "you control" vs "any player",
     once-per-turn limits, sorcery-speed restrictions.
   - What the commander needs to work (creatures with power for Station,
     counters already on creatures for Cheer, nonland mills for Mothman), and
     whether any cut removes one of those enablers.
2. **Check each cut against the plan.** For every card going out, ask: does it
   trigger, enable or pay off the commander or the direction? If yes, cut a
   different card. Record the reason in the swap's `why`.
3. **Check each new card's interactions.** Confirm each claimed combo actually
   works by its text (e.g. moving a counter is "putting" one, so +1 effects
   apply). Drop any claim you can't confirm.
4. **Validate the final 100 — mechanically, not by eye.**
   ```
   python3 tools/verify_comparison.py comparisons/<deck>-upgrades.json
   ```
   It re-applies the core plus each direction's swaps and checks: every cut is
   in the deck and every addition isn't, no card twice or both ways, 100 cards
   after the swaps, no land cut for a nonland, colour identity and Commander
   legality from Scryfall, Game Changers from the cached index, `budget_eur`,
   and the metrics it can derive from rules text (`Lands`, `Different land
   names`, `Extra land drops`, `Landfall payoffs`) so hand-counted numbers can't
   drift. Exit code 1 blocks the commit. Add `--offline` when Scryfall is
   unreachable; it works from `.cache/oracle.json`.
   For a per-direction card list, `python3 tools/build_comparison.py
   comparisons/<deck>-upgrades.json --after <direction-id>` still prints it.
   **Release gate:** a card from a set that hasn't released yet reports
   `not_legal` on Scryfall. That is not a deck problem — note the release date
   and carry on (the Landing Party precon releases 2026-11-13, so every TRC/TRK
   card read as illegal for the fortnight before it).
5. **Recount after the swaps** — the tool does the derivable ones; you still
   count spot removal, wipes, instant-speed answers, protection, card draw and
   ramp by hand, and update each direction's `metrics` so the page matches.
   Cross-check the directions against each other: categories the core supplies
   (spot removal, instant-speed answers, wipes) must come out *identical* in
   every direction unless that direction adds interaction of its own — if one
   number differs, you missed a count. Then re-check the ledger: does the
   direction still hold up as one engine, or did the swaps quietly remove an
   enabler or a payoff you counted on?
6. **Check consistency.** No stale text in the spec (old budget figures, cards
   no longer in the list, wrong claims in `why`/`pitch`/`notes`), the build
   shows no `warning:` lines, and the cost is within budget with margin.
7. **Report the review to the user:** what you changed and why, what passed,
   and any card you're unsure about (e.g. an odd price). Get their OK before
   writing buy lists, committing or editing deck files.

## After the user picks a direction

Set `"picked": true` on that direction in the spec and rebuild the page. Then
run **Review before the list is final** (above) before anything below.

Write the buy list (include every deck the user has picked so far, so the
combined total stays correct):
```
python3 tools/build_buylist.py comparisons/<deck>-upgrades.json:<direction-id> [...]
```
This writes `buylists/<deck>.md` (checklist, cheapest printing per currency,
mass-entry text) and `buylists/README.md` (combined total). Apply the swaps to
`decks/<deck>.md` only once the user has the cards.

When the user says they bought the cards:
1. Append one row per card to `inventory.csv`
   (`Count,Name,Set,Deck,Source,Acquired,Notes`): Source is the shop (e.g.
   `Cardmarket`), Acquired the date, Notes `for <Deck> (<direction>), replaces
   <card>`. Never remove rows for cut cards; they're still owned.
2. Apply the swaps to the deck file:
   `python3 tools/apply_direction.py comparisons/<deck>-upgrades.json <direction-id>`
   (reads the spec's `deck`, normally the stock snapshot in `decks/precon/`,
   and writes `decks/<deck>.md` with a changelog entry).
3. `python3 tools/sync_inventory.py` to fill the Deck column (cut cards become
   `Loose`). It must report no `warning:` lines.

For a new comparison on an already-upgraded deck, point the spec's `deck` at
`decks/<deck>.md` (the current list), not the precon snapshot.

## Spec schema

```jsonc
{
  "title": "Mutant Menace — Upgrade Options",
  "deck": "decks/mutant-menace.md",          // repo-relative path
  "date": "YYYY-MM-DD",
  "budget_eur": 20,                          // optional (or budget_usd); build warns when a direction's cards-in cost exceeds it
  "summary": "One paragraph: what the commander does and the overall plan.",
  "analysis": {
    "notes": ["Curve / mana / weakness observations, one line each"],
    "interaction": [
      {"category": "Spot removal", "stock": 5, "target": "8–10", "low": true, "cards": ["Putrefy", "..."]}
    ],
    "stock_metrics": {"Spot removal": 5, "Game Changers": 0}   // the "Stock" column of the comparison table
  },
  "core": {                                   // optional; omit or empty swaps if not needed
    "name": "Core interaction package",
    "description": "Why these go in every direction.",
    "swaps": [{"in": "Card In", "out": "Card Out", "why": "..."}]
  },
  "directions": [
    {
      "id": "counters",                       // anchor slug
      "name": "Counter Engine",
      "recommended": true,                    // exactly one direction
      "picked": true,                         // set once the user chooses it: green badge, buy list opens by default
      "pitch": "One or two sentences on the plan.",
      "plays_like": "Short phrase for the comparison table",
      "metrics": {"Spot removal": 9, "Game Changers": 0},   // same keys as stock_metrics
      "how_to_play": {                        // collapsible guide under the direction (open when picked)
        "summary": "One line: how this version wins.",
        "sections": [{"title": "Turns 1–3", "points": ["Short, concrete play tips naming the deck's cards"]}]
      },
      "swaps": [{"in": "Card In", "out": "Card Out", "why": "..."}]
    }
  ],
  "recommendation": "Which direction and why, in one or two sentences."
}
```

The build script adds the curve, average MV and costs for each direction. Don't
put those numbers in the spec.

## Viewer

`tools/comparison_template.html` is the single template for every comparison.
Change the look there; don't edit generated `.html` files.

Builds are deterministic: `generated` in the page data comes from the spec's
`date`, and the site footer prints the date of the price snapshot instead of the
build clock. Rebuilding an unchanged tree therefore produces byte-identical
files — if a rebuild dirties generated HTML, prices actually moved and the diff
should be committed deliberately. Every page has the
same sections: header with commander, stock analysis (curve and interaction
table), comparison table (avg MV, cost in, value out, metrics), curve per
direction against stock, core package, then each direction as OUT → IN card
pairs, with an expandable buy list for each direction: a price table and a
Cardmarket-ready text box with a Copy button, then a collapsible How to play guide. Clicking a card opens a large image, showing both faces for
double-faced cards.

## Website

The repo is published at https://mtg.grontved.xyz by GitHub Actions
(`.github/workflows/pages.yml` runs `tools/build_site.py` on every push to
`main`). Pushing a changed deck file, comparison spec or inventory is enough;
there's nothing to deploy by hand. Deck pages mark cards that differ from
`decks/precon/<deck>.md` as "Added" and list cut cards. To preview locally:
`python3 tools/build_site.py && xdg-open _site/index.html`.
