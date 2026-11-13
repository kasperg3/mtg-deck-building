#!/usr/bin/env python3
"""Render the cheat-sheet page from page_data.json and the prep config.

Usage: python3 gen_page.py --work <dir> --config prep.json [--out <work>/site/draft-night-cheat-sheet.html]

The page body (no <html>/<head>; the Artifact publisher wraps it) holds every list as static HTML,
so it is complete before any script runs. Script only drives the set switch, the card search,
Open all / Close all and tap-to-zoom. All numbers come from page_data.json; all prose that isn't
generated from numbers (keywords, booster facts, lede) comes from the config.
"""
import argparse, html, json, os, re
from datetime import date

E = html.escape
WUBRG = 'WUBRG'
COLOR_NAME = {'W': 'White', 'U': 'Blue', 'B': 'Black', 'R': 'Red', 'G': 'Green'}
RARITY = {'C': 'Common', 'U': 'Uncommon', 'R': 'Rare', 'M': 'Mythic'}
DEFAULT_SET_COLORS = ['#A898E8', '#E2685C', '#6FC3B2', '#E0B354', '#8FB7F0']


def porder(p):
    return ''.join(sorted(p, key=WUBRG.index))


def pips(colors, cls='pip'):
    cs = [c for c in colors if c in WUBRG]
    if not cs:
        return f'<span class="{cls} m-c" title="Colorless">◇</span>'
    return ''.join(f'<span class="{cls} m-{c.lower()}" title="{COLOR_NAME[c]}">{c}</span>' for c in cs)


def cost_html(cost):
    front = (cost or '').split(' // ')[0]
    toks = re.findall(r'\{([^}]+)\}', front)
    if not toks:
        return ''
    out = ''.join(f'<span class="mana m-{t.lower()}">{t}</span>' if t in WUBRG else f'<span class="mana m-gen">{E(t)}</span>'
                  for t in toks)
    return f'<span class="cost" aria-label="Mana cost {E(front)}">{out}</span>'


def short_type(t):
    return t.split(' // ')[0].split(' — ')[0]


def fmt_date(s):
    d = date.fromisoformat(s)
    return f'{d.day} {d.strftime("%b")} {d.year}'


