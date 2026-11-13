---
name: draft-night-prep
description: Build a precise, phone-first draft-night cheat sheet for any Magic Limited event (one set or a mixed draft of several sets) as a published artifact. It covers card lookup, color-pair win rates, bombs, a top 10 per color pair, a second-color guide for the user's main color ("going red"), keywords and booster contents, all from 17lands public game data and Scryfall images. Use whenever the user mentions an upcoming draft, prerelease-style booster draft, draft night, LGS draft, cube-like mixed-set draft, "cheat sheet", pick orders, which colors are best in a set, or asks to check their draft plan, even if they don't ask for a page.
---

# Draft night prep

Produces one artifact page the user can hold in one hand at the table: a sticky set switch and
card search, then collapsible sections per set. Every number on it comes from the 17lands public
game data, with dates and game counts printed in the footer. The pipeline lives in `scripts/`
and turns a small config (`prep.json`) into the page. You write the config, read the numbers,
and check the user's plan against them.

## Why the rules below exist

They come from a real prep session where the first draft of the page was wrong in ways the user
would only have found mid-draft:

- **Stale numbers.** Articles quote win rates from a format's first week or two. Crimson Vow's
  R/B was quoted at 57.3%; the full month of data says 56.3%. Lantern Flare and Piercing Light
  were "top picks" by review grade but ranked #86 and #189 of 259 by data. So the page shows only
  numbers computed from the dataset, never article figures or grades (Draftsim, LSV and the like).
- **The 17lands API trap.** `card_ratings/data` and `color_ratings/data` ignore `start_date` and
  `end_date` now and return a small recent window, often near-empty for an old set. Use the
  public game-data files (`scripts/aggregate.py` downloads them).
- **Booster miscount.** Play Boosters were drawn as 6 commons + 3 wildcards; they have 7 common
  slots, 2 wildcards (one foil) and a land slot that can hold a common dual. Verify booster facts
  (see `references/boosters.md`) rather than writing them from memory.
- **Overlay bug.** The zoom overlay set `display:flex`, which beat the `hidden` attribute and
  covered the page, blocking every tap. The stylesheet carries `[hidden]{display:none!important}`
  and the render check runs without the host's reset so it catches a regression.
- **"Equally good" plans.** The user planned "red first, second color doesn't matter". True in
  Crimson Vow (all red pairs above average), false in Duskmourn (W/R best at 56.9%, U/R 8th of 10
  at 52.1%). Always check the plan against the per-set table and say so with numbers.

## Workflow

### 1. Intake

You need, per set: the set code (DSK, VOW, BLB…) and whether its packs are Play Boosters or Draft
Boosters (sets from MKM onward are Play Boosters). Also note the user's plan if they have one: an
anchor color ("going red") and pairs they care about. Ask only for what you can't infer. If the
user supplies a design mockup, keep its look: map its colors and fonts onto the tokens at the top
of `scripts/page.css` through the config's `theme` map, and set each set's `color`.

Featured pairs default to: every pair containing the anchor color that is above average in at
least one set, plus the pairs the user names; keep it to 2–4 so the page stays navigable.

### 2. Data

Work in a scratch directory outside the repo; the game data is 30–80 MB per set.

```bash
SK=.claude/skills/draft-night-prep
W=<scratchpad>/draft-prep
python3 $SK/scripts/aggregate.py --work $W --set DSK     # downloads + aggregates (about 1 min)
python3 $SK/scripts/scryfall_set.py --work $W --set DSK  # booster card list, oracle text
```

`aggregate.py` prints games, average win rate and the draft dates. If the download 404s, 17lands
hasn't published that set: tell the user, and don't substitute API or article numbers.

### 3. Write prep.json

Copy `assets/prep.example.json` (the DSK + VOW sheet, red anchor) and edit it. The schema and
every optional key are in `references/page-config.md`. The parts you write by hand:

- **keywords**: 5–7 per set, written from the oracle text in `data/sf_<SET>.json`, never from
  memory. `scryfall_set.py` prints the most common keywords; check each one's reminder text.
  Skip evergreen ones (flying, trample) unless the set does something new with them.
- **booster facts**: 2–3 lines per set, verified per `references/boosters.md`.
- **pair_names**: use the user's wording for a pair (they said "red black", so
  `"BR": ["Red–Black", "R/B"]`).
