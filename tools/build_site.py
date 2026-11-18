#!/usr/bin/env python3
"""Build the static website (GitHub Pages) from the repo.

Usage:
    python3 tools/build_site.py [--out _site] [--cname mtg.grontved.xyz]

Pages:
    index.html                     front page: the decks, each with its chosen
                                   upgrade direction, plus the bulk list
    decks/<deck>.html              one page per deck: how to play it (the
                                   picked direction and its guide), every
                                   swap from the precon with the reason for it,
                                   grouped as core package, picked direction,
                                   later changes and the bracket 3 package (when
                                   applied or planned), then the current
                                   decklist as a list or as card images
    inventory.html                 the bulk list: every owned card, loose cards
                                   first, with search, filters and prices
    comparisons/<deck>.html        only while a deck's spec has no picked
                                   direction: the comparison page (restyled to
                                   match), so a direction can be chosen

Only what was chosen is shown: directions that were not picked, declined
bracket 3 packages and premium options stay in the spec, not on the site.

Card data comes from the local Scryfall index (.cache/card-index.json),
downloaded automatically when missing or older than a week. CI runs this on
every push to main (see .github/workflows/pages.yml).
"""

import argparse
import csv
import hashlib
import html
import json
import math
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from apply_direction import SECTIONS, section_for  # noqa: E402
from build_comparison import fetch_cards, key, load_index, parse_deck  # noqa: E402

E = html.escape
COLOUR_ORDER = "WUBRG"
COLOUR_NAMES = {"White": "W", "Blue": "U", "Black": "B", "Red": "R", "Green": "G"}
BASICS = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}
NUMBER_WORDS = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"]
REPO = "https://github.com/kasperg3/mtg-deck-building"
# Date of the Scryfall bulk snapshot the pages were built from. Kept out of the
# build clock so rebuilding an unchanged tree produces byte-identical pages.
PRICES_AS_OF = ""

FONTS = ("https://fonts.googleapis.com/css2?family=Oswald:wght@300;400;500"
         "&family=Mona+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap")
FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
           "%3Crect width='32' height='32' fill='%231d1df2'/%3E%3Cpath d='M16 5 27 16 16 27 5 16Z' "
           "fill='none' stroke='white' stroke-width='2'/%3E%3C/svg%3E")

# ---------------------------------------------------------------- styles

# Tokens shared with tools/comparison_template.html (same names), so the
# header injected into a comparison page looks the same as on the site.
TOKENS = r"""
:root {
  color-scheme: dark;
  --ink: #0a0a1c; --ink-2: #0f0f27; --ink-3: #16163a;
  --line: rgba(176,176,255,.12); --line-2: rgba(176,176,255,.24);
  --paper: #f4f4fb; --text: #d9d9ea; --muted: #9696bd; --faint: #686894;
  --brand: #1d1df2; --lift: #8c8cff; --frame: #5b5be8;
  --in: #00f279; --out: #ff4f9a; --gc: #f2f200; --plan: #ffa31a;
  --W: #f7efcf; --U: #5cb4ff; --B: #c3b9d9; --R: #ff6b55; --G: #3ee08c;
  --display: "Oswald", "Arial Narrow", sans-serif;
  --body: "Mona Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
  --max: 1200px; --gut: clamp(16px, 4vw, 48px);
}
"""

NAV_CSS = r"""
.top { max-width: var(--max); margin: 0 auto; padding: 22px var(--gut) 18px; display: grid;
  grid-template-columns: minmax(0,1fr) auto minmax(0,1fr); align-items: center; gap: 24px; }
.top nav { display: flex; align-items: center; justify-content: space-around; gap: 18px; }
.top nav a { font: 400 13px/1 var(--display); letter-spacing: .09em; text-transform: uppercase;
  color: var(--text); text-decoration: none; white-space: nowrap; }
.top nav a:hover, .top nav a.cur { color: var(--lift); }
.top nav a.cur { text-decoration: underline; text-underline-offset: 7px; text-decoration-thickness: 1px; }
.top .mark { font: 300 30px/.92 var(--display); color: var(--paper); text-align: center; text-decoration: none; letter-spacing: -.01em; }
.top .mark:hover { color: var(--lift); }
.top .nav-m { display: none; }
.top .btn-w { display: inline-flex; align-items: center; height: 32px; padding: 0 12px; background: var(--paper);
  color: var(--brand) !important; text-decoration: none !important; font: 500 13px/1 var(--display); letter-spacing: .06em; text-transform: uppercase; }
.top .btn-w:hover { background: #fff; }
@media (max-width: 900px) {
  .top { grid-template-columns: auto 1fr; gap: 10px 16px; padding-top: 18px; }
  .top .nav-l, .top .nav-r { display: none; }
  .top .mark { text-align: left; font-size: 24px; }
  .top .nav-m { display: flex; grid-column: 1 / -1; justify-content: flex-start; gap: 20px; overflow-x: auto;
    padding: 12px 0 4px; border-top: 1px solid var(--line); scrollbar-width: none;
    -webkit-mask-image: linear-gradient(to right, #000 82%, transparent); mask-image: linear-gradient(to right, #000 82%, transparent); }
  .top .nav-m::-webkit-scrollbar { display: none; }
}
"""