def join_words(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ', '.join(xs[:-1]) + ' and ' + xs[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', required=True)
    ap.add_argument('--config', required=True)
    ap.add_argument('--out')
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    data = json.load(open(os.path.join(a.work, 'page_data.json')))
    out_path = a.out or os.path.join(a.work, 'site', 'draft-night-cheat-sheet.html')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    order = data['order']
    SC = {}
    for i, sc in enumerate(cfg['sets']):
        s = sc['code'].upper()
        SC[s] = dict(sc, color=sc.get('color') or DEFAULT_SET_COLORS[i % len(DEFAULT_SET_COLORS)])
    D = data['sets']
    labels, pnames = data['labels'], data['pair_names']
    featured, anchor, hl = data['featured'], data.get('anchor'), data.get('highlight')
    multi = len(order) > 1
    accent = SC[order[0]]['color']
    accent2 = SC[order[1]]['color'] if multi else '#E2685C'

    def card_row(c, s, pct=None, sub=None):
        front, _, back = c['name'].partition(' // ')
        pct = c['gih'] if pct is None else pct
        sub = f"#{c['rank']} of {D[s]['ranked']}" if sub is None else sub
        img = c.get('img')
        thumb = (f'<button type="button" class="thumb" data-zoom="img/lg/{img}.jpg" data-name="{E(front)}" aria-label="Show {E(front)} larger">'
                 f'<img src="img/sm/{img}.jpg" alt="" width="146" height="204" loading="lazy"></button>') if img else '<span class="thumb nothumb"></span>'
        back_html = f'<span class="back">// {E(back)}</span>' if back else ''
        return f'''<li class="crow">
  {thumb}
  <div class="cmain">
    <a class="cname" href="{c['uri']}" target="_blank" rel="noopener">{E(front)}</a>{back_html}
    <div class="cmeta">{cost_html(c['cost'])}<span>{E(short_type(c['type']))}</span><span class="rar r-{c['r'].lower()}">{RARITY.get(c['r'], c['r'])}</span></div>
  </div>
  <div class="cstat">
    <span class="tier t-{c['tier'].lower().replace(' ', '-')}">{c['tier']}</span>
    <span class="gih">{pct:.1f}%</span>
    <span class="rank">{sub}</span>
  </div>
</li>'''

    def fold(fid, summary, body, open_=False):
        return f'''<details class="panel fold" id="{fid}"{' open' if open_ else ''}>
  <summary>{summary}<span class="chev" aria-hidden="true"></span></summary>
  <div class="fold-body">
{body}
  </div>
</details>'''

    def pairs_html(s):
        d = D[s]
        lo = min(50.0, float(int(min(p['wr'] for p in d['pairs']))))
        hi = max(58.0, float(int(max(p['wr'] for p in d['pairs'])) + 1))
        avg_left = (d['avg'] - lo) / (hi - lo) * 100
        rows = []
        for i, p in enumerate(d['pairs']):
            w = (p['wr'] - lo) / (hi - lo) * 100
            rows.append(f'''<li class="prow{' is-hl' if p['p'] == hl else ''}">
  <span class="pnum">{i + 1}</span>
  <span class="ppips">{pips(p['p'], 'pip sm')}</span>
  <span class="ptrack"><span class="pbar" style="width:{w:.1f}%"></span></span>
  <span class="pval">{p['wr']:.1f}%</span>
</li>''')
        return f'''<div class="pairs-chart">
  <ol class="plist" style="--avg:{avg_left:.1f}%">
{''.join(rows)}
  </ol>
  <div class="pscale" aria-hidden="true"><span>{lo:.0f}%</span><span class="pavg-label" style="left:{avg_left:.1f}%">avg {d['avg']:.1f}%</span><span>{hi:.0f}%</span></div>
</div>'''

    def pair_section(s, p):
        d = D[s]
        pl = d['pairlists'][p]
        by = {c['name']: c for c in d['cards']}
        rank = next((i + 1 for i, x in enumerate(d['pairs']) if x['p'] == p), None)
        wr = next((x['wr'] for x in d['pairs'] if x['p'] == p), None)
        short = labels[p]
        top = ''.join(card_row(by[x['name']], s, x['wr'], f"{x['n']:,} games") for x in pl['top'])
        com = ''.join(card_row(by[x['name']], s, x['wr'], f"{x['n']:,} games") for x in pl['com'])
        meta = f'<b>{wr:.1f}%</b> · #{rank} of {len(d["pairs"])} pairs' if wr is not None else 'no games'
        summary = (f'<span class="ppips">{pips(p, "pip")}</span><span class="stitle">{E(pnames[p])} top 10</span>'
                   f'<span class="smeta">{meta}</span>')
        body = f'''    <p class="take">The {len(pl['top'])} best cards a {short} deck can cast, ranked by their win rate in {short} decks.</p>
    <ol class="clist">{top}</ol>'''
        if pl['com']:
            body += f'''
    <h3 class="subhead">Best commons, after the top 10</h3>
    <ol class="clist">{com}</ol>'''
        return fold(f'{s.lower()}-{p.lower()}', summary, body)

    def keywords_html(s):
        return '<dl class="kw">' + ''.join(f'<div><dt>{E(k)}</dt><dd>{E(v)}</dd></div>' for k, v in SC[s].get('keywords', [])) + '</dl>'

    def set_view(s, first):
        d = D[s]
        head, sub = d['takeaway']
        by = {c['name']: c for c in d['cards']}
        bomb1 = d['bombs'][0].split(' // ')[0] if d['bombs'] else ''
        colors_body = f'''    <p class="take"><strong>{E(head)}</strong> {E(sub)}</p>
    {pairs_html(s)}'''
        bombs_body = f'''    <p class="take">The set's {len(d['bombs'])} best cards by win rate. Take these in pack 1 whatever their color.</p>
    <ol class="clist">{''.join(card_row(by[n], s) for n in d['bombs'])}</ol>'''
        kws = SC[s].get('keywords', [])
        parts = [
            fold(f'{s.lower()}-colors', '<span class="stitle">Color pairs</span><span class="smeta">ranked by win rate</span>', colors_body, open_=True),
            fold(f'{s.lower()}-bombs', f'<span class="stitle">Bombs</span><span class="smeta">any color · #1 {E(bomb1)}</span>', bombs_body),
        ] + [pair_section(s, p) for p in featured if p in d['pairlists']]
        if kws:
            parts.append(fold(f'{s.lower()}-keywords', f'<span class="stitle">Keywords</span><span class="smeta">{len(kws)} to know</span>', '    ' + keywords_html(s)))
        return f'''<div class="setview" data-set="{s}" id="view-{s.lower()}" style="--set:{SC[s]['color']}"{'' if first else ' hidden'}>
  <div class="foldtools"><span class="hint">{E(SC[s]['name'])} · {d['games']:,} games</span><button type="button" class="toggle-all">Open all</button></div>
{chr(10).join(parts)}
</div>'''

    def anchor_panel():
        if not anchor or 'anchor_text' not in data:
            return ''
        cols = []
        for s in order:
            d = D[s]
            rows = d.get('anchor_rows') or []
            g = sum(r['g'] for r in rows)
            red_wr = sum(r['wr'] * r['g'] for r in rows) / g if g else 0
            col_wr = next((x['wr'] for x in d['colors'] if x['c'] == anchor), red_wr)
            items = ''.join(
                f'<li class="rp"><span class="ppips">{pips(r["p"], "pip sm")}</span>'
                f'<span class="rp-name">+ {COLOR_NAME[r["other"]]}</span><span class="rp-wr">{r["wr"]:.1f}%</span>'
                f'<span class="verdict vd-{r["verdict"].lower().replace(" ", "-")}">{r["verdict"]}</span></li>' for r in rows)
            cols.append(f'''<div class="redcol" style="--set:{SC[s]['color']}">
      <h3>{E(SC[s]['name'])}</h3>
      <p class="hint">{COLOR_NAME[anchor]} decks {col_wr:.1f}% · set average {d['avg']:.1f}%</p>
      <ol>{items}</ol>
    </div>''')
        head, lines = data['anchor_text']
        summary = (f'<span class="ppips">{pips(anchor, "pip")}</span>'
                   f'<span class="stitle">Going {COLOR_NAME[anchor].lower()}: pick the second color</span>')
        body = f'''    <p class="take"><strong>{E(head)}</strong> {E(lines)}</p>
    <div class="redcols">
    {''.join(cols)}
    </div>'''
        return fold('going-anchor', summary, body, open_=True)

    # Search index across every set.
    index = []
    for s in order:
        for c in D[s]['cards']:
            front, _, back = c['name'].partition(' // ')
            index.append(dict(n=front, b=back, s=s, c=''.join(ch for ch in c['colors'] if ch in WUBRG), r=c['r'],
                              g=c['gih'], t=c['tier'], k=c['rank'], u=c['uri']))
    index_json = json.dumps(dict(sets={s: dict(name=SC[s]['name'], ranked=D[s]['ranked'], color=SC[s]['color']) for s in order},
                                 cards=index, start=order[0]),
                            ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')

    set_names = [SC[s]['name'] for s in order]
    placeholder = 'Look up a card' if not multi else ('Look up a card in either set' if len(order) == 2 else 'Look up a card in any set')
    seg = ''
    if multi:
        seg = '<div class="seg" role="group" aria-label="Show set">' + ''.join(
            f'<button type="button" data-set="{s}" aria-pressed="{"true" if i == 0 else "false"}" style="--set:{SC[s]["color"]}">{E(SC[s]["name"])}</button>'
            for i, s in enumerate(order)) + '</div>'
    lede = cfg.get('lede') or (f"{join_words(set_names)}, mixed. Search any card, or switch sets when the packs change." if multi
                              else f"{set_names[0]}. Search any card to see how it performed.")
    title = cfg.get('title', 'Draft Night Cheat Sheet')
    deck_note = cfg.get('deck_note', 'is fine for a low-curve aggressive deck')
    cross = cfg.get('cross_set_note', "The sets barely share mechanics, so don't chase cross-set combos. " if multi else '')
    facts = ''.join(f'''<div style="--set:{SC[s]['color']}">
      <h3>{E(SC[s]['name'])} {E(SC[s]['booster']['name'])} · {SC[s]['booster']['cards']} cards</h3>
      <ul>{''.join(f'<li>{E(f)}</li>' for f in SC[s]['booster'].get('facts', []))}</ul>
    </div>''' for s in order)
    src = ' '.join(f"{SC[s]['name']}: {D[s]['games']:,} games drafted {fmt_date(D[s]['start'])} – {fmt_date(D[s]['end'])}." for s in order)
    avgs = join_words([f"{D[s]['avg']:.1f}%" for s in order])
    cuts = ' '.join(f"{SC[s]['name']}: Bomb ≥ {D[s]['cuts']['Bomb']}%, Great ≥ {D[s]['cuts']['Great']}%, Good ≥ {D[s]['cuts']['Good']}%, OK ≥ {D[s]['cuts']['OK']}%." for s in order)
    rank_mins = join_words([f"{D[s]['thresholds']['rank_min']:,} ({SC[s]['name']})" for s in order])
    pair_mins = join_words([f"{D[s]['thresholds']['pair_min']:,} ({SC[s]['name']})" for s in order])
    theme = ''.join(f' {k}: {v};' for k, v in (cfg.get('theme') or {}).items())

    css = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'page.css')).read()
    js = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'page.js')).read()

    page = f'''<title>{E(title)}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,700;9..144,800&family=Inter:wght@400;500;600;700;800&display=swap">
<style>
{css}
:root {{ --accent: {accent}; --accent-2: {accent2};{theme} }}
</style>

<div class="wrap">

<header class="top">
  <h1>{E(title)}</h1>
  <p class="lede">{E(lede)}</p>
</header>

<div class="bar" role="search">
  {seg}
  <div class="search">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="M20 20l-4-4"></path></svg>
    <input id="card-search" type="search" placeholder="{placeholder}" autocomplete="off" spellcheck="false" aria-label="Look up a card" aria-controls="search-results">
    <button type="button" class="clear" aria-label="Clear search" hidden>×</button>
    <ul class="results" id="search-results" hidden></ul>
  </div>
</div>

<div class="order">
  <span class="lbl" id="lbl-order">Every pick</span>
  <ol aria-labelledby="lbl-order"><li><b>1</b>Bombs</li><li><b>2</b>Cheap removal</li><li><b>3</b>Flyers</li><li><b>4</b>Efficient creatures</li><li><b>5</b>The rest</li></ol>
</div>

{anchor_panel()}

{chr(10).join(set_view(s, i == 0) for i, s in enumerate(order))}

<div class="duo">
  <section class="panel" aria-labelledby="h-flow">
    <p class="eyebrow">During the draft</p>
    <h2 id="h-flow">How the three packs flow</h2>
    <ol class="steps">
      <li><strong>Pack 1 · early</strong><span>Take the most powerful card, any color.</span></li>
      <li><strong>Pack 1 · late</strong><span>Notice which colors still come to you. Those are open.</span></li>
      <li><strong>Pack 2 · early</strong><span>Settle into your two best colors.</span></li>
      <li><strong>Pack 3</strong><span>Fill the gaps: 2-drops, removal, solid playables.</span></li>
    </ol>
    <p class="take">{E(cross)}Skip basic lands; the store supplies them.</p>
  </section>

  <section class="panel" aria-labelledby="h-build">
    <p class="eyebrow">After the draft</p>
    <h2 id="h-build">Build 40 cards</h2>
    <div class="split" role="img" aria-label="17 lands and 23 spells"><div class="l">17 lands</div><div class="s">23 spells</div></div>
    <ul class="ticks">
      <li><span><strong>15–17 creatures</strong> <span class="muted">among the spells</span></span></li>
      <li><span><strong>Two colors</strong> <span class="muted">with lands split by count, e.g. 9 + 8</span></span></li>
      <li><span><strong>16 lands</strong> <span class="muted">{E(deck_note)}</span></span></li>
    </ul>
    <div class="curve" role="img" aria-label="Creatures by mana value: 0 to 1 one-drops, 4 to 6 two-drops, 4 to 5 three-drops, 3 to 4 four-drops, 2 to 3 at five or more">
      <div><b>0–1</b><i style="height:10px"></i>1</div>
      <div><b>4–6</b><i style="height:100px"></i>2</div>
      <div><b>4–5</b><i style="height:90px"></i>3</div>
      <div><b>3–4</b><i style="height:70px"></i>4</div>
      <div><b>2–3</b><i style="height:50px"></i>5+</div>
    </div>
    <p class="hint">Creatures at each mana value.</p>
  </section>
</div>

<section class="panel" aria-labelledby="h-packs">
  <p class="eyebrow">Opening a pack</p>
  <h2 id="h-packs">What's in the boosters</h2>
  <div class="facts">
    {facts}
  </div>
</section>

<footer class="foot">
  <p><strong>Where the numbers come from.</strong> 17lands public game data, Premier Draft on MTG Arena. {src}</p>
  <p>A card's win rate is its GIH WR: the share of games won when the card was in the opening hand or drawn. 17lands users win more often than most players, so compare against each set's average ({avgs}), not 50%. Tiers rank cards within their own set: Bomb is the top 5%, Great the next 10%, Good the next 20%, OK the next 30% and Weak the rest. {cuts} Cards seen in fewer than {rank_mins} games are shown as Low data. Basic lands are left out. Color pairs count every deck with those two main colors. Each pair's top 10 ranks the cards that pair can cast by their win rate in decks of exactly those two main colors, among cards seen in at least {pair_mins} of those games; the count is shown under each win rate. The tier chip is the card's set-wide tier, as in search.</p>
  <p>Card images and details: Scryfall. Booster contents: {E(cfg.get('booster_source', 'Wizards of the Coast and mtg.wtf'))}.</p>
</footer>

</div>

<div class="zoom" id="zoom" role="dialog" aria-modal="true" aria-label="Card image" hidden>
  <img alt="" id="zoom-img">
  <button type="button" aria-label="Close">×</button>
</div>

<script type="application/json" id="card-index">{index_json}</script>
<script>
{js}
</script>
'''
    open(out_path, 'w').write(page)
    print(f'wrote {out_path} ({len(page) / 1024:.0f} KB, {len(index)} cards in search)')


if __name__ == '__main__':
    main()
