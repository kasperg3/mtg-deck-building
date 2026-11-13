# Data pipeline

## Source

17lands publishes one gzipped CSV per set and format:

```
https://17lands-public.s3.amazonaws.com/analysis_data/game_data/game_data_public.{SET}.{FORMAT}.csv.gz
```

`FORMAT` is `PremierDraft` by default (largest sample); `TradDraft` exists for most sets. A file
usually covers the set's first four to six weeks on MTG Arena (DSK: 24 Sep – 28 Oct 2024, 1.01M
games; VOW: 11 Nov – 10 Dec 2021, 494k games; BLB: 30 Jul – 3 Sep 2024, 931k games). Print those
dates on the page; that is the honest freshness statement.

Do not use `https://www.17lands.com/card_ratings/data` or `/color_ratings/data` for a past format:
they ignore `start_date`/`end_date` and return a small recent window (a few thousand games, or
zero counts). Don't use secondary write-ups either; they are usually from week one or two.

## Columns used

One row per game. `aggregate.py` reads only:

- `draft_time`: min and max become the date range
- `main_colors`: e.g. `WR`, in WUBRG order; splash colors are ignored (as 17lands does)
- `won`: boolean
- `opening_hand_<card>`, `drawn_<card>`: counts per card. GIH = opening_hand + drawn > 0

There are 1,500+ columns, so it reads in 50k-row chunks with float32 dtypes and `nan_to_num`
(some cells are empty, which breaks int dtypes). The per-pair accumulation uses a boolean
games × cards matrix per chunk; a per-card Python loop is 10× slower.

## Definitions

- **Set average** = wins / games over all rows. Around 54–55% because 17lands users are above
  average. Compare everything against it.
- **Color pair win rate** = games with exactly those two main colors.
- **Color win rate** = all two-color decks containing that color (used for "Red is the color to
  be in" and the anchor panel).
- **Card GIH WR** = wins / games where the card was in hand.
- **Per-pair card GIH WR** = the same, restricted to games with that pair as main colors. Pair top
  10s rank cards whose color identity fits inside the pair (colorless included).

## Thresholds

Noise on a win rate is about ±50/√n percentage points (n = 1,000 → ±1.6 pts). Thresholds scale
with the dataset's game count G so big and small formats get comparable noise:

| threshold | formula | DSK (1.01M) | VOW (494k) | used for |
|---|---|---|---|---|
| rank_min | max(250, 500·round(1.5·√G / 500)) | 1,500 | 1,000 | ranked + tiered |
| pair_min | max(200, 500·round(√G / 500)) | 1,000 | 500 | pair top 10s |
| index_min | max(100, rank_min / 5) | 300 | 200 | in search at all |

Override per set in the config (`"thresholds": {"pair_min": 750}`) when a pair list comes up
short or a small format needs it; say so in your reply. Rows in pair lists show their game count
so the user can see when a rare sits on 500 games.

## Name matching

17lands names double-faced cards either `A // B` or by the front face; `build_data.py` matches by
full name, then front face. Cards that match nothing in `set:xxx is:booster` are Special Guests or
List cards: dropped, and counted in the summary line.

## Takeaways and the plan check

`build_data.py` writes the chart takeaway from the numbers:

- If the top color leads the next by ≥ 0.8 pts → "<Color> is the color to be in…" plus how many of
  the top five pairs contain it; otherwise "<best pair> was the best pair…", adding the runner-up
  when within 1 pt.
- The highlight pair's rank against the average, and the two weakest pairs.

The anchor verdicts, per pair against the set average: ≥ +1.5 Strong, ≥ 0 Above avg, ≥ −1 Average,
otherwise Avoid. The panel says "look for X and stay away from Y" when any pair is Avoid, "every
pair beats the average, so follow the packs" when all are above, else names the best partner.

## Reproducing the reference numbers

The example config reproduces the published DSK + VOW sheet exactly: W/R 56.9% (DSK #1), U/R
52.1%, red decks 55.4% (DSK) and 55.9% (VOW), R/B 56.3% (VOW #1), W/R 55.4% (VOW #5), DSK bombs
led by Overlord of the Mistmoors 68.1%, VOW W/R top 10 led by Wedding Announcement 68.5%. If a
rerun on the same files gives different values, something in the pipeline changed.
