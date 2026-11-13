# prep.json and the page

## Schema

```jsonc
{
  "title": "Draft Night Cheat Sheet",          // page name and <title>; optional
  "lede": "…",                                 // one sentence under the title; generated if omitted
  "anchor": "R",                               // the user's first color; omit for no "Going …" panel
  "featured_pairs": ["WR", "BR", "WU"],        // 2–4 pairs that get a top 10 each (any letter order)
  "highlight_pair": "WR",                      // gold row in the chart; defaults to the first featured
  "pair_names": {"BR": ["Red–Black", "R/B"]},  // display name + short label; default is WUBRG order
  "deck_note": "is fine for a low-curve W/R deck",   // text after "16 lands"
  "cross_set_note": "…",                       // pack-flow note for mixed drafts; has a default
  "booster_source": "Wizards of the Coast and mtg.wtf",  // footer credit for booster facts
  "theme": {"--bg": "#141118"},                // CSS token overrides (see page.css :root)
  "sets": [
    {
      "code": "DSK",                           // 17lands + Scryfall set code
      "name": "Duskmourn",                     // short name on buttons and headings
      "full": "Duskmourn: House of Horror",
      "color": "#A898E8",                      // set accent; a default palette is used if omitted
      "booster": {"name": "Play Booster", "cards": 14, "facts": ["…", "…"]},
      "keywords": [["Rooms", "…"], ["Eerie", "…"]],
      "thresholds": {"rank_min": 1500, "pair_min": 1000, "index_min": 300}  // optional overrides
    }
  ]
}
```

The order of `sets` is the order of the set-switch buttons; the first set shows by default. A
`#<code>` hash (e.g. `#vow`) or the viewer's last choice (localStorage) picks the starting set.

## Writing the prose

- Keyword lines: one or two plain sentences each, from the card's reminder text, said the way a
  friend would explain it at the table. Name the payoff when it isn't obvious ("Delirium: a
  bonus once your graveyard holds 4+ card types").
- Booster facts: counts first, then one practical tip (e.g. which common dual matches the plan).
- No hedges, no article numbers, no grades. Every number on the page is generated.

## Page structure

1. Header: title, lede.
2. Sticky bar: set switch (2+ sets), search over every card with data in every set. Results show
   tier, win rate, rank (or "small sample"), set, colors and rarity.
3. "Every pick" strip: bombs › cheap removal › flyers › efficient creatures › the rest.
4. "Going <color>" fold (open): one column per set with the anchor's four pairs, win rate and
   verdict, plus the generated advice sentence.
5. Per set (one visible at a time): "Open all" button, then folds:
   - Color pairs (open): takeaway + chart. The scale runs from 50% (or lower) to 58% (or higher),
     with a marker at the set average and the highlight pair in gold.
   - Bombs: the set's top 10 by GIH WR, any color.
   - One "<Pair> top 10" per featured pair, then its best 5 commons outside the top 10. The summary
     shows the pair's win rate and rank.
   - Keywords.
6. Pack flow, a 40-card build (17/23, curve), booster facts, and the source footer with dates,
   game counts, averages, tier cut-offs and thresholds.

Card rows: tap-to-zoom thumbnail (Scryfall small → normal), name linking to Scryfall, back-face
name for double-faced cards, cost pips, type, rarity, tier chip (set-wide), win rate, and rank or
game count.

## Design

`page.css` carries a dark single theme (from the first user's mockup) as tokens on `:root`. To
follow a different mockup, override tokens through `theme` and set each set's `color`. Keep the
structural rules: `[hidden]{display:none!important}`, the hidden native search clear button, the
16px side gutter with safe-area `max()`, `min-width: 0` on text columns, and the 520px breakpoint.
Fonts load from Google Fonts (Fraunces display, Inter body) with system fallbacks.

## Publishing

- Page: `<work>/site/draft-night-cheat-sheet.html` (a page body; the artifact host wraps it).
- Files: `<work>/files_map.json` → the Artifact tool's `files`, with `root` = `<work>/site`.
  Paths are `img/sm/<set>-<num>.jpg` and `img/lg/<set>-<num>.jpg`; `null` entries remove images
  that dropped off the lists.
- Icon: a generic word such as `cards`. Description: one sentence naming the sets.
- Revisions keep the URL: republish the same file path, or pass the URL (read it first when it
  came from another session).