CSS = r"""
* { box-sizing: border-box; }
html { scroll-behavior: smooth; -webkit-text-size-adjust: 100%; }
@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } *, *::before, *::after { transition: none !important; animation: none !important; } }
body { margin: 0; background: var(--ink); color: var(--text); font: 400 16px/1.6 var(--body); -webkit-font-smoothing: antialiased; overflow-x: hidden; }
body::after { content: ""; position: fixed; inset: 0; border: 3px solid var(--frame); pointer-events: none; z-index: 95; }
::selection { background: var(--brand); color: #fff; }
:focus-visible { outline: 2px solid var(--lift); outline-offset: 2px; }
a { color: var(--paper); text-decoration-color: var(--line-2); text-underline-offset: 3px; }
a:hover { color: var(--lift); }
img { max-width: 100%; }
[id] { scroll-margin-top: 72px; }
.wrap { max-width: var(--max); margin: 0 auto; padding: 0 var(--gut); }
.lbl { font: 500 11px/1.5 var(--mono); letter-spacing: .09em; text-transform: uppercase; color: var(--muted); }
.lbl a { color: inherit; text-decoration: none; }
.lbl a:hover { color: var(--paper); }
.d1 { font: 300 clamp(60px, 9.5vw, 128px)/.9 var(--display); letter-spacing: -.015em; color: var(--paper); margin: 0; }
.d2 { font: 300 clamp(46px, 6vw, 80px)/.95 var(--display); letter-spacing: -.01em; color: var(--paper); margin: 0; }
.d3 { font: 400 clamp(24px, 2.4vw, 32px)/1.08 var(--display); color: var(--paper); margin: 0; }
.muted { color: var(--muted); }
.sep { color: var(--faint); margin: 0 .5em; }

.btn { display: inline-flex; align-items: center; gap: 8px; height: 36px; padding: 0 15px; border: 1px solid var(--paper);
  background: var(--paper); color: var(--brand); font: 500 13px/1 var(--display); letter-spacing: .06em; text-transform: uppercase;
  text-decoration: none; cursor: pointer; white-space: nowrap; }
.btn:hover { background: #fff; border-color: #fff; color: var(--brand); }
.btn.ghost { background: transparent; color: var(--paper); border-color: var(--line-2); }
.btn.ghost:hover { background: rgba(140,140,255,.1); border-color: var(--lift); color: var(--paper); }
.btn svg { width: 14px; height: 14px; }

.pips { display: inline-flex; gap: 4px; vertical-align: middle; }
.pip { display: inline-grid; place-items: center; width: 20px; height: 20px; border: 1px solid currentColor; font: 500 11px/1 var(--mono); }
.pip.W { color: var(--W); } .pip.U { color: var(--U); } .pip.B { color: var(--B); } .pip.R { color: var(--R); } .pip.G { color: var(--G); }

/* card names in text: hover for a preview, click to enlarge */
.cn { cursor: zoom-in; text-decoration: underline dotted; text-decoration-color: var(--faint); text-underline-offset: 3px; }
.cn:hover { color: var(--paper); text-decoration-color: var(--lift); }
.prose .cn, .why .cn, .step .cn { color: var(--paper); }
.cn.gone, .prose .cn.gone, .why .cn.gone, .step .cn.gone { color: var(--muted); text-decoration: line-through;
  text-decoration-color: color-mix(in srgb, var(--out) 65%, transparent); }
.gone-note { margin: 28px 0 0; }
.gone-note s { text-decoration-color: var(--out); color: var(--muted); }

/* duotone art, full colour on hover */
.duo { position: relative; overflow: hidden; background: var(--brand); isolation: isolate; }
.duo img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; display: block; }
.duo .d { filter: grayscale(1) contrast(1.3) brightness(1.05); mix-blend-mode: luminosity; }
.duo .c { opacity: 0; transition: opacity .6s ease; }
.duo::after { content: ""; position: absolute; inset: 0; z-index: 2; pointer-events: none;
  background: repeating-linear-gradient(0deg, rgba(4,4,40,.3) 0 1px, transparent 1px 3px); }
a:hover .duo .c, .duo.live:hover .c { opacity: 1; }
.rays { position: absolute; inset: 0; width: 100%; height: 100%; color: rgba(214,214,255,.4); pointer-events: none; }

/* sections */
.sec { padding: clamp(64px, 9vw, 120px) 0; border-top: 1px solid var(--line); }
.sec-h { display: flex; align-items: flex-start; gap: 16px; margin-bottom: clamp(28px, 4vw, 48px); flex-wrap: wrap; }
.sec-h .no { font: 500 12px/1 var(--mono); color: var(--lift); margin-top: .9em; letter-spacing: .08em; }
.sec-h .aside { margin-left: auto; align-self: flex-end; max-width: 46ch; color: var(--muted); font-size: 15px; }

/* ---------- front page */
.hero { display: grid; grid-template-columns: minmax(0, 1.08fr) minmax(0, .92fr); gap: clamp(24px, 4vw, 64px); align-items: center;
  padding: clamp(20px, 4vw, 48px) 0 clamp(56px, 8vw, 104px); }
.hero h1 { margin: 18px 0 30px; font-size: clamp(56px, 7.4vw, 108px); }
.hero .actions { display: flex; gap: 8px; flex-wrap: wrap; }
.term { border: 1px solid var(--line-2); background: var(--ink-2); max-width: 540px; margin-top: 40px; }
.term-bar { display: flex; align-items: center; gap: 12px; padding: 7px 12px; background: var(--brand); color: #fff; font: 500 11px/1.4 var(--mono); letter-spacing: .05em; }
.term-bar .dots { display: inline-flex; gap: 5px; } .term-bar .dots i { width: 8px; height: 8px; border-radius: 50%; background: rgba(255,255,255,.45); }
.term-body { padding: 14px 16px 16px; font: 400 13px/1.55 var(--mono); }
.term-body .cmd { color: var(--paper); margin-bottom: 8px; } .term-body .cmd b { color: var(--in); font-weight: 400; margin-right: 8px; }
.term dl { margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 3px 22px; }
.term dt { color: var(--faint); } .term dd { margin: 0; color: var(--text); } .term dd b { color: var(--paper); font-weight: 500; }
.caret { display: inline-block; width: 8px; height: 15px; background: var(--paper); vertical-align: -2px; animation: blink 1.1s steps(1) infinite; margin-top: 8px; }
@keyframes blink { 50% { opacity: 0; } }
.fan { position: relative; aspect-ratio: 1; width: 100%; max-width: 600px; justify-self: center; }
.fan a { position: absolute; left: 50%; top: 50%; width: 40%; margin: -27.9% 0 0 -20%; transform-origin: 50% 165%;
  transform: rotate(var(--r)); transition: transform .4s cubic-bezier(.2,.7,.2,1); }
.fan a:hover, .fan a:focus-visible { transform: rotate(var(--r)) translateY(-9%); z-index: 5; }
.fan img { width: 100%; display: block; border-radius: 4.75% / 3.5%; box-shadow: 0 22px 50px rgba(0,0,10,.6); aspect-ratio: 488/680; background: var(--ink-3); }

.decks { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: clamp(48px, 6vw, 80px) clamp(24px, 3vw, 40px); }
.deckcard { display: flex; flex-direction: column; text-decoration: none; color: var(--text); }
.deckcard h3 { font: 300 clamp(38px, 4.2vw, 56px)/1 var(--display); color: var(--paper); margin: 12px 0 10px; transition: color .2s; }
.deckcard:hover h3 { color: var(--lift); }
.deckcard .cmdr { font-size: 15px; }
.deckcard .dirline { margin-top: 18px; display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap; }
.deckcard .dirline .d { font: 400 20px/1.2 var(--display); color: var(--paper); }
.deckcard p { margin: 8px 0 0; max-width: 56ch; color: var(--muted); font-size: 15px; }
.deckcard .duo { margin-top: 24px; aspect-ratio: 16 / 9; }
.deckcard .row { display: flex; justify-content: space-between; gap: 12px; margin-top: 12px; flex-wrap: wrap; }
.deckcard .row .go { color: var(--paper); }
.deckcard:hover .row .go { color: var(--lift); }

.band { position: relative; background: var(--brand); color: #fff; overflow: hidden; }
.band::before { content: ""; position: absolute; inset: 0; background: repeating-linear-gradient(0deg, rgba(0,0,60,.18) 0 1px, transparent 1px 3px); pointer-events: none; }
.band .wrap { position: relative; display: grid; grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr); gap: 40px; align-items: center; padding-block: clamp(64px, 8vw, 112px); }
.band .d2 { color: #fff; margin: 14px 0 20px; }
.band p { color: rgba(255,255,255,.84); max-width: 44ch; margin: 0 0 28px; }
.band .lbl { color: rgba(255,255,255,.72); }
.band .btn { background: #fff; border-color: #fff; color: var(--brand); }
.strip { display: flex; justify-content: center; align-items: flex-end; padding: 12px 4%; }
.strip figure { margin: 0 -2.6%; width: 21%; transform: rotate(var(--r)) translateY(var(--y)); transition: transform .35s cubic-bezier(.2,.7,.2,1); }
.strip figure:hover { transform: rotate(0deg) translateY(-14px); z-index: 3; }
.strip img { width: 100%; display: block; border-radius: 4.75% / 3.5%; box-shadow: 0 16px 36px rgba(0,0,50,.55); cursor: zoom-in; aspect-ratio: 488/680; background: rgba(0,0,40,.4); }
.strip figcaption { font: 500 10px/1.3 var(--mono); letter-spacing: .06em; text-align: center; color: rgba(255,255,255,.8); margin-top: 10px; }

/* ---------- deck page */
.dhero { position: relative; overflow: hidden; padding-bottom: clamp(40px, 6vw, 72px); }
.dhero-bg { position: absolute; inset: 0; opacity: .2; -webkit-mask-image: linear-gradient(to bottom, #000 20%, transparent 92%); mask-image: linear-gradient(to bottom, #000 20%, transparent 92%); }
.dhero-bg .duo { position: absolute; inset: 0; }
.dhero-in { position: relative; display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, .8fr); gap: clamp(24px, 5vw, 72px); align-items: center; padding-top: clamp(16px, 4vw, 48px); }
.dhero h1 { margin: 16px 0 20px; }
.cmdr { display: flex; align-items: center; gap: 12px; color: var(--paper); flex-wrap: wrap; }
.dhero .cmdr { font-size: 18px; }
.dir { margin-top: 34px; padding-left: 18px; border-left: 2px solid var(--brand); }
.dir .d3 { margin-top: 6px; }
.dir .plus { color: var(--lift); }
.dir p { margin: 8px 0 0; color: var(--muted); max-width: 52ch; }
.dhero .actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 34px; }
.dhero-card { position: relative; width: 100%; max-width: 440px; justify-self: center; aspect-ratio: 1; display: grid; place-items: center; }
.dhero-card .rays { inset: -8%; width: 116%; height: 116%; }
.dhero-card img { position: relative; width: 66%; border-radius: 4.75% / 3.5%; box-shadow: 0 30px 70px rgba(0,0,10,.65); cursor: zoom-in; aspect-ratio: 488/680; background: var(--ink-3); }
.stats { position: relative; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin: clamp(40px, 6vw, 64px) 0 0; border: 1px solid var(--line-2); background: rgba(10,10,28,.7); }
.stats > div { padding: 16px 18px 18px; border-right: 1px solid var(--line); }
.stats > div:last-child { border-right: 0; }
.stats dt { font: 500 10.5px/1.4 var(--mono); letter-spacing: .09em; text-transform: uppercase; color: var(--muted); }
.stats dd { margin: 6px 0 0; font: 300 clamp(30px, 3.4vw, 44px)/1 var(--display); color: var(--paper); }
.stats dd small { font: 400 13px var(--mono); color: var(--faint); margin-left: 6px; letter-spacing: 0; }
.bnote { position: relative; margin: 12px 0 0; font: 400 12px/1.6 var(--mono); color: var(--faint); }
.bnote b { color: var(--muted); font-weight: 500; }

.secnav { position: sticky; top: 0; z-index: 30; background: rgba(10,10,28,.86); -webkit-backdrop-filter: blur(12px); backdrop-filter: blur(12px); border-bottom: 1px solid var(--line); }
.secnav .wrap { display: flex; align-items: center; gap: 28px; height: 52px; overflow-x: auto; scrollbar-width: none; }
.secnav .wrap::-webkit-scrollbar { display: none; }
.secnav a { font: 500 11px/1 var(--mono); letter-spacing: .1em; text-transform: uppercase; color: var(--muted); text-decoration: none; white-space: nowrap; }
.secnav a .n { color: var(--faint); margin-right: 8px; }
.secnav a:hover, .secnav a.on { color: var(--paper); }
.secnav a.on .n { color: var(--lift); }
.secnav .title { font: 400 15px/1 var(--display); letter-spacing: .04em; color: var(--paper); text-transform: uppercase; margin-right: 8px; white-space: nowrap; }
.secnav .sp { flex: 1; }
.secnav .btn { height: 30px; font-size: 12px; }

.plan-intro { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 24px clamp(24px, 5vw, 72px); align-items: start; }
.lead { font: 300 clamp(26px, 2.8vw, 36px)/1.22 var(--display); color: var(--paper); margin: 0; }
.prose { margin: 0; max-width: 64ch; }
.steps { list-style: none; margin: clamp(40px, 6vw, 64px) 0 0; padding: 0; border-top: 1px solid var(--line-2); }
.step { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 2fr); gap: 14px clamp(24px, 5vw, 72px); padding: 30px 0; border-bottom: 1px solid var(--line); }
.step h3 { font: 400 clamp(24px, 2.4vw, 30px)/1.1 var(--display); color: var(--paper); margin: 8px 0 0; }
.step ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; }
.step li { position: relative; padding-left: 24px; max-width: 72ch; }
.step li::before { content: ""; position: absolute; left: 3px; top: .66em; width: 6px; height: 6px; background: var(--lift); }
.step.b3 li::before { background: var(--gc); }
.review { border: 1px solid var(--line-2); padding: 28px; display: flex; gap: 24px; align-items: center; justify-content: space-between; flex-wrap: wrap; }

.og-sum { align-items: center; margin: 0 0 clamp(28px, 4vw, 44px); }
.og-sum .lbl { color: var(--paper); margin-right: 8px; }
.ogroup { margin-top: clamp(36px, 5vw, 56px); }
.og-h { display: flex; justify-content: space-between; gap: 16px; margin: 0; padding-bottom: 10px; border-bottom: 1px solid var(--line-2);
  font: 500 11px/1.4 var(--mono); letter-spacing: .09em; text-transform: uppercase; color: var(--muted); }
.og-h span:last-child { color: var(--faint); }
.ogroup.planned .og-h { color: var(--plan); border-bottom-color: color-mix(in srgb, var(--plan) 50%, transparent); }
.swap { display: grid; grid-template-columns: 40px 232px minmax(0, 1fr); gap: 24px; padding: 28px 0; border-bottom: 1px solid var(--line); }
.swap .no { font: 500 12px/1 var(--mono); color: var(--faint); padding-top: 9px; }
.pair { display: grid; grid-template-columns: 86px 22px 124px; align-items: end; align-self: start; }
.thumb { margin: 0; position: relative; }
.thumb img, .thumb .noimg { width: 100%; display: block; border-radius: 4.75% / 3.5%; aspect-ratio: 488/680; background: var(--ink-3); cursor: zoom-in; }
.thumb.out img { filter: grayscale(1) brightness(.55); transition: filter .25s; }
.thumb.out:hover img { filter: none; }
.thumb figcaption { font: 500 9.5px/1 var(--mono); letter-spacing: .12em; text-transform: uppercase; margin-top: 8px; }
.thumb.out figcaption { color: var(--out); }
.thumb.in figcaption { color: var(--in); }
.pair .arr { align-self: center; text-align: center; color: var(--faint); font: 400 14px var(--mono); }
.noimg { display: grid !important; place-items: center; padding: 8px; text-align: center; font: 500 11px/1.3 var(--mono); color: var(--muted); border: 1px dashed var(--line-2); }
.swap .in-name { font: 400 clamp(24px, 2.4vw, 30px)/1.1 var(--display); color: var(--paper); margin: 0; }
.swap .in-name .sig { font: 400 .62em var(--mono); color: var(--in); margin-right: 10px; vertical-align: .12em; }
.swap .out-name { margin-top: 6px; font-size: 14px; color: var(--muted); }
.swap .out-name .sig { font: 400 12px var(--mono); color: var(--out); margin-right: 8px; }
.swap .out-name .cn { text-decoration: line-through; text-decoration-color: color-mix(in srgb, var(--out) 70%, transparent); }
.swap .why { margin: 14px 0 0; max-width: 68ch; }
.swap.is-planned .thumb.in img { outline: 1px dashed var(--plan); outline-offset: 3px; }
.tags { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 14px; }
.tag { display: inline-flex; align-items: center; font: 500 10px/1 var(--mono); letter-spacing: .09em; text-transform: uppercase; padding: 6px 8px;
  border: 1px solid var(--line-2); color: var(--muted); text-decoration: none; }
.tag.gc { color: var(--gc); border-color: color-mix(in srgb, var(--gc) 40%, transparent); }
.tag.plan { color: var(--plan); border-color: color-mix(in srgb, var(--plan) 45%, transparent); }
.tag.own { color: var(--in); border-color: color-mix(in srgb, var(--in) 40%, transparent); }
.tag.src { color: var(--lift); border-color: color-mix(in srgb, var(--lift) 45%, transparent); }
a.tag:hover { color: var(--paper); border-color: var(--paper); }

/* history: git log */
.log { list-style: none; margin: 0; padding: 0 0 0 22px; border-left: 1px solid var(--line-2); max-width: 980px; }
.commit { position: relative; padding: 0 0 30px; }
.commit::before { content: ""; position: absolute; left: -27px; top: 5px; width: 9px; height: 9px; background: var(--ink); border: 1px solid var(--lift); }
.commit.planned::before { border-color: var(--plan); border-style: dashed; }
.commit.root::before { background: var(--lift); }
.commit.root { padding-bottom: 0; }
.c-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 14px; font: 400 12px/1.5 var(--mono); }
.c-head .hash { color: var(--gc); }
.commit.planned .c-head .hash { color: var(--plan); }
.c-head .c-date { color: var(--faint); }
.c-head .c-msg { font: 400 18px/1.3 var(--display); color: var(--paper); letter-spacing: .01em; }
.c-head .c-meta { color: var(--faint); margin-left: auto; }
.c-diff { list-style: none; margin: 10px 0 0; padding: 10px 14px; background: var(--ink-2); border: 1px solid var(--line); font: 400 13px/1.75 var(--mono); }
.c-diff li { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 0 24px; }
.c-diff i { font-style: normal; margin-right: 10px; }
.c-diff .add { color: var(--text); } .c-diff .add i { color: var(--in); }
.c-diff .del { color: var(--muted); } .c-diff .del i { color: var(--out); }
.c-diff .cn { text-decoration-color: transparent; }
.c-diff .cn:hover { text-decoration-color: var(--lift); }
.c-diff .cn.gone { text-decoration: none; color: inherit; }
.c-diff li.plan .add { color: var(--plan); }

.tools { display: flex; gap: 12px 18px; align-items: center; flex-wrap: wrap; margin-bottom: 32px; }
.tools .sp { flex: 1; }
.legend { display: flex; gap: 16px; flex-wrap: wrap; }
.legend .new { color: var(--in); } .legend .cut { color: var(--plan); }
.seg { display: inline-flex; border: 1px solid var(--line-2); }
.seg button { font: 500 11px/1 var(--mono); letter-spacing: .09em; text-transform: uppercase; padding: 10px 13px; background: none; color: var(--muted); border: 0; cursor: pointer; }
.seg button + button { border-left: 1px solid var(--line-2); }
.seg button:hover { color: var(--paper); }
.seg button[aria-pressed="true"] { background: var(--paper); color: var(--brand); }
.dlist { columns: 3 250px; column-gap: 44px; }
.dgroup { break-inside: avoid; margin: 0 0 30px; }
.dgroup h4, .cgroup h4 { display: flex; justify-content: space-between; margin: 0 0 8px; padding-bottom: 8px; border-bottom: 1px solid var(--line-2);
  font: 500 11px/1.4 var(--mono); letter-spacing: .09em; text-transform: uppercase; color: var(--muted); }
.dgroup h4 span:last-child, .cgroup h4 span:last-child { color: var(--faint); }
.dgroup ul { list-style: none; margin: 0; padding: 0; }
.dgroup li { display: grid; grid-template-columns: 24px minmax(0, 1fr) auto; gap: 6px; padding: 3px 0; font-size: 14.5px; line-height: 1.45; }
.dgroup li .q { font: 400 12px/1.7 var(--mono); color: var(--faint); }
.dgroup li .cn { text-decoration-color: transparent; }
.dgroup li .cn:hover { text-decoration-color: var(--lift); }
.dgroup li.new .cn { color: var(--paper); }
.mk { font: 500 10.5px/1.8 var(--mono); letter-spacing: .06em; }
.mk.new { color: var(--in); } .mk.cut { color: var(--plan); text-transform: uppercase; }
.dl[data-view="list"] .dcards, .dl[data-view="cards"] .dlist { display: none; }
.cgroup { margin-bottom: 36px; }
.cgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 16px 14px; padding-top: 8px; }
.tile { margin: 0; position: relative; }
.tile img, .tile .noimg { width: 100%; display: block; border-radius: 4.75% / 3.5%; aspect-ratio: 488/680; background: var(--ink-3); cursor: zoom-in; }
.tile.new img { outline: 2px solid var(--in); outline-offset: 3px; }
.tile.cut img { outline: 2px dashed var(--plan); outline-offset: 3px; }
.tile .qty { position: absolute; top: 8px; right: 8px; background: rgba(6,6,20,.85); color: var(--paper); font: 500 11px/1 var(--mono); padding: 5px 7px; }
.tile figcaption { display: flex; justify-content: space-between; gap: 8px; margin-top: 8px; font: 400 12px/1.35 var(--body); color: var(--muted); }
.tile figcaption span:first-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tile figcaption .p { font: 400 11px/1.5 var(--mono); color: var(--faint); white-space: nowrap; }

/* ---------- bulk list */
.ihero { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 32px; align-items: end; padding: clamp(20px, 4vw, 48px) 0 clamp(32px, 5vw, 56px); }
.ihero h1 { margin: 16px 0 18px; }
.ihero p { margin: 0; max-width: 52ch; color: var(--muted); }
.ihero .stats { margin: 0; grid-template-columns: repeat(3, minmax(120px, 1fr)); }
.filters { display: grid; gap: 14px; padding: 22px 0; border-top: 1px solid var(--line); }
.search { display: flex; align-items: center; gap: 12px; border: 1px solid var(--line-2); background: var(--ink-2); padding: 0 16px; height: 52px; }
.search:focus-within { border-color: var(--lift); }
.search span { font: 500 15px var(--mono); color: var(--lift); }
.search input { flex: 1; min-width: 0; background: none; border: 0; color: var(--paper); font: 400 15px var(--mono); outline: none; }
.search input::placeholder { color: var(--faint); }
.chips { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.chips .lbl { margin-right: 6px; min-width: 76px; }
.chip { font: 500 11px/1 var(--mono); letter-spacing: .08em; text-transform: uppercase; padding: 8px 10px; border: 1px solid var(--line-2); background: none; color: var(--muted); cursor: pointer; }
.chip:hover { color: var(--paper); border-color: var(--lift); }
.chip[aria-pressed="true"] { background: var(--paper); color: var(--brand); border-color: var(--paper); }
.chip .c { opacity: .6; margin-left: 6px; }
.select { font: 500 11px/1 var(--mono); letter-spacing: .08em; text-transform: uppercase; padding: 8px 10px; border: 1px solid var(--line-2); background: var(--ink); color: var(--muted); }
.result { display: flex; align-items: center; gap: 16px; justify-content: space-between; flex-wrap: wrap; padding: 6px 0 18px; }
.result .count b { color: var(--paper); font-weight: 500; }
.table-scroll { overflow-x: auto; }
table.inv { width: 100%; border-collapse: collapse; font-size: 14.5px; }
table.inv th { font: 500 10.5px/1.4 var(--mono); letter-spacing: .09em; text-transform: uppercase; color: var(--muted); text-align: left; padding: 12px 10px;
  border-bottom: 1px solid var(--line-2); position: sticky; top: 0; background: var(--ink); cursor: pointer; user-select: none; white-space: nowrap; z-index: 2; }
table.inv th:hover { color: var(--paper); }
table.inv th[aria-sort="ascending"]::after { content: " ↑"; color: var(--lift); }
table.inv th[aria-sort="descending"]::after { content: " ↓"; color: var(--lift); }
table.inv td { padding: 9px 10px; border-bottom: 1px solid var(--line); vertical-align: baseline; }
table.inv tbody tr { cursor: zoom-in; }
table.inv tbody tr:hover td { background: rgba(140,140,255,.07); }
table.inv .num { text-align: right; font: 400 13px var(--mono); white-space: nowrap; }
table.inv td.q { color: var(--faint); }
table.inv .nm { color: var(--paper); }
table.inv .set { font: 400 10.5px var(--mono); color: var(--faint); margin-left: 10px; letter-spacing: .05em; }
table.inv .loc-loose { color: var(--muted); }
.one-place table.inv .where { display: none; }
.src { font: 500 10px/1 var(--mono); letter-spacing: .08em; text-transform: uppercase; color: var(--faint); white-space: nowrap; }
.src.shop { color: var(--in); } .src.tobuy { color: var(--plan); }
.inv-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 18px 14px; }
.empty { padding: 48px 0; text-align: center; color: var(--muted); font: 400 13px var(--mono); }

/* ---------- lightbox, preview, footer */
#lightbox { position: fixed; inset: 0; z-index: 100; display: none; flex-direction: column; align-items: center; justify-content: center; gap: 20px;
  padding: 24px; background: rgba(5,5,18,.88); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); cursor: zoom-out; }
#lightbox.open { display: flex; }
.lb-cards { display: flex; gap: 16px; justify-content: center; max-width: 100%; }
.lb-cards img { max-height: min(78vh, 680px); max-width: min(44vw, 488px); border-radius: 4.75% / 3.5%; box-shadow: 0 30px 80px rgba(0,0,0,.6); }
.lb-cards img:only-child { max-width: 92vw; }
.lb-cap { display: flex; gap: 18px; align-items: center; flex-wrap: wrap; justify-content: center; font: 500 11px/1.4 var(--mono); letter-spacing: .09em; text-transform: uppercase; color: var(--muted); }
.lb-cap .n { color: var(--paper); }
.lb-cap a { color: var(--lift); text-decoration: none; cursor: pointer; }
#preview { position: fixed; left: 0; top: 0; width: 244px; aspect-ratio: 488/680; border-radius: 4.75% / 3.5%; z-index: 80; pointer-events: none;
  opacity: 0; transition: opacity .12s; box-shadow: 0 20px 50px rgba(0,0,0,.6); background: var(--ink-3); }
#preview.on { opacity: 1; }
.foot { border-top: 1px solid var(--line); margin-top: clamp(40px, 6vw, 80px); padding-top: 48px; overflow: hidden; }
.foot-cols { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 32px; }
.foot-cols a { display: block; color: var(--text); text-decoration: none; font-size: 14px; padding: 3px 0; }
.foot-cols a:hover { color: var(--lift); }
.foot-cols p { margin: 6px 0; font-size: 14px; color: var(--muted); max-width: 40ch; }
.foot-cols .lbl { margin-bottom: 10px; color: var(--faint); }
.foot-mark { font: 300 clamp(80px, 17vw, 236px)/.8 var(--display); letter-spacing: -.02em; color: transparent; -webkit-text-stroke: 1px rgba(176,176,255,.3);
  margin: 56px 0 0; padding-bottom: 8px; white-space: nowrap; user-select: none; }

@media (max-width: 900px) {
  .hero, .dhero-in, .band .wrap, .plan-intro, .ihero { grid-template-columns: minmax(0, 1fr); }
  .fan { max-width: 440px; }
  .decks { grid-template-columns: minmax(0, 1fr); }
  .dhero-card { max-width: 320px; }
  .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .stats > div:nth-child(2) { border-right: 0; }
  .stats > div:nth-child(-n+2) { border-bottom: 1px solid var(--line); }
  .ihero .stats { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .ihero .stats > div { border-bottom: 0; border-right: 1px solid var(--line); }
  .ihero .stats > div:last-child { border-right: 0; }
  .step { grid-template-columns: minmax(0, 1fr); }
  .swap { grid-template-columns: minmax(0, 1fr); gap: 16px; }
  .swap .no { padding: 0; }
  .sec-h .aside { margin-left: 0; }
  .strip figure { width: 26%; }
  .c-diff li { grid-template-columns: minmax(0, 1fr); }
  .c-head .c-meta { margin-left: 0; }
  .foot-cols { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 600px) {
  body::after { border-width: 2px; }
  .secnav .title { display: none; }
  .secnav .wrap { gap: 20px; }
  .secnav .btn { padding: 0 9px; }
  .secnav .btn .t { display: none; }
  .secnav .btn.done svg { display: none; }
  .secnav .btn.done::before { content: "✓"; color: var(--in); }
  .pair { grid-template-columns: 96px 26px 140px; }
  table.inv .hide-s { display: none; }
  .ihero .stats { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .ihero .stats > div { padding: 12px; }
  .chips .lbl { min-width: 0; width: 100%; }
  .cgrid, .inv-cards { grid-template-columns: repeat(auto-fill, minmax(104px, 1fr)); }
  .strip figure:nth-child(n+5) { display: none; }
  .strip figure { width: 30%; }
}
"""

