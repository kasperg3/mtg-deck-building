#!/usr/bin/env python3
"""Build the static website (GitHub Pages) from the repo.

Usage:
    python3 tools/build_site.py [--out _site] [--cname mtg.grontved.xyz]

Pages:
    index.html                     front page: every deck with its commander,
                                   colours, bracket and upgrade status
    decks/<deck>.html              the full, current decklist with card images;
                                   cards added since the precon are marked
                                   "Added", and cut precon cards are listed
    comparisons/<deck>.html        the upgrade comparison (rebuilt here, so
                                   prices are current)

Card data comes from the local Scryfall index (.cache/card-index.json),
downloaded automatically when missing or older than a week. CI runs this on
every push to main (see .github/workflows/pages.yml).
"""

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from apply_direction import SECTIONS, section_for  # noqa: E402
from build_comparison import key, load_index, parse_deck  # noqa: E402

E = html.escape
COLOUR_ORDER = "WUBRG"
COLOUR_NAMES = {"White": "W", "Blue": "U", "Black": "B", "Red": "R", "Green": "G"}

CSS = r"""
:root {
  --bg: #f6f5f2; --surface: #ffffff; --surface-2: #efede8; --text: #1d1c1a; --muted: #6b6862;
  --border: #dcd8d0; --accent: #4f46e5; --in: #15803d; --in-bg: #dcfce7; --out: #b91c1c; --out-bg: #fee2e2;
  --W: #f3ecd2; --U: #3b82c4; --B: #3d3a36; --R: #d1453b; --G: #3f8f4f;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #141413; --surface: #1e1d1b; --surface-2: #2a2926; --text: #ecebe7; --muted: #a29f97;
    --border: #3a3834; --accent: #8b85ff; --in: #4ade80; --in-bg: #14321f; --out: #f87171; --out-bg: #3b1717;
  }
}
:root[data-theme="dark"] {
  --bg: #141413; --surface: #1e1d1b; --surface-2: #2a2926; --text: #ecebe7; --muted: #a29f97;
  --border: #3a3834; --accent: #8b85ff; --in: #4ade80; --in-bg: #14321f; --out: #f87171; --out-bg: #3b1717;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
a { color: var(--accent); }
.wrap { max-width: 1180px; margin: 0 auto; padding: 24px 16px 80px; }
h1 { font-size: 30px; margin: 0 0 6px; }
h2 { font-size: 20px; margin: 36px 0 12px; }
.muted { color: var(--muted); }
.small { font-size: 13px; }
.pill { display: inline-block; font-size: 12px; padding: 2px 9px; border-radius: 999px; background: var(--surface-2); }
.pips { display: inline-flex; gap: 4px; vertical-align: middle; }
.pip { width: 16px; height: 16px; border-radius: 50%; border: 1px solid rgba(0,0,0,.25); display: inline-block; }
.pip.W { background: var(--W); } .pip.U { background: var(--U); } .pip.B { background: var(--B); }
.pip.R { background: var(--R); } .pip.G { background: var(--G); }

/* front page */
.hero { padding: 8px 0 18px; }
.decks { display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); gap: 18px; }
.deck { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; display: flex; flex-direction: column; }
.deck .art { height: 190px; background: var(--surface-2) center 18% / cover no-repeat; }
.deck .body { padding: 14px 16px 16px; display: flex; flex-direction: column; gap: 8px; flex: 1; }
.deck h2 { margin: 0; font-size: 21px; }
.deck .facts { display: grid; grid-template-columns: auto 1fr; gap: 2px 12px; font-size: 13px; }
.deck .facts dt { color: var(--muted); }
.deck .facts dd { margin: 0; }
.deck .links { display: flex; gap: 8px; margin-top: auto; padding-top: 8px; flex-wrap: wrap; }
.btn { display: inline-block; padding: 7px 14px; border-radius: 8px; background: var(--accent); color: #fff; text-decoration: none; font-weight: 600; font-size: 14px; }
.btn.secondary { background: var(--surface-2); color: var(--text); }
.stats { display: flex; gap: 22px; flex-wrap: wrap; margin-top: 30px; }
.stat b { display: block; font-size: 22px; }

/* deck page */
.deckhead { display: flex; gap: 22px; align-items: flex-start; }
.deckhead img { width: 220px; border-radius: 4.75% / 3.5%; flex: none; cursor: zoom-in; }
.deckhead .facts { display: grid; grid-template-columns: auto 1fr; gap: 3px 14px; font-size: 14px; margin: 10px 0; }
.deckhead .facts dt { color: var(--muted); }
.deckhead .facts dd { margin: 0; }
.toolbar { position: sticky; top: 0; z-index: 5; background: var(--bg); padding: 10px 0; border-bottom: 1px solid var(--border);
  display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-top: 20px; }
.toolbar button { font: inherit; font-size: 13px; padding: 5px 12px; border-radius: 999px; border: 1px solid var(--border);
  background: var(--surface); color: var(--text); cursor: pointer; }
.toolbar button[aria-pressed="true"] { background: var(--accent); color: #fff; border-color: var(--accent); }
.toolbar .spacer { flex: 1; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; }
.tile { position: relative; }
.tile img { width: 100%; display: block; border-radius: 4.75% / 3.5%; aspect-ratio: 488/680; background: var(--surface-2); cursor: zoom-in; }
.tile .badge { position: absolute; top: 6px; left: 6px; font-size: 11px; font-weight: 700; padding: 1px 7px; border-radius: 4px; }
.tile.added .badge { background: var(--in-bg); color: var(--in); }
.tile.added img { outline: 3px solid var(--in); outline-offset: 2px; }
.tile.cut img { filter: grayscale(.7) brightness(.85); }
.tile.cut .badge { background: var(--out-bg); color: var(--out); }
.tile .qty { position: absolute; bottom: 30px; right: 6px; background: rgba(0,0,0,.75); color: #fff; font-weight: 700; font-size: 13px; padding: 1px 8px; border-radius: 6px; }
.tile .cap { font-size: 12px; margin-top: 4px; display: flex; justify-content: space-between; gap: 6px; }
.tile .cap span:first-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.hidden { display: none !important; }
.legend { display: flex; gap: 14px; font-size: 13px; color: var(--muted); }
.legend .sw { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 5px; vertical-align: -1px; }
details.cuts { margin-top: 36px; }
details.cuts summary { cursor: pointer; font-weight: 600; font-size: 18px; }
ul.changelog { padding-left: 18px; font-size: 14px; }
#lightbox { position: fixed; inset: 0; background: rgba(0,0,0,.8); display: none; align-items: center; justify-content: center; gap: 12px; z-index: 50; padding: 16px; cursor: zoom-out; }
#lightbox.open { display: flex; }
#lightbox img { max-height: 90vh; max-width: min(46vw, 488px); border-radius: 18px; }
#lightbox img:only-child { max-width: 92vw; }
footer { margin-top: 50px; font-size: 12px; color: var(--muted); }
@media (max-width: 720px) {
  .deckhead { flex-direction: column; }
  .deckhead img { width: 160px; }
  .grid { grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); }
}
"""