- **deck_note**: the 16-land line, tuned to the plan ("is fine for a low-curve W/R deck").

### 4. Build, read and check the plan

```bash
python3 $SK/scripts/build_data.py --work $W --config $W/prep.json
```

It prints, per set: thresholds, the pair ranking, per-color win rates, bombs, each featured
pair's top 10 and commons, and a **plan check** table for the anchor color. Read it before
building the page:

- Sanity-check the takeaways it generated (they are written from the numbers and go on the page).
- If a pair list warns that fewer than 10 cards cleared the sample threshold, say so or drop that
  pair.
- Prepare the plan correction for your reply: which partner colors are strong, which to avoid,
  per set, with win rates and the set average.

### 5. Images, page, render check

```bash
python3 $SK/scripts/fetch_images.py --work $W --prune   # Scryfall small + normal for listed cards
python3 $SK/scripts/gen_page.py --work $W --config $W/prep.json
node $SK/scripts/render_check.js $W/site/draft-night-cheat-sheet.html $W/shots "<a card name>"
```

Or run everything with `python3 $SK/scripts/prep.py --work $W --config $W/prep.json`.
`render_check.js` fails on horizontal overflow, broken images, console errors, placeholder text,
a visible overlay at load, or a broken set switch, search, Open all / Close all or zoom. Fix
every failure, then take one look at `$W/shots/phone.png` and `desktop.png`.

### 6. Publish

Before writing any artifact, follow the Artifact tool's own instructions (quickstart / design
guidance). Then publish `$W/site/draft-night-cheat-sheet.html` as a plain HTML artifact with
`root` = `$W/site` and `files` = the contents of `$W/files_map.json`. External images are blocked
by the artifact CSP, so the images must travel as files. More than 255 files: publish twice to the
same URL.

Revisions: republish the same file path in this session, or pass the existing URL from another
session (read it first). Images that dropped off the lists appear as `null` in the files map after
`--prune`, which removes them from the artifact. Delete an old artifact only when the user asks.

### 7. Reply and clean up

Lead with the link, then the plan check as a small table (pair, win rate per set, set average),
and one sentence per set on what to do. Name anything the data couldn't settle. Delete
`$W/data/*.csv.gz` when the page is final.

## Rules for numbers

- **Source of truth**: 17lands public game data (Premier Draft by default). State dates and game
  counts for every set in the footer; the generator does this.
- **GIH WR** (opening hand or drawn) is the card number; per-pair lists use GIH WR in decks whose
  two main colors are exactly that pair, with the game count shown on each row.
- **Compare with the set average**, not 50%. 17lands users win about 54–55%.
- **Tiers are percentiles within a set** (Bomb top 5%, Great next 10%, Good next 20%, OK next 30%,
  Weak the rest), among cards above `rank_min` games. Thresholds scale with sample size; see
  `references/data-pipeline.md`.
- Leave out basic lands and cards Scryfall doesn't list in the set (Special Guests, The List).
- No third-party grades, tier lists or article quotes on the page. If the user asks about one,
  compare it with the data in chat.

## Page anatomy (what gen_page.py renders)

Header and lede; sticky bar (set switch for 2+ sets, search across all sets); pick-order strip;
the "Going <color>" panel (open, only with an anchor); per set: Open all / Close all, then folds
for Color pairs (open, chart to scale with an average marker and the highlight pair in gold),
Bombs (top 10 any color), one top 10 + best 5 commons per featured pair, Keywords; then pack flow,
40-card build, booster facts and the source footer. Card rows show a thumbnail (tap to zoom), cost
pips, type, rarity, tier chip, win rate and rank or game count. Details and how to change any of
this: `references/page-config.md`.

## Files

- `scripts/aggregate.py`: download and aggregate 17lands game data for one set
- `scripts/scryfall_set.py`: booster card list with oracle text
- `scripts/build_data.py`: tiers, pair lists, takeaways, plan check → `page_data.json`
- `scripts/fetch_images.py`: Scryfall images for listed cards, `files_map.json`
- `scripts/gen_page.py` + `page.css` + `page.js`: the page
- `scripts/render_check.js`: Playwright check at 1280px and 400px
- `scripts/prep.py`: runs all of the above
- `assets/prep.example.json`: a complete config (Duskmourn + Crimson Vow, red anchor)
- `references/data-pipeline.md`, `references/page-config.md`, `references/boosters.md`