JS = r"""
(() => {
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const data = $("#cards");
  const C = window.CARDS = Object.assign(window.CARDS || {}, data ? JSON.parse(data.textContent) : {});
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // Lightbox: click any card (image, name or table row) for the large scan, both faces for DFCs
  const lb = $("#lightbox"), pv = $("#preview");
  const hidePv = () => { if (pv) pv.classList.remove("on"); };
  const close = () => { lb.classList.remove("open"); lb.innerHTML = ""; };
  const open = k => {
    const c = C[k];
    if (!c || !c.l || !c.l.length) return false;
    lb.innerHTML = `<div class="lb-cards">${c.l.map(u => `<img src="${esc(u)}" alt="${esc(c.n)}">`).join("")}</div>
      <div class="lb-cap"><span class="n">${esc(c.n)}</span>${c.e != null ? `<span>€${c.e.toFixed(2)}</span>` : ""}
      ${c.u ? `<a href="${esc(c.u)}" target="_blank" rel="noopener">Scryfall ↗</a>` : ""}<span>Esc to close</span></div>`;
    lb.classList.add("open"); hidePv(); return true;
  };
  document.addEventListener("click", e => {
    if (lb.classList.contains("open")) { if (!e.target.closest(".lb-cap a")) close(); return; }
    const el = e.target.closest("[data-k]");
    if (!el) return;
    const link = e.target.closest("a[href]");
    if (link && !link.hasAttribute("data-k")) return;
    if (open(el.dataset.k)) e.preventDefault();
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") return close();
    if ((e.key === "Enter" || e.key === " ") && e.target.matches("[data-k][tabindex]")) { e.preventDefault(); open(e.target.dataset.k); }
  });

  // Hover preview for card names and table rows (mouse only)
  if (pv && matchMedia("(hover: hover) and (pointer: fine)").matches) {
    let cur = null;
    document.addEventListener("mousemove", e => {
      const el = lb.classList.contains("open") ? null : e.target.closest(".cn[data-k], tr[data-k]");
      const c = el && C[el.dataset.k];
      if (!c || !c.i) { hidePv(); cur = null; return; }
      if (cur !== el.dataset.k) { pv.src = c.i; cur = el.dataset.k; }
      const w = 244, h = 340;
      let x = e.clientX + 24, y = e.clientY - h / 2;
      if (x + w > innerWidth - 16) x = e.clientX - w - 24;
      y = Math.max(16, Math.min(y, innerHeight - h - 16));
      pv.style.transform = `translate(${x}px, ${y}px)`;
      pv.classList.add("on");
    }, { passive: true });
    document.addEventListener("scroll", hidePv, { passive: true });
  }

  // Copy buttons: data-copy names a <textarea>
  document.addEventListener("click", async e => {
    const b = e.target.closest("[data-copy]");
    if (!b) return;
    const ta = document.getElementById(b.dataset.copy);
    try { await navigator.clipboard.writeText(ta.value); }
    catch { ta.hidden = false; ta.select(); document.execCommand("copy"); ta.hidden = true; }
    const t = b.querySelector(".t") || b, old = t.textContent;
    t.textContent = "Copied ✓"; b.classList.add("done");
    setTimeout(() => { t.textContent = old; b.classList.remove("done"); }, 1600);
  });

  // List / cards toggles: data-views names the element whose data-view changes
  $$("[data-views]").forEach(g => {
    const target = document.getElementById(g.dataset.views), store = "view:" + g.dataset.views;
    const set = v => {
      $$("button", g).forEach(x => x.setAttribute("aria-pressed", String(x.dataset.v === v)));
      target.dataset.view = v; target.dispatchEvent(new CustomEvent("view"));
    };
    g.addEventListener("click", e => {
      const b = e.target.closest("button[data-v]");
      if (!b) return;
      set(b.dataset.v);
      try { localStorage.setItem(store, b.dataset.v); } catch {}
    });
    let saved = null;
    try { saved = localStorage.getItem(store); } catch {}
    if (saved && g.querySelector(`button[data-v="${saved}"]`)) set(saved);
  });

  // Section nav: highlight the section in view
  const links = $$(".secnav a[href^='#']");
  if (links.length && "IntersectionObserver" in window) {
    const byId = new Map(links.map(a => [a.getAttribute("href").slice(1), a]));
    const io = new IntersectionObserver(es => es.forEach(en => {
      if (en.isIntersecting) links.forEach(a => a.classList.toggle("on", a === byId.get(en.target.id)));
    }), { rootMargin: "-40% 0px -55% 0px" });
    byId.forEach((a, id) => { const s = document.getElementById(id); if (s) io.observe(s); });
  }
})();
"""