NAV_CSS = """
.site-nav { background: var(--surface); border-bottom: 1px solid var(--border); }
.site-nav .in { max-width: 1180px; margin: 0 auto; padding: 10px 16px; display: flex; gap: 6px 16px; align-items: center; flex-wrap: wrap; font-size: 14px; }
.site-nav a { color: var(--text); text-decoration: none; }
.site-nav a:hover { color: var(--accent); }
.site-nav .brand { font-weight: 700; margin-right: 8px; }
.site-nav .cur { color: var(--accent); font-weight: 600; }
"""

LIGHTBOX_JS = """
const lb = document.getElementById("lightbox");
document.addEventListener("click", e => {
  if (e.target.closest("#lightbox")) { lb.classList.remove("open"); lb.innerHTML = ""; return; }
  const img = e.target.closest("img[data-large]");
  if (!img) return;
  lb.innerHTML = img.dataset.large.split("|").map(u => `<img src="${u}" alt="">`).join("");
  lb.classList.add("open");
});
document.addEventListener("keydown", e => { if (e.key === "Escape") { lb.classList.remove("open"); lb.innerHTML = ""; } });
"""


def deck_meta(path):
    """Title and '- **Key:** value' bullets from a deck file header."""
    lines = path.read_text().splitlines()
    title = lines[0].lstrip("# ").strip()
    meta, changelog, in_log = {}, [], False
    for line in lines:
        m = re.match(r"- \*\*(.+?):\*\*\s*(.*)", line)
        if m and not in_log:
            meta[m.group(1)] = m.group(2)
        if line.startswith("## "):
            in_log = line.startswith("## Changelog")
            continue
        if in_log and line.startswith("- "):
            changelog.append(line[2:])
    return title, meta, changelog


def pips(identity_text):
    cols = [COLOUR_NAMES[w] for w in re.findall(r"White|Blue|Black|Red|Green", identity_text or "")]
    cols.sort(key=COLOUR_ORDER.index)
    return '<span class="pips">' + "".join(f'<span class="pip {c}" title="{c}"></span>' for c in cols) + "</span>"


def nav(decks, base, current=None):
    items = [f'<a class="brand{" cur" if current == "home" else ""}" href="{base}index.html">MTG Decks</a>']
    for d in decks:
        cur = ' class="cur"' if current == d["slug"] else ""
        items.append(f'<a{cur} href="{base}decks/{d["slug"]}.html">{E(d["title"])}</a>')
    return f'<nav class="site-nav"><div class="in">{"".join(items)}</div></nav>'


def page(title, body, base, decks, current, description=""):
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(description)}">
<link rel="stylesheet" href="{base}assets/site.css">
</head><body>
{nav(decks, base, current)}
<div class="wrap">
{body}
<footer>Card images and prices from <a href="https://scryfall.com" target="_blank" rel="noopener">Scryfall</a> (cheapest paper printing). Built {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} from <a href="https://github.com/kasperg3/mtg-deck-building">kasperg3/mtg-deck-building</a>.</footer>
</div>
<div id="lightbox"></div>
<script>{LIGHTBOX_JS}</script>
</body></html>
"""


def img_attrs(info):
    imgs = (info or {}).get("images") or []
    if not imgs:
        return None, ""
    large = "|".join(i.get("large") or i.get("normal") for i in imgs)
    return imgs[0].get("normal"), large


def money(v):
    return "" if v is None else f"€{v:.2f}"


def build_deck(d, cards):
    """Decklist page: current list vs precon snapshot."""
    commanders, current = parse_deck(d["path"])
    precon_path = ROOT / "decks" / "precon" / d["path"].name
    pre_cmd, pre = parse_deck(precon_path) if precon_path.exists() else (commanders, current)
    cur_c = Counter({key(n): q for q, n in current})
    pre_c = Counter({key(n): q for q, n in pre})
    names = {key(n): n for _, n in current + pre}

    groups, value, added_total = {}, 0.0, 0
    for k, q in cur_c.items():
        info = cards.get(k) or {}
        added = max(0, q - pre_c.get(k, 0))
        added_total += added
        value += (info.get("eur") or 0) * q
        groups.setdefault(section_for(info.get("type_line", "")), []).append((names[k], q, added, info))
    cut = [(names[k], pre_c[k] - cur_c.get(k, 0), cards.get(k) or {}) for k in pre_c if pre_c[k] > cur_c.get(k, 0)]

    def tile(name, qty, kind, info):
        src, large = img_attrs(info)
        img = (f'<img loading="lazy" src="{E(src)}" data-large="{E(large)}" alt="{E(name)}">' if src
               else f'<div class="muted small" style="aspect-ratio:488/680;border:1px dashed var(--border);border-radius:8px;padding:8px">{E(name)}</div>')
        badge = {"added": "＋ Added", "cut": "Cut", "precon": ""}[kind]
        link = info.get("scryfall_uri") or "#"
        return (f'<div class="tile {kind}" data-kind="{kind}">{img}'
                f'{f"<span class=badge>{badge}</span>" if badge else ""}'
                f'{f"<span class=qty>×{qty}</span>" if qty > 1 else ""}'
                f'<div class="cap"><span title="{E(name)}"><a href="{E(link)}" target="_blank" rel="noopener">{E(name)}</a></span>'
                f'<span class="muted">{money(info.get("eur"))}</span></div></div>')

    cmd_info = cards.get(key(commanders[0])) if commanders else None
    csrc, clarge = img_attrs(cmd_info)
    facts = "".join(f"<dt>{E(k)}</dt><dd>{E(v)}</dd>" for k, v in d["meta"].items()
                    if k not in ("Commander", "Colour identity", "Product"))
    sections = []
    cmd_tiles = "".join(tile(c, 1, "precon" if key(c) in {key(x) for x in pre_cmd} else "added",
                             cards.get(key(c)) or {}) for c in commanders)
    sections.append(f'<h2>Commander</h2><div class="grid">{cmd_tiles}</div>')
    for sec in SECTIONS + ["Other"]:
        items = groups.get(sec)
        if not items:
            continue
        items.sort(key=lambda x: ("Basic" in x[3].get("type_line", ""), x[3].get("cmc", 0), x[0]))
        tiles = []
        for name, q, added, info in items:
            if added and q - added:   # some copies precon, some added
                tiles.append(tile(name, q - added, "precon", info))
                tiles.append(tile(name, added, "added", info))
            else:
                tiles.append(tile(name, q, "added" if added else "precon", info))
        n_added = sum(a for *_, a, _ in items)
        sections.append(f'<section data-section><h2>{sec} <span class="muted small">{sum(q for _, q, _, _ in items)}'
                        f'{f" · {n_added} added" if n_added else ""}</span></h2><div class="grid">{"".join(tiles)}</div></section>')
    if cut:
        cut.sort(key=lambda x: x[0])
        sections.append(f'<details class="cuts"><summary>Cut from the precon ({sum(q for _, q, _ in cut)})</summary>'
                        f'<p class="muted small">Still owned; these are loose singles now.</p>'
                        f'<div class="grid">{"".join(tile(n, q, "cut", i) for n, q, i in cut)}</div></details>')

    decklist = "\n".join([*(f"1 {c}" for c in commanders), *(f"{q} {n}" for q, n in current)])
    total = len(commanders) + sum(cur_c.values())
    comp = f'<a class="btn secondary" href="../comparisons/{d["slug"]}.html">Upgrade comparison</a>' if d["comparison"] else ""
    log = "".join(f"<li>{E(re.sub(r'[*`]', '', l))}</li>" for l in d["changelog"])
    body = f"""