COPY_ICON = ('<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">'
             '<rect x="5" y="5" width="8.5" height="8.5"/><path d="M3 10.5V2.5h8"/></svg>')


# ---------------------------------------------------------------- helpers

class Cards:
    """Card lookups for one page; records every card the page shows so the
    page can carry its images (hover preview, lightbox) as one JSON map."""

    def __init__(self, index):
        self.index, self.used = index, {}

    def info(self, name):
        return self.index.get(key(name)) or {}

    def ref(self, name):
        k = key(name)
        if k not in self.used:
            info = self.info(name)
            imgs = info.get("images") or []
            self.used[k] = {"n": info.get("name") or name, "i": imgs[0].get("normal") if imgs else "",
                            "l": [i.get("large") or i.get("normal") for i in imgs],
                            "u": info.get("scryfall_uri") or "", "e": info.get("eur")}
        return k

    def img(self, name, lazy=True, zoom=True):
        """<img> for a card. zoom=False leaves out data-k (no lightbox), for an image inside a link."""
        k = self.ref(name)
        src = self.used[k]["i"]
        dk = f' data-k="{E(k)}"' if zoom else ""
        if not src:
            return f'<div class="noimg"{dk}>{E(name)}</div>'
        load = ' loading="lazy"' if lazy else ""
        return f'<img src="{E(src)}" alt="{E(name)}"{dk}{load} decoding="async">'

    def name(self, name, label=None):
        k = self.ref(name)
        return f'<span class="cn" data-k="{E(k)}" tabindex="0" role="button">{E(label or name)}</span>'

    def art(self, name):
        imgs = self.info(name).get("images") or [{}]
        return imgs[0].get("art_crop") or imgs[0].get("normal") or ""

    def json(self):
        return json.dumps(self.used, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")


class Linker:
    """Wrap card names that appear in a piece of text in hoverable spans."""

    def __init__(self, cards, names, present=None):
        self.cards, forms, short = cards, {}, Counter()
        self.present, self.gone = present, set()   # keys in the deck now; names found that aren't
        for n in dict.fromkeys(names):
            for full in [n, *(n.split(" // ") if " // " in n else [])]:
                if len(full) >= 4 and full not in BASICS:
                    forms.setdefault(full, n)
                if ", " in full and len(full.split(", ")[0]) >= 4:
                    short[full.split(", ")[0]] += 1
        for s, count in short.items():      # "Hearthhull" for "Hearthhull, the Worldseed", unless ambiguous
            if count == 1:
                forms.setdefault(s, next(n for n in names if n.startswith(s + ", ")))
        self.forms = forms
        pats = sorted(forms, key=len, reverse=True)
        self.rx = re.compile(r"(?<!\w)(" + "|".join(re.escape(E(p, quote=False)) for p in pats) + r")(?!\w)") if pats else None

    def __call__(self, text):
        t = E(text or "", quote=False)
        if not self.rx:
            return t

        def sub(m):
            k = self.cards.ref(self.forms[html.unescape(m.group(1))])
            if self.present is not None and k not in self.present:
                self.gone.add(k)
                return (f'<span class="cn gone" data-k="{E(k)}" tabindex="0" role="button" '
                        f'title="No longer in the deck">{m.group(1)}</span>')
            return f'<span class="cn" data-k="{E(k)}" tabindex="0" role="button">{m.group(1)}</span>'
        return self.rx.sub(sub, t)


def deck_meta(path):
    """Title and '- **Key:** value' bullets from a deck file header."""
    lines = path.read_text().splitlines()
    title = lines[0].lstrip("# ").strip()
    meta = {}
    for line in lines:
        if line.startswith("## "):
            break
        m = re.match(r"- \*\*(.+?):\*\*\s*(.*)", line)
        if m:
            meta[m.group(1)] = m.group(2)
    return title, meta


def colours(identity_text):
    cols = [COLOUR_NAMES[w] for w in re.findall(r"White|Blue|Black|Red|Green", identity_text or "")]
    return sorted(cols, key=COLOUR_ORDER.index)


def pips(identity_text):
    return ('<span class="pips">' + "".join(f'<span class="pip {c}" title="{c}">{c}</span>' for c in colours(identity_text))
            + "</span>")


def guild(identity_text):
    m = re.search(r"\(([^)]+)\)", identity_text or "")
    return m.group(1) if m else " / ".join(colours(identity_text)) or "Colourless"


def product_short(product):
    return re.sub(r"\s*Commander precon.*|,? released.*", "", product or "").strip() or "Precon"


def bracket(meta):
    m = re.match(r"\s*(\d)\s*(?:\((.*)\))?", meta.get("Bracket", ""))
    return (m.group(1), (m.group(2) or "").strip()) if m else ("—", "")


def money(v, digits=2):
    return "—" if v is None else f"€{v:.{digits}f}"


def rays(n=132):
    """Engraving-style sunburst (deterministic, no randomness)."""
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n
        r1 = 0.33 + 0.07 * ((i * 37) % 7) / 6
        r2 = 0.62 + 0.36 * ((i * 53) % 11) / 10
        out.append(f'<line x1="{r1 * math.cos(a):.4f}" y1="{r1 * math.sin(a):.4f}" '
                   f'x2="{r2 * math.cos(a):.4f}" y2="{r2 * math.sin(a):.4f}"/>')
    return ('<svg class="rays" viewBox="-1 -1 2 2" aria-hidden="true"><g stroke="currentColor" stroke-width=".0032" '
            f'stroke-linecap="round">{"".join(out)}</g><circle r=".3" fill="none" stroke="currentColor" stroke-width=".003"/>'
            '<circle r=".985" fill="none" stroke="currentColor" stroke-width=".0025" stroke-dasharray=".006 .018"/></svg>')


def duo(src, live=False):
    if not src:
        return '<div class="duo"></div>'
    return (f'<div class="duo{" live" if live else ""}"><img class="d" src="{E(src)}" alt="" loading="lazy" decoding="async">'
            f'<img class="c" src="{E(src)}" alt="" loading="lazy" decoding="async"></div>')


def header(decks, base, current):
    def link(d):
        cur = ' class="cur" aria-current="page"' if current == d["slug"] else ""
        return f'<a href="{base}decks/{d["slug"]}.html"{cur}>{E(d["title"])}</a>'
    links = [link(d) for d in decks]
    half = (len(links) + 1) // 2
    bulk_cur = ' aria-current="page"' if current == "inventory" else ""
    return f"""<header class="top">
<nav class="nav-l" aria-label="Decks">{"".join(links[:half])}</nav>
<a class="mark" href="{base}index.html">MTG<br>Decks</a>
<nav class="nav-r" aria-label="Decks and bulk list">{"".join(links[half:])}<a class="btn-w" href="{base}inventory.html"{bulk_cur}>Bulk list</a></nav>
<nav class="nav-m" aria-label="Site">{"".join(links)}<a href="{base}inventory.html"{' class="cur"' if current == "inventory" else ""}>Bulk list</a></nav>
</header>"""


def footer(decks, base):
    deck_links = "".join(f'<a href="{base}decks/{d["slug"]}.html">{E(d["title"])}</a>' for d in decks)
    return f"""<footer class="foot"><div class="wrap">
<div class="foot-cols">
  <div><div class="lbl">Decks</div>{deck_links}</div>
  <div><div class="lbl">Collection</div><a href="{base}inventory.html">Bulk list</a><a href="{base}inventory.html?deck=all">Every card owned</a></div>
  <div><div class="lbl">Data</div><p>Card images and prices from <a style="display:inline" href="https://scryfall.com" target="_blank" rel="noopener">Scryfall</a>, cheapest paper printing, as of {E(PRICES_AS_OF) or "?"}.</p>
    <a href="{REPO}" target="_blank" rel="noopener">Source on GitHub ↗</a></div>
</div>
<div class="foot-mark" aria-hidden="true">MTG Decks</div>
</div></footer>"""


def page(title, body, base, decks, current, description="", cards=None, script=""):
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(description)}">
<meta name="theme-color" content="#0a0a1c">
<link rel="icon" href="{FAVICON}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<link rel="stylesheet" href="{base}assets/site.css">
</head><body>
{header(decks, base, current)}
<main>{body}</main>
{footer(decks, base)}
<div id="lightbox" role="dialog" aria-modal="true" aria-label="Card image"></div>
<img id="preview" alt="" aria-hidden="true">
<script id="cards" type="application/json">{cards.json() if cards else "{}"}</script>
<script src="{base}assets/site.js"></script>{script}
</body></html>
"""


# ---------------------------------------------------------------- upgrades

def picked_direction(spec):
    return next((d for d in (spec or {}).get("directions") or [] if d.get("picked")), None)


def upgrade_phases(spec):
    """What was chosen for a deck, in the order it went in: core package, the
    picked direction, later changes, and the bracket 3 package unless it was
    declined. Changes dated after the package was applied come after it, the
    same order verify_comparison.py replays them in. Empty until a direction
    is picked."""
    picked = picked_direction(spec)
    if not picked:
        return []
    phases = []
    core = spec.get("core") or {}
    if core.get("swaps"):
        phases.append({"key": "core", "kicker": "Goes in every direction", "name": core.get("name") or "Core package",
                       "date": spec.get("date"), "text": core.get("description") or "",
                       "swaps": [dict(s) for s in core["swaps"]]})
    phases.append({"key": "direction", "kicker": "Chosen direction", "name": picked["name"], "date": spec.get("date"),
                   "text": picked.get("plays_like") or "",
                   "swaps": [dict(s, planned=bool(s.get("pending"))) for s in picked.get("swaps") or []]})
    b3 = spec.get("bracket3") or {}
    b3_date = b3.get("applied") if b3.get("swaps") and not b3.get("declined") else None
    changes = spec.get("deck_changes") or []

    def changes_phase(key_, cs):
        dates = sorted({c["date"] for c in cs if c.get("date")})
        span = (dates[0] if len(dates) == 1 else f"{dates[0]} → {dates[-1]}") if dates else None
        return {"key": key_, "kicker": "After playing it", "name": "Later changes", "date": span,
                "text": "", "swaps": [dict(c) for c in cs]}

    early = [c for c in changes if not b3_date or (c.get("date") or "") <= b3_date]
    late = [c for c in changes if b3_date and (c.get("date") or "") > b3_date]
    if early:
        phases.append(changes_phase("later", early))
    if b3.get("swaps") and not b3.get("declined"):
        planned = not b3.get("applied")
        phases.append({"key": "bracket3", "kicker": "Planned · not in the deck yet" if planned else "Power level",
                       "name": b3.get("name") or "Bracket 3 package", "date": b3.get("applied"), "planned": planned,
                       "text": b3.get("description") or "", "swaps": [dict(s, planned=planned) for s in b3["swaps"]]})
    if late:
        phases.append(changes_phase("review", late))
    return phases


def tag_rows(phases):
    """Every recorded swap, in order, tagged with where and when it came from."""
    rows = []
    for ph in phases:
        for s in ph["swaps"]:
            rows.append(dict(s, source=None if ph["key"] in ("later", "review") else ph["name"],
                             when=s.get("date") if ph["key"] in ("later", "review") else ph.get("date")))
    return rows


def net_swaps(rows, pre_c):
    """The deck as it is now against the precon, as one-for-one pairs.

    Follows each slot through the swaps (A -> B, later B -> C is one slot
    A -> C), and when a precon card comes back, joins the slot it came back
    into with the slot it left (X -> Juri, Juri -> Azusa is X -> Azusa).
    Swaps that were undone drop out. Each pair keeps the swap that brought its
    current card in (`via`), whose `why` is the reason that card is in the deck.
    """
    slots, holder = [], {}
    for s in rows:
        if s.get("planned"):
            continue
        o, i = key(s["out"]), key(s["in"])
        if holder.get(o):
            slot = holder[o].pop()
        else:
            slots.append({"orig": s["out"], "chain": []})
            slot = slots[-1]
        slot["cur"] = s["in"]
        slot["chain"].append(s)
        holder.setdefault(i, []).append(slot)
    live = list(slots)
    joined = True
    while joined:
        joined = False
        for a in live:
            b = next((b for b in live if b is not a and key(b["orig"]) == key(a["cur"]) and key(a["cur"]) in pre_c), None)
            if b:
                a["cur"], a["chain"] = b["cur"], a["chain"] + b["chain"]
                live.remove(b)
                joined = True
                break
    pairs = [x for x in live if key(x["orig"]) != key(x["cur"])]
    for p in pairs:
        p["via"] = next(s for s in reversed(p["chain"]) if key(s["in"]) == key(p["cur"]))
    return pairs


def swap_html(no, cur, orig, via, cards, link, net_of=1):
    """One card in the deck now (or planned), next to the precon card whose slot it took."""
    tags = []
    if via.get("planned"):
        tags.append('<span class="tag plan">Planned</span>')
    if via.get("source"):
        tags.append(f'<span class="tag src">{E(via["source"])}</span>')
    if via.get("when"):
        tags.append(f'<span class="tag">{E(via["when"])}</span>')
    if via.get("owned"):
        tags.append('<span class="tag own">Already owned</span>')
    if cards.info(cur).get("game_changer"):
        tags.append('<span class="tag gc">Game Changer</span>')
    if net_of > 1:
        tags.append(f'<a class="tag" href="#history">Net of {net_of} swaps</a>')
    return f"""<article class="swap{" is-planned" if via.get("planned") else ""}" id="swap-{no}">
  <div class="no">#{no:02d}</div>
  <div class="pair">
    <figure class="thumb out">{cards.img(orig)}<figcaption>Out</figcaption></figure>
    <span class="arr" aria-hidden="true">→</span>
    <figure class="thumb in">{cards.img(cur)}<figcaption>In</figcaption></figure>
  </div>
  <div class="txt">
    <h4 class="in-name"><span class="sig">+</span>{cards.name(cur)}</h4>
    <div class="out-name"><span class="sig">−</span>replaces {cards.name(orig)}</div>
    {f'<p class="why">{link(via["why"])}</p>' if via.get("why") else ""}
    {f'<div class="tags">{"".join(tags)}</div>' if tags else ""}
  </div>