<div class="deckhead">
  {f'<img src="{E(csrc)}" data-large="{E(clarge)}" alt="{E(commanders[0])}">' if csrc else ""}
  <div>
    <div class="muted small">{E(d["meta"].get("Product", ""))}</div>
    <h1>{E(d["title"])}</h1>
    <div>{pips(d["meta"].get("Colour identity"))} <b>{E(", ".join(commanders))}</b> <span class="muted">· {E(d["meta"].get("Colour identity", ""))}</span></div>
    <dl class="facts">{facts}<dt>Cards</dt><dd>{total} · <b style="color:var(--in)">{added_total} added</b> · {total - added_total} from the precon</dd>
      <dt>Value</dt><dd>≈ €{value:.0f} (cheapest printings)</dd></dl>
    <div style="display:flex;gap:8px;flex-wrap:wrap">{comp}<button class="btn" id="copy" type="button">Copy decklist</button><span id="copied" class="small" style="color:var(--in);align-self:center" hidden>Copied ✓</span></div>
  </div>
</div>
<div class="toolbar">
  <button data-filter="all" aria-pressed="true">All cards</button>
  <button data-filter="added" aria-pressed="false">Added ({added_total})</button>
  <button data-filter="precon" aria-pressed="false">From the precon</button>
  <span class="spacer"></span>
  <span class="legend"><span><span class="sw" style="background:var(--in)"></span>Added</span><span><span class="sw" style="background:var(--out)"></span>Cut</span></span>
</div>
{"".join(sections)}
{f'<h2>Changelog</h2><ul class="changelog">{log}</ul>' if log else ""}
<textarea id="decklist" hidden>{E(decklist)}</textarea>
<script>
document.querySelectorAll(".toolbar button[data-filter]").forEach(b => b.addEventListener("click", () => {{
  const f = b.dataset.filter;
  document.querySelectorAll(".toolbar button[data-filter]").forEach(x => x.setAttribute("aria-pressed", x === b));
  document.querySelectorAll("section[data-section] .tile").forEach(t => t.classList.toggle("hidden", f !== "all" && t.dataset.kind !== f));
  document.querySelectorAll("section[data-section]").forEach(s => s.classList.toggle("hidden", !s.querySelector(".tile:not(.hidden)")));
}}));
document.getElementById("copy").addEventListener("click", async () => {{
  const t = document.getElementById("decklist").value;
  try {{ await navigator.clipboard.writeText(t); }} catch {{ const a = document.getElementById("decklist"); a.hidden = false; a.select(); document.execCommand("copy"); a.hidden = true; }}
  const ok = document.getElementById("copied"); ok.hidden = false; setTimeout(() => ok.hidden = true, 1800);
}});
</script>"""
    stats = {"total": total, "added": added_total, "value": value, "cut": sum(q for _, q, _ in cut),
             "art": (cmd_info or {}).get("images", [{}])[0].get("art_crop") or csrc}
    return body, stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="_site")
    ap.add_argument("--cname", default="mtg.grontved.xyz")
    args = ap.parse_args()
    out = ROOT / args.out
    if out.exists():
        shutil.rmtree(out)
    (out / "decks").mkdir(parents=True)
    (out / "comparisons").mkdir()
    (out / "assets").mkdir()
    (out / "assets" / "site.css").write_text(CSS + NAV_CSS)
    if args.cname:
        (out / "CNAME").write_text(args.cname + "\n")
    (out / ".nojekyll").write_text("")

    cards = load_index(refresh=False, max_age_days=7)["cards"]
    decks = []
    for path in sorted((ROOT / "decks").glob("*.md")):
        title, meta, changelog = deck_meta(path)
        spec = ROOT / "comparisons" / f"{path.stem}-upgrades.json"
        decks.append({"slug": path.stem, "path": path, "title": title, "meta": meta,
                      "changelog": changelog, "comparison": spec if spec.exists() else None})

    for d in decks:
        body, d["stats"] = build_deck(d, cards)
        (out / "decks" / f"{d['slug']}.html").write_text(
            page(f"{d['title']} — decklist", body, "../", decks, d["slug"],
                 f"{d['title']}: full decklist with upgrades marked"))
        if d["comparison"]:
            target = out / "comparisons" / f"{d['slug']}.html"
            subprocess.run([sys.executable, "-B", str(ROOT / "tools" / "build_comparison.py"),
                            str(d["comparison"]), "-o", str(target)], check=True, stdout=subprocess.DEVNULL)
            nav_html = f"<style>{NAV_CSS}</style>" + nav(decks, "../", d["slug"])
            target.write_text(target.read_text().replace("<!--SITE_NAV-->", nav_html, 1))

    tiles = []
    for d in decks:
        s, m = d["stats"], d["meta"]
        comp = f'<a class="btn secondary" href="comparisons/{d["slug"]}.html">Upgrade comparison</a>' if d["comparison"] else ""
        tiles.append(f"""<article class="deck">
  <div class="art" style="background-image:url('{E(s["art"] or "")}')"></div>
  <div class="body">
    <h2>{E(d["title"])}</h2>
    <div>{pips(m.get("Colour identity"))} <b>{E(m.get("Commander", ""))}</b></div>
    <dl class="facts">
      <dt>Precon</dt><dd>{E(re.sub(r",? released.*", "", m.get("Product", "")))}</dd>
      <dt>Bracket</dt><dd>{E(m.get("Bracket", "—"))}</dd>
      <dt>Status</dt><dd>{E(m.get("Status", ""))}</dd>
      <dt>Cards</dt><dd>{s["total"]} · <b style="color:var(--in)">{s["added"]} added</b> · {s["cut"]} cut</dd>
      <dt>Value</dt><dd>≈ €{s["value"]:.0f}</dd>
    </dl>
    <div class="links"><a class="btn" href="decks/{d["slug"]}.html">Decklist</a>{comp}</div>
  </div>
</article>""")
    total = sum(d["stats"]["total"] for d in decks)
    added = sum(d["stats"]["added"] for d in decks)
    body = f"""<div class="hero"><h1>My Commander decks</h1>
<p class="muted">The decks I own, as I play them: full decklists with every upgrade marked, plus the comparisons behind each upgrade.</p></div>
<div class="decks">{"".join(tiles)}</div>
<div class="stats"><div class="stat"><b>{len(decks)}</b><span class="muted small">decks</span></div>
<div class="stat"><b>{total}</b><span class="muted small">cards in decks</span></div>
<div class="stat"><b>{added}</b><span class="muted small">upgrades added</span></div></div>"""
    (out / "index.html").write_text(page("MTG Decks", body, "", decks, "home", "Kasper's Commander decks and upgrades"))
    print(f"built {out.relative_to(ROOT)}: index + {len(decks)} decks + {sum(1 for d in decks if d['comparison'])} comparisons")


if __name__ == "__main__":
    main()