</article>"""


PLAN_CLS = ' class="plan"'


def history_html(phases, meta, cards):
    """Git-log style record, newest first: one entry per package or date of
    changes, as + / − lines, down to the stock precon."""
    entries = []
    for ph in phases:
        if ph["key"] in ("later", "review"):
            for date in sorted({s.get("date") or "" for s in ph["swaps"]}):
                entries.append({"date": date, "msg": "Deck changes", "swaps": [s for s in ph["swaps"] if (s.get("date") or "") == date]})
        else:
            entries.append({"date": ph.get("date") or "", "msg": ph["name"], "swaps": ph["swaps"],
                            "planned": ph.get("planned"), "cost": True})
    # newest first; on the same date the later entry first (the direction went in after its core package)
    order = {id(e): i for i, e in enumerate(entries)}
    entries.sort(key=lambda e: (bool(e.get("planned")), e["date"], order[id(e)]), reverse=True)

    def sha(e):
        raw = e["date"] + e["msg"] + "".join(s["in"] + s["out"] for s in e["swaps"])
        return hashlib.sha1(raw.encode()).hexdigest()[:7]

    items = []
    for e in entries:
        n = len(e["swaps"])
        cost = sum(cards.info(s["in"]).get("eur") or 0 for s in e["swaps"] if not s.get("owned"))
        meta_bits = [f"{n} swap{'s' if n != 1 else ''}"] + ([f"≈ {money(cost)}"] if e.get("cost") else [])
        lines = "".join(
            f'<li{PLAN_CLS if s.get("planned") else ""}><span class="add"><i>+</i>{cards.name(s["in"])}</span>'
            f'<span class="del"><i>−</i>{cards.name(s["out"])}</span></li>' for s in e["swaps"])
        items.append(f"""<li class="commit{" planned" if e.get("planned") else ""}">
  <div class="c-head"><span class="hash">{"planned" if e.get("planned") else sha(e)}</span><span class="c-date">{E(e["date"] or "—")}</span>
    <span class="c-msg">{E(e["msg"])}</span><span class="c-meta">{" · ".join(meta_bits)}</span></div>
  <ul class="c-diff">{lines}</ul>
</li>""")
    released = re.search(r"released (\d{4}-\d{2}-\d{2})", meta.get("Product", ""))
    items.append(f"""<li class="commit root">
  <div class="c-head"><span class="hash">precon</span><span class="c-date">{E(released.group(1) if released else "—")}</span>
    <span class="c-msg">{E(product_short(meta.get("Product")))} precon, stock list</span><span class="c-meta">100 cards</span></div>
</li>""")
    return f'<ol class="log">{"".join(items)}</ol>'


# ---------------------------------------------------------------- deck page

def build_deck(d, index):
    """Deck page: how to play, the swaps that make the deck what it is now,
    the decklist, and the history of every swap."""
    cards = Cards(index)
    commanders, current = parse_deck(d["path"])
    precon_path = ROOT / "decks" / "precon" / d["path"].name
    pre_cmd, pre = parse_deck(precon_path) if precon_path.exists() else (commanders, current)
    cur_c, pre_c = Counter(), Counter()
    for q, n in current:
        cur_c[key(n)] += q
    for q, n in pre:
        pre_c[key(n)] += q
    names = {key(n): n for _, n in pre + current}
    spec = d["spec"]
    picked = picked_direction(spec)
    phases = upgrade_phases(spec)
    b3 = (spec or {}).get("bracket3") or {}
    meta = d["meta"]

    # The deck now against the precon, as pairs; the full record goes to History
    rows = tag_rows(phases)
    pairs = net_swaps(rows, pre_c)
    planned = [s for s in rows if s.get("planned")]
    plan_cut = Counter(key(s["out"]) for s in planned)

    present = set(cur_c) | {key(c) for c in commanders} | {key(s["in"]) for s in planned}
    linker = Linker(cards, commanders + [n for _, n in current + pre] + [n for s in rows for n in (s["in"], s["out"])],
                    present)

    added_total = sum(max(0, q - pre_c.get(k, 0)) for k, q in cur_c.items())
    total = len(commanders) + sum(cur_c.values())
    value = sum((cards.info(names[k]).get("eur") or 0) * q for k, q in cur_c.items()) + \
        sum(cards.info(c).get("eur") or 0 for c in commanders)
    gcs = [names[k] for k in cur_c if cards.info(names[k]).get("game_changer")]
    br, br_note = bracket(meta)
    cmd = commanders[0] if commanders else d["title"]
    art = cards.art(cmd)

    # ---- hero
    direction = ""
    if picked:
        extra = ' <span class="plus">+ Bracket 3</span>' if b3.get("applied") else ""
        direction = (f'<div class="dir"><div class="lbl">Chosen direction</div><div class="d3">{E(picked["name"])}{extra}</div>'
                     f'<p>{E(picked.get("plays_like") or "")}</p></div>')
    elif spec:
        direction = '<div class="dir"><div class="lbl">Upgrade</div><div class="d3">Options under review</div></div>'
    swaps_btn = '<a class="btn" href="#swaps">See the swaps</a>' if pairs or planned else '<a class="btn" href="#decklist">Decklist</a>'
    note_bits = [f"<b>Bracket {E(br)}</b> — {E(br_note)}" if br_note else f"<b>Bracket {E(br)}</b>",
                 f"Game Changers: {E(', '.join(gcs))}" if gcs else "No Game Changers"]
    hero = f"""<section class="dhero">
  <div class="dhero-bg" aria-hidden="true">{duo(art)}</div>
  <div class="wrap dhero-in">
    <div>
      <div class="lbl"><a href="../index.html">Decks</a><span class="sep">/</span>#{d["no"]:02d}<span class="sep">/</span>{E(guild(meta.get("Colour identity")))}<span class="sep">·</span>{E(product_short(meta.get("Product")))} precon</div>
      <h1 class="d1">{E(d["title"])}</h1>
      <div class="cmdr">{pips(meta.get("Colour identity"))}<span>{" &amp; ".join(cards.name(c) for c in commanders)}</span></div>
      {direction}
      <div class="actions">{swaps_btn}<button class="btn ghost" type="button" data-copy="decklist-text">{COPY_ICON}<span class="t">Copy decklist</span></button></div>
    </div>
    <div class="dhero-card">{rays()}{cards.img(cmd, lazy=False)}</div>
  </div>
  <div class="wrap">
    <dl class="stats">
      <div><dt>Cards</dt><dd>{total}</dd></div>
      <div><dt>New since precon</dt><dd>{added_total}{f"<small>+{len(planned)} planned</small>" if planned else ""}</dd></div>
      <div><dt>Bracket</dt><dd>{E(br)}</dd></div>
      <div><dt>Value</dt><dd>≈ €{value:.0f}</dd></div>
    </dl>
    <p class="bnote">{" · ".join(note_bits)}</p>
  </div>
</section>"""

    # ---- section nav
    secs = []
    if spec:
        secs.append(("plan", "How to play"))
    if pairs or planned:
        secs.append(("swaps", "Swaps"))
    secs.append(("decklist", "Decklist"))
    if rows:
        secs.append(("history", "History"))
    secnav = (f'<nav class="secnav" aria-label="On this page"><div class="wrap"><span class="title">{E(d["title"])}</span>'
              + "".join(f'<a href="#{i}"><span class="n">{n:02d}</span>{E(t)}</a>' for n, (i, t) in enumerate(secs, 1))
              + f'<span class="sp"></span><button class="btn ghost" type="button" data-copy="decklist-text">{COPY_ICON}'
              '<span class="t">Copy decklist</span></button></div></nav>')
    num = {i: n for n, (i, _) in enumerate(secs, 1)}

    # ---- the plan
    plan = ""
    if picked:
        htp = picked.get("how_to_play") or {}
        lead_html = linker(htp.get("summary") or picked.get("plays_like") or "")
        pitch_html = linker(picked.get("pitch") or "")
        steps = [(sec.get("title", ""), sec.get("points") or [], "") for sec in htp.get("sections") or []]
        if b3.get("applied"):
            tips = [n for n in b3.get("notes") or [] if not n.startswith("Changed on")]
            if tips:
                steps.append(("Bracket 3 notes", tips, " b3"))
        steps_html = "".join(
            f'<li class="step{cls}"><div><div class="lbl">#{i:02d}</div><h3>{E(t)}</h3></div>'
            f'<ul>{"".join(f"<li>{linker(p)}</li>" for p in pts)}</ul></li>'
            for i, (t, pts, cls) in enumerate(steps, 1))
        gone_note = ('<p class="lbl gone-note">Names in <s>strikethrough</s> have left the deck since this guide was '
                     'written; see the swaps below for what replaced them.</p>') if linker.gone else ""
        plan = f"""<section class="sec" id="plan"><div class="wrap">
  <div class="sec-h"><span class="no">{num["plan"]:02d}</span><h2 class="d2">How to play</h2></div>
  <div class="plan-intro">
    <p class="lead">{lead_html}</p>
    <p class="prose">{pitch_html}</p>
  </div>
  {f'<ol class="steps">{steps_html}</ol>' if steps_html else ""}
  {gone_note}
</div></section>"""
    elif spec:
        plan = f"""<section class="sec" id="plan"><div class="wrap">
  <div class="sec-h"><span class="no">{num["plan"]:02d}</span><h2 class="d2">How to play</h2></div>
  <div class="review"><div><div class="lbl">Upgrade options under review</div>
    <p class="prose" style="margin-top:8px">{E(spec.get("summary") or "")}</p></div>
    <a class="btn" href="../comparisons/{d["slug"]}.html">Compare the directions</a></div>
</div></section>"""

    # ---- swaps: the deck as it is now, against the precon
    swaps = ""
    if pairs or planned:
        def type_of(name):
            return section_for(cards.info(name).get("type_line", ""))

        def order(name):
            info = cards.info(name)
            return ("Basic" in info.get("type_line", ""), info.get("cmc", 0), name)

        blocks, no = [], 0
        for sec in SECTIONS + ["Other"]:
            group = sorted((p for p in pairs if type_of(p["cur"]) == sec), key=lambda p: order(p["cur"]))
            if not group:
                continue
            items = []
            for p in group:
                no += 1
                items.append(swap_html(no, p["cur"], p["orig"], p["via"], cards, linker, len(p["chain"])))
            blocks.append(f'<div class="ogroup"><h3 class="og-h"><span>{E(sec)}</span><span>{len(group)}</span></h3>'
                          f'{"".join(items)}</div>')
        if planned:
            items = []
            for s in planned:
                no += 1
                items.append(swap_html(no, s["in"], s["out"], s, cards, linker))
            cost = sum(cards.info(s["in"]).get("eur") or 0 for s in planned if not s.get("owned"))
            blocks.append(f'<div class="ogroup planned"><h3 class="og-h"><span>Planned · not in the deck yet</span>'
                          f'<span>{len(planned)} · ≈ {money(cost)} to buy</span></h3>{"".join(items)}</div>')
        by_source = Counter(p["via"].get("source") or "Deck changes" for p in pairs)
        order_src = [ph["name"] for ph in phases if ph["key"] not in ("later", "review")] + ["Deck changes"]
        chips = "".join(f'<span class="tag{" src" if src != "Deck changes" else ""}">{E(src)} · {by_source[src]}</span>'
                        for src in order_src if by_source.get(src))
        swaps = f"""<section class="sec" id="swaps"><div class="wrap">
  <div class="sec-h"><span class="no">{num["swaps"]:02d}</span><h2 class="d2">Swaps</h2>
    <p class="aside">The deck as it is now: each card that wasn't in the {E(product_short(meta.get("Product")))} precon, the precon card it replaced, and why it's in. Swaps that were later undone are only in the history.</p></div>
  <div class="tags og-sum"><span class="lbl">{len(pairs)} cards differ from the precon</span>{chips}</div>
  {"".join(blocks)}
</div></section>"""

    # ---- decklist
    groups = {}
    for k, q in cur_c.items():
        info = cards.info(names[k])
        groups.setdefault(section_for(info.get("type_line", "")), []).append(
            (names[k], q, max(0, q - pre_c.get(k, 0)), info))
    ordered = [("Commander", [(c, 1, 0 if key(c) in {key(x) for x in pre_cmd} else 1, cards.info(c)) for c in commanders])]
    for sec in SECTIONS + ["Other"]:
        if groups.get(sec):
            items = sorted(groups[sec], key=lambda x: ("Basic" in x[3].get("type_line", ""), x[3].get("cmc", 0), x[0]))
            ordered.append((sec, items))

    def marker(name, q, added):
        if plan_cut.get(key(name)):
            return '<span class="mk cut" title="Planned cut">out</span>'
        if added:
            return f'<span class="mk new" title="New since the precon">+{added if q > 1 else ""}</span>'
        return ""

    lists, grids = [], []
    for sec, items in ordered:
        n = sum(q for _, q, _, _ in items)
        lis = "".join(f'<li class="{"new" if a else ""}"><span class="q">{q}</span>{cards.name(nm)}{marker(nm, q, a)}</li>'
                      for nm, q, a, _ in items)
        lists.append(f'<div class="dgroup"><h4><span>{E(sec)}</span><span>{n}</span></h4><ul>{lis}</ul></div>')
        tiles = "".join(
            f'<figure class="tile{" cut" if plan_cut.get(key(nm)) else " new" if a else ""}">{cards.img(nm)}'
            f'{f"<span class=qty>×{q}</span>" if q > 1 else ""}'
            f'<figcaption><span>{E(nm)}</span><span class="p">{money(info.get("eur"))}</span></figcaption></figure>'
            for nm, q, a, info in items)
        grids.append(f'<div class="cgroup"><h4><span>{E(sec)}</span><span>{n}</span></h4><div class="cgrid">{tiles}</div></div>')
    decklist_text = "\n".join([*(f"1 {c}" for c in commanders), *(f"{q} {n}" for q, n in current)])
    legend = '<span class="lbl legend"><span class="new">+ new since the precon</span>' + \
        ('<span class="cut">out · planned cut</span>' if planned else "") + "</span>"
    decklist = f"""<section class="sec" id="decklist"><div class="wrap">
  <div class="sec-h"><span class="no">{num["decklist"]:02d}</span><h2 class="d2">Decklist</h2>
    <p class="aside">The deck as it is now: {total} cards, ready to paste into Moxfield or Archidekt.</p></div>
  <div class="tools">
    <div class="seg" data-views="dl" role="group" aria-label="View"><button type="button" data-v="list" aria-pressed="true">List</button><button type="button" data-v="cards" aria-pressed="false">Cards</button></div>
    {legend}
  </div>
  <div class="dl" id="dl" data-view="list">
    <div class="dlist">{"".join(lists)}</div>
    <div class="dcards">{"".join(grids)}</div>
  </div>
  <textarea id="decklist-text" hidden>{E(decklist_text)}</textarea>
</div></section>"""

    history = ""
    if rows:
        history = f"""<section class="sec" id="history"><div class="wrap">
  <div class="sec-h"><span class="no">{num["history"]:02d}</span><h2 class="d2">History</h2>
    <p class="aside">Every swap since the precon, newest first, including ones that were later undone.</p></div>
  {history_html(phases, meta, cards)}
</div></section>"""

    body = hero + secnav + plan + swaps + decklist + history
    stats = {"total": total, "added": added_total, "value": value, "planned": len(planned), "swaps": len(pairs),
             "bracket": br, "art": art, "picked": picked, "b3_applied": bool(b3.get("applied"))}
    return body, cards, stats


# ---------------------------------------------------------------- bulk list

def build_inventory(index, decks):
    """The bulk list from inventory.csv: every owned card, loose ones first."""
    cards = Cards(index)
    rows = list(csv.DictReader((ROOT / "inventory.csv").open()))
    data, totals = [], Counter()
    for r in rows:
        info = cards.info(r["Name"])
        q = int(r["Count"])
        loc = r["Deck"] or "Loose"
        totals[loc] += q
        data.append({"q": q, "n": r["Name"], "k": cards.ref(r["Name"]), "d": loc, "s": r["Source"],
                     "set": r.get("Set", ""), "a": r.get("Acquired", ""), "no": r.get("Notes", ""),
                     "t": section_for(info.get("type_line", "")), "e": info.get("eur")})
    value = sum((x["e"] or 0) * x["q"] for x in data)
    loose = [x for x in data if x["d"] == "Loose"]
    loose_value = sum((x["e"] or 0) * x["q"] for x in loose)
    deck_order = [d["title"] for d in decks]
    locs = [("Loose", "Loose", totals.get("Loose", 0))] + \
        [(t, t, totals[t]) for t in deck_order if totals.get(t)] + \
        [(t, t, n) for t, n in sorted(totals.items()) if t != "Loose" and t not in deck_order] + \
        [("all", "Everything", sum(totals.values()))]
    loc_chips = "".join(f'<button class="chip" type="button" data-loc="{E(v)}" aria-pressed="false">{E(lab)}<span class="c">{n}</span></button>'
                        for v, lab, n in locs)
    types = [s for s in SECTIONS + ["Other"] if any(x["t"] == s for x in data)]
    type_chips = '<button class="chip" type="button" data-type="" aria-pressed="true">All</button>' + \
        "".join(f'<button class="chip" type="button" data-type="{E(t)}" aria-pressed="false">{E(t)}</button>' for t in types)
    src_opts = "".join(f'<option value="{E(s)}">{E(s)}</option>' for s in sorted({x["s"] for x in data}))
    body = f"""<div class="wrap">
<section class="ihero">
  <div>
    <div class="lbl">Collection<span class="sep">/</span>{sum(totals.values())} cards owned<span class="sep">·</span>≈ €{value:.0f}</div>
    <h1 class="d1">Bulk list</h1>
    <p>Every card that isn't in a deck, searchable, with the cheapest paper price. Switch to a deck or to everything with the chips below; click a card to see it.</p>
  </div>
  <dl class="stats">
    <div><dt>Loose</dt><dd>{totals.get("Loose", 0)}</dd></div>
    <div><dt>In decks</dt><dd>{sum(n for t, n in totals.items() if t != "Loose")}</dd></div>
    <div><dt>Loose value</dt><dd>€{loose_value:.0f}</dd></div>
  </dl>
</section>
<section class="filters" aria-label="Filters">
  <label class="search"><span aria-hidden="true">›</span><input id="q" type="search" placeholder="search cards, sets, notes…" aria-label="Search" autocomplete="off" spellcheck="false"></label>
  <div class="chips" id="locs"><span class="lbl">Where</span>{loc_chips}</div>
  <div class="chips" id="types"><span class="lbl">Type</span>{type_chips}
    <select class="select" id="src" aria-label="Source"><option value="">Any source</option>{src_opts}</select></div>
</section>
<div class="result">
  <span class="lbl count" id="count"></span>
  <div class="seg" data-views="inv" role="group" aria-label="View"><button type="button" data-v="list" aria-pressed="true">List</button><button type="button" data-v="cards" aria-pressed="false">Cards</button></div>
</div>
<div id="inv" data-view="list">
  <div class="table-scroll" id="inv-list"><table class="inv">
    <thead><tr><th class="num" data-s="q">Qty</th><th data-s="n">Card</th><th class="hide-s" data-s="t">Type</th><th class="where" data-s="d">Where</th>
    <th class="hide-s" data-s="s">Source</th><th class="num" data-s="e">Price</th></tr></thead>
    <tbody id="rows"></tbody>
  </table></div>
  <div class="inv-cards" id="inv-cards" hidden></div>
  <div class="empty" id="empty" hidden>No cards match.</div>
</div>
</div>"""
    script = """
<script>
(() => {
  const DATA = %s;
  const C = window.CARDS, $ = s => document.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
  const eur = v => v == null ? "—" : "€" + v.toFixed(2);
  const params = new URLSearchParams(location.search);
  const st = { loc: params.get("deck") || "Loose", type: "", src: "", q: "", sort: "e", dir: -1 };
  if (!document.querySelector(`#locs [data-loc="${CSS.escape(st.loc)}"]`)) st.loc = "Loose";
  const view = $("#inv");
  function rows() {
    const q = st.q.toLowerCase();
    return DATA.filter(r => (st.loc === "all" || r.d === st.loc) && (!st.type || r.t === st.type) && (!st.src || r.s === st.src)
        && (!q || `${r.n} ${r.set} ${r.no} ${r.d} ${r.s}`.toLowerCase().includes(q)))
      .sort((a, b) => {
        const x = a[st.sort] ?? (st.sort === "e" ? -1 : ""), y = b[st.sort] ?? (st.sort === "e" ? -1 : "");
        return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y))) * st.dir || a.n.localeCompare(b.n);
      });
  }
  function srcCls(s) { return s === "To buy" ? "tobuy" : /precon|bulk/i.test(s) ? "" : "shop"; }
  function render() {
    const rs = rows(), cards = view.dataset.view === "cards";
    view.classList.toggle("one-place", st.loc !== "all");
    $("#inv-list").hidden = cards; $("#inv-cards").hidden = !cards; $("#empty").hidden = rs.length > 0;
    if (cards) {
      $("#inv-cards").innerHTML = rs.map(r => { const c = C[r.k] || {};
        return `<figure class="tile">${c.i ? `<img src="${esc(c.i)}" alt="${esc(r.n)}" data-k="${esc(r.k)}" loading="lazy" decoding="async">` : `<div class="noimg" data-k="${esc(r.k)}">${esc(r.n)}</div>`}
          ${r.q > 1 ? `<span class="qty">×${r.q}</span>` : ""}<figcaption><span title="${esc(r.n)}">${esc(r.n)}</span><span class="p">${eur(r.e)}</span></figcaption></figure>`; }).join("");
    } else {
      $("#rows").innerHTML = rs.map(r => `<tr data-k="${esc(r.k)}"${r.no ? ` title="${esc(r.no)}"` : ""}>
        <td class="num q">${r.q}</td><td><span class="nm">${esc(r.n)}</span><span class="set">${esc(r.set)}</span></td>
        <td class="hide-s muted">${esc(r.t)}</td><td class="where${r.d === "Loose" ? " loc-loose" : ""}">${esc(r.d)}</td>
        <td class="hide-s"><span class="src ${srcCls(r.s)}">${esc(r.s)}</span></td><td class="num">${eur(r.e)}</td></tr>`).join("");
      document.querySelectorAll("table.inv th").forEach(th => th.setAttribute("aria-sort", th.dataset.s === st.sort ? (st.dir > 0 ? "ascending" : "descending") : "none"));
    }
    const n = rs.reduce((s, r) => s + r.q, 0), v = rs.reduce((s, r) => s + (r.e || 0) * r.q, 0);
    $("#count").innerHTML = `<b>${n}</b> card${n === 1 ? "" : "s"} · ≈ <b>€${v.toFixed(0)}</b>`;
  }
  const press = (sel, attr, val) => document.querySelectorAll(sel).forEach(b => b.setAttribute("aria-pressed", String(b.dataset[attr] === val)));
  $("#locs").addEventListener("click", e => { const b = e.target.closest("[data-loc]"); if (!b) return; st.loc = b.dataset.loc; press("#locs .chip", "loc", st.loc); render();
    const u = new URL(location.href); st.loc === "Loose" ? u.searchParams.delete("deck") : u.searchParams.set("deck", st.loc); history.replaceState(null, "", u); });
  $("#types").addEventListener("click", e => { const b = e.target.closest("[data-type]"); if (!b) return; st.type = b.dataset.type; press("#types .chip", "type", st.type); render(); });
  $("#src").addEventListener("change", e => { st.src = e.target.value; render(); });
  $("#q").addEventListener("input", e => { st.q = e.target.value; render(); });
  document.querySelectorAll("table.inv th").forEach(th => th.addEventListener("click", () => {
    st.dir = st.sort === th.dataset.s ? -st.dir : (th.dataset.s === "e" || th.dataset.s === "q" ? -1 : 1); st.sort = th.dataset.s; render(); }));
  view.addEventListener("view", render);
  press("#locs .chip", "loc", st.loc);
  render();
})();
</script>""" % json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    top_loose = sorted({x["k"]: x for x in loose if x["e"]}.values(), key=lambda x: (-x["e"], x["n"]))[:6]
    stats = {"total": sum(totals.values()), "loose": totals.get("Loose", 0), "loose_value": loose_value,
             "value": value, "top_loose": top_loose}
    return body, cards, script, stats


# ---------------------------------------------------------------- front page

def build_index(decks, inv, index):
    cards = Cards(index)
    n = len(decks)
    word = NUMBER_WORDS[n] if n < len(NUMBER_WORDS) else str(n)
    fan = "".join(
        f'<a href="decks/{d["slug"]}.html" style="--r:{(i - (n - 1) / 2) * 15:.1f}deg" aria-label="{E(d["title"])}">'
        f'{cards.img(d["commanders"][0] if d["commanders"] else d["title"], lazy=False, zoom=False)}</a>'
        for i, d in enumerate(decks))
    in_decks = sum(d["stats"]["total"] for d in decks)
    added = sum(d["stats"]["added"] for d in decks)
    guilds = Counter(guild(d["meta"].get("Colour identity")) for d in decks)
    guild_txt = " · ".join(f"{g}{f' ×{c}' if c > 1 else ''}" for g, c in sorted(guilds.items()))
    hero = f"""<div class="wrap"><section class="hero">
  <div>
    <div class="lbl">Commander<span class="sep">/</span>{n} decks<span class="sep">·</span>{inv["total"]} cards owned</div>
    <h1 class="d1">{word} Precon{"s" if n != 1 else ""}<br>Rebuilt Card<br>By Card</h1>
    <div class="actions"><a class="btn" href="#decks">Browse the decks</a><a class="btn ghost" href="inventory.html">Bulk list</a></div>
    <div class="term" aria-label="Collection summary">
      <div class="term-bar"><span class="dots"><i></i><i></i><i></i></span><span>~/collection — status</span></div>
      <div class="term-body">
        <div class="cmd"><b>~ %</b>collection status</div>
        <dl>
          <dt>decks</dt><dd><b>{n}</b> · {E(guild_txt)}</dd>
          <dt>cards</dt><dd><b>{in_decks}</b> in decks · <b>{inv["total"]}</b> owned</dd>
          <dt>upgrades</dt><dd><b>{added}</b> new cards since the precons</dd>
          <dt>bulk</dt><dd><b>{inv["loose"]}</b> loose · ≈ €{inv["loose_value"]:.0f}</dd>
          <dt>prices</dt><dd>scryfall · {E(PRICES_AS_OF or "?")}</dd>
        </dl>
        <span class="caret" aria-hidden="true"></span>
      </div>
    </div>
  </div>
  <div class="fan">{rays()}{fan}</div>
</section></div>"""
    tiles = []
    for d in decks:
        s, m = d["stats"], d["meta"]
        p = s["picked"]
        dir_name = (p["name"] + (" + Bracket 3" if s["b3_applied"] else "")) if p else ("Options under review" if d["spec"] else "Stock")
        summary = ((p.get("how_to_play") or {}).get("summary") or p.get("plays_like") or "") if p else ""
        tiles.append(f"""<a class="deckcard" href="decks/{d["slug"]}.html">
  <div class="lbl">#{d["no"]:02d}<span class="sep">·</span>{E(guild(m.get("Colour identity")))}<span class="sep">·</span>Bracket {E(s["bracket"])}</div>
  <h3>{E(d["title"])}</h3>
  <div class="cmdr">{pips(m.get("Colour identity"))}<span>{E(", ".join(d["commanders"]))}</span></div>
  <div class="dirline"><span class="lbl">Direction</span><span class="d">{E(dir_name)}</span></div>
  {f"<p>{E(summary)}</p>" if summary else ""}
  {duo(s["art"])}
  <div class="row lbl"><span>{s["swaps"]} swaps<span class="sep">·</span>{s["added"]} new cards<span class="sep">·</span>≈ €{s["value"]:.0f}</span><span class="go">Open deck →</span></div>
</a>""")
    strip = "".join(
        f'<figure style="--r:{(i - 2.5) * 5:.1f}deg;--y:{abs(i - 2.5) * 9:.0f}px">{cards.img(x["n"])}<figcaption>{E(money(x["e"]))}</figcaption></figure>'
        for i, x in enumerate(inv["top_loose"]))
    body = hero + f"""
<section class="sec" id="decks"><div class="wrap">
  <div class="sec-h"><h2 class="d2">Decks</h2><span class="no">[{n:02d}]</span>
    <p class="aside">Each deck started as a precon. Open one for how to play it, every swap with its reason, and the list as it is now.</p></div>
  <div class="decks">{"".join(tiles)}</div>
</div></section>
<section class="band"><div class="wrap">
  <div>
    <div class="lbl">Collection<span class="sep">/</span>Not in a deck</div>
    <h2 class="d2">Bulk list</h2>
    <p>{inv["loose"]} loose cards, worth about €{inv["loose_value"]:.0f} together: cuts from the precons and singles waiting for a deck. Search them by name, type or set.</p>
    <a class="btn" href="inventory.html">Open the bulk list</a>
  </div>
  <div class="strip" aria-label="Most valuable loose cards">{strip}</div>
</div></section>"""
    return body, cards


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="_site")
    ap.add_argument("--cname", default="mtg.grontved.xyz")
    ap.add_argument("--max-age-days", type=float, default=7,
                    help="re-download Scryfall bulk data older than this (default 7)")
    args = ap.parse_args()
    out = ROOT / args.out
    if out.exists():
        shutil.rmtree(out)
    (out / "decks").mkdir(parents=True)
    (out / "assets").mkdir()
    (out / "assets" / "site.css").write_text(TOKENS + NAV_CSS + CSS)
    (out / "assets" / "site.js").write_text(JS.lstrip())
    if args.cname:
        (out / "CNAME").write_text(args.cname + "\n")
    (out / ".nojekyll").write_text("")

    loaded = load_index(refresh=False, max_age_days=args.max_age_days)
    global PRICES_AS_OF
    PRICES_AS_OF = (loaded.get("bulk_updated") or "")[:10]
    index = loaded["cards"]
    decks = []
    for i, path in enumerate(sorted((ROOT / "decks").glob("*.md")), 1):
        title, meta = deck_meta(path)
        spec_path = ROOT / "comparisons" / f"{path.stem}-upgrades.json"
        decks.append({"no": i, "slug": path.stem, "path": path, "title": title, "meta": meta,
                      "spec_path": spec_path if spec_path.exists() else None,
                      "spec": json.loads(spec_path.read_text()) if spec_path.exists() else None,
                      "commanders": parse_deck(path)[0]})

    needed = []
    for d in decks:
        cmdr, dcards = parse_deck(d["path"])
        precon = ROOT / "decks" / "precon" / d["path"].name
        needed += cmdr + [n for _, n in dcards] + ([n for _, n in parse_deck(precon)[1]] if precon.exists() else [])
        for ph in upgrade_phases(d["spec"]):
            needed += [n for s in ph["swaps"] for n in (s["in"], s["out"])]
    gaps = fetch_cards(needed, index)
    if gaps:
        print(f"warning: {len(gaps)} card(s) not on Scryfall: {', '.join(gaps[:5])}", file=sys.stderr)

    for d in decks:
        body, cards, d["stats"] = build_deck(d, index)
        (out / "decks" / f"{d['slug']}.html").write_text(
            page(f"{d['title']} — MTG Decks", body, "../", decks, d["slug"],
                 f"{d['title']}: the plan, every swap from the precon with the reason, and the decklist", cards))
        if d["spec"] and not picked_direction(d["spec"]):
            # nothing picked yet: publish the comparison so a direction can be chosen
            target = out / "comparisons" / f"{d['slug']}.html"
            target.parent.mkdir(exist_ok=True)
            subprocess.run([sys.executable, "-B", str(ROOT / "tools" / "build_comparison.py"),
                            str(d["spec_path"]), "-o", str(target)], check=True, stdout=subprocess.DEVNULL)
            nav_html = f"<style>{NAV_CSS}</style>" + header(decks, "../", d["slug"])
            target.write_text(target.read_text().replace("<!--SITE_NAV-->", nav_html, 1))

    inv_body, inv_cards, inv_script, inv = build_inventory(index, decks)
    (out / "inventory.html").write_text(page("Bulk list — MTG Decks", inv_body, "", decks, "inventory",
                                             "Every MTG card I own that isn't in a deck, plus the deck cards",
                                             inv_cards, inv_script))

    body, cards = build_index(decks, inv, index)
    (out / "index.html").write_text(page("MTG Decks", body, "", decks, "home",
                                         "Commander decks rebuilt from precons: the plan and every swap, explained", cards))
    try:
        shown = out.relative_to(ROOT)
    except ValueError:          # --out outside the repo
        shown = out
    undecided = sum(1 for d in decks if d["spec"] and not picked_direction(d["spec"]))
    print(f"built {shown}: index + bulk list + {len(decks)} decks"
          + (f" + {undecided} comparison(s) awaiting a pick" if undecided else ""))


if __name__ == "__main__":
    main()
