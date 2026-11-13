#!/usr/bin/env python3
"""Join the 17lands aggregates with Scryfall data and compute everything the page shows.

Usage: python3 build_data.py --work <dir> --config prep.json

Reads  <work>/data/agg_<SET>.json and <work>/data/sf_<SET>.json for every set in the config.
Writes <work>/page_data.json and prints a summary plus a plan check for the anchor color.

Rules (see references/data-pipeline.md for why):
- Tiers are percentiles within each set among cards with >= rank_min GIH games.
- Thresholds scale with dataset size unless the config overrides them:
    rank_min  = max(250, 500 * round(1.5 * sqrt(games) / 500))
    pair_min  = max(200, 500 * round(sqrt(games) / 500))
    index_min = max(100, rank_min // 5)   (below this a card is left out of search entirely)
- Basic lands and cards Scryfall doesn't list in the set (Special Guests, The List) are left out.
- Win rates are compared with the set's average, never with 50%.
"""
import argparse, json, math, os, sys

WUBRG = 'WUBRG'
COLOR_NAME = {'W': 'White', 'U': 'Blue', 'B': 'Black', 'R': 'Red', 'G': 'Green'}
PAIRS = ['WU', 'WB', 'WR', 'WG', 'UB', 'UR', 'UG', 'BR', 'BG', 'RG']
WORDS = {1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five'}


def ordinal(n):
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def porder(p):
    return ''.join(sorted(p, key=WUBRG.index))


def thresholds(games, override):
    rank_min = max(250, 500 * round(1.5 * math.sqrt(games) / 500))
    t = dict(rank_min=rank_min, pair_min=max(200, 500 * round(math.sqrt(games) / 500)),
             index_min=max(100, rank_min // 5))
    t.update(override or {})
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', required=True)
    ap.add_argument('--config', required=True)
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    names = {k: v for k, v in (cfg.get('pair_names') or {}).items()}

    def label(p):
        p = porder(p)
        return names[p][1] if p in names else '/'.join(p)

    def pname(p):
        p = porder(p)
        return names[p][0] if p in names else '–'.join(COLOR_NAME[c] for c in p)

    featured = [porder(p) for p in cfg.get('featured_pairs', [])]
    anchor = cfg.get('anchor')
    hl = porder(cfg.get('highlight_pair') or (featured[0] if featured else '')) or None
    out = dict(sets={}, order=[s['code'].upper() for s in cfg['sets']], featured=featured, anchor=anchor,
               highlight=hl, labels={p: label(p) for p in PAIRS}, pair_names={p: pname(p) for p in PAIRS})

    for sc in cfg['sets']:
        s = sc['code'].upper()
        agg = json.load(open(os.path.join(a.work, 'data', f'agg_{s}.json')))
        sf = json.load(open(os.path.join(a.work, 'data', f'sf_{s}.json')))
        byfront = {v['front']: k for k, v in sf.items()}
        th = thresholds(agg['games'], sc.get('thresholds'))
        avg = agg['wins'] / agg['games'] * 100
        cards, unmatched = [], []
        for raw, v in agg['cards'].items():
            key = raw if raw in sf else byfront.get(raw.split(' // ')[0])
            if not key:
                unmatched.append(raw); continue
            m = sf[key]
            if 'Basic' in m['type'] and 'Land' in m['type']:
                continue
            if v['g'] < th['index_min']:
                continue
            cards.append(dict(name=key, r=m['rarity'][0].upper(), colors=''.join(m['colors']) or 'C',
                              ci=''.join(m['ci']), cost=m['cost'], type=m['type'], num=m['num'], uri=m['uri'],
                              gih=round(v['w'] / v['g'] * 100, 1), n=v['g'],
                              pairs={p: v['p'][p] for p in PAIRS if p in v['p']}))
        ranked = sorted([c for c in cards if c['n'] >= th['rank_min']], key=lambda c: -c['gih'])
        N = len(ranked)
        for i, c in enumerate(ranked):
            c['rank'] = i + 1
            q = (i + 1) / N
            c['tier'] = 'Bomb' if q <= .05 else 'Great' if q <= .15 else 'Good' if q <= .35 else 'OK' if q <= .65 else 'Weak'
        for c in cards:
            c.setdefault('rank', None); c.setdefault('tier', 'Low data')
        cuts = {t: min(c['gih'] for c in ranked if c['tier'] == t) for t in ['Bomb', 'Great', 'Good', 'OK']}

        pairs = sorted([dict(p=porder(k), wr=round(w / g * 100, 1), g=g, w=w) for k, (g, w) in agg['pairs'].items()
                        if len(k) == 2 and g > 0], key=lambda x: -x['wr'])
        colors = []
        for col in WUBRG:
            g = sum(p['g'] for p in pairs if col in p['p'])
            w = sum(p['w'] for p in pairs if col in p['p'])
            if g:
                colors.append(dict(c=col, wr=round(w / g * 100, 1), g=g))
        colors.sort(key=lambda x: -x['wr'])

        # Pair lists: cards the pair can cast, ranked by GIH WR in that pair's decks.
        pairlists = {}
        for p in featured:
            rows = []
            for c in cards:
                if not set(c['ci']) <= set(p) or p not in c['pairs']:
                    continue
                g, w = c['pairs'][p]
                if g >= th['pair_min']:
                    rows.append(dict(name=c['name'], wr=round(w / g * 100, 1), n=g, r=c['r']))
            rows.sort(key=lambda r: -r['wr'])
            top = rows[:10]
            topn = {r['name'] for r in top}
            com = [r for r in rows if r['r'] == 'C' and r['name'] not in topn][:5]
            pairlists[p] = dict(top=top, com=com)

        # Takeaway for the color-pair chart, written from the numbers.
        rank_of = {x['p']: i + 1 for i, x in enumerate(pairs)}
        best, second = pairs[0], pairs[1]
        c1, c2 = colors[0], colors[1]
        mentioned = set()
        if c1['wr'] - c2['wr'] >= 0.8:
            top5 = [x for x in pairs[:5] if c1['c'] in x['p']]
            lead = top5[0] if top5 else best
            head = f"{COLOR_NAME[c1['c']]} is the color to be in for {sc['name']}."
            sub = (f"{COLOR_NAME[c1['c']]} pairs took {WORDS.get(len(top5), len(top5))} of the top five spots, "
                   f"led by {label(lead['p'])} at {lead['wr']:.1f}%.")
            mentioned.add(lead['p'])
        else:
            head = f"{label(best['p'])} was the best pair in {sc['name']}."
            sub = f"{label(best['p'])} won {best['wr']:.1f}% of games"
            if best['wr'] - second['wr'] <= 1.0:
                sub += f", just ahead of {label(second['p'])} at {second['wr']:.1f}%"
                mentioned.add(second['p'])
            sub += '.'
            mentioned.add(best['p'])
        if hl and hl in rank_of and hl not in mentioned:
            x = pairs[rank_of[hl] - 1]
            sub += (f" {label(hl)} came {ordinal(rank_of[hl])} at {x['wr']:.1f}%, "
                    f"{'above' if x['wr'] >= avg else 'below'} the {avg:.1f}% average.")
        w1, w2 = pairs[-2], pairs[-1]
        sub += f" {label(w1['p'])} and {label(w2['p'])} were the weakest."

        anchor_rows = None
        if anchor:
            anchor_rows = []
            for x in pairs:
                if anchor not in x['p']:
                    continue
                diff = x['wr'] - avg
                verdict = 'Strong' if diff >= 1.5 else 'Above avg' if diff >= 0 else 'Average' if diff >= -1 else 'Avoid'
                other = next(ch for ch in x['p'] if ch != anchor)
                anchor_rows.append(dict(p=x['p'], other=other, wr=x['wr'], g=x['g'], rank=rank_of[x['p']], verdict=verdict))

        out['sets'][s] = dict(
            code=s, name=sc['name'], games=agg['games'], avg=round(avg, 1), start=agg['tmin'][:10], end=agg['tmax'][:10],
            thresholds=th, ranked=N, cuts=cuts, pairs=pairs, colors=colors, pairlists=pairlists,
            bombs=[c['name'] for c in ranked[:10]], takeaway=[head, sub], anchor_rows=anchor_rows,
            cards=sorted(cards, key=lambda c: c['name']), unmatched=len(unmatched))

        print(f"== {s} {sc['name']}: {agg['games']:,} games {agg['tmin'][:10]}..{agg['tmax'][:10]} avg {avg:.1f}% | "
              f"thresholds {th} | ranked {N} | unmatched (Special Guests etc.) {len(unmatched)}")
        print(f"   {head} {sub}")
        print('   pairs: ' + ', '.join(f"{label(x['p'])} {x['wr']:.1f}" for x in pairs))
        print('   colors: ' + ', '.join(f"{x['c']} {x['wr']:.1f}" for x in colors))
        print('   bombs: ' + ', '.join(n.split(' // ')[0] for n in out['sets'][s]['bombs']))
        for p, pl in pairlists.items():
            print(f'   {label(p)} top 10: ' + ', '.join(f"{r['name'].split(' // ')[0]} {r['wr']:.1f}" for r in pl['top']))
            print(f'   {label(p)} commons: ' + ', '.join(f"{r['name'].split(' // ')[0]} {r['wr']:.1f}" for r in pl['com']))
            if len(pl['top']) < 10:
                print(f'   WARNING: only {len(pl["top"])} cards cleared pair_min={th["pair_min"]} for {label(p)}')

    # Anchor panel text and the plan check.
    if anchor:
        sets = [out['sets'][s] for s in out['order']]
        A = COLOR_NAME[anchor]
        ranks = {sd['code']: next((i + 1 for i, x in enumerate(sd['colors']) if x['c'] == anchor), None) for sd in sets}
        wrs = {sd['code']: next((x['wr'] for x in sd['colors'] if x['c'] == anchor), None) for sd in sets}
        below = [sd for sd in sets if wrs[sd['code']] is not None and wrs[sd['code']] < sd['avg']]
        scope = sets[0]['name'] if len(sets) == 1 else ('both sets' if len(sets) == 2 else 'every set')
        if not below and all((ranks[sd['code']] or 9) <= 2 for sd in sets):
            head = f"{A} is a safe first color in {scope}."
        elif not below:
            head = f"{A} is above average in {scope}."
        else:
            head = f"{A} is below average in {', '.join(sd['name'] for sd in below)}."
        lines = []
        for sd in sets:
            rows = sd['anchor_rows']
            if not rows:
                continue
            pre = f"In {sd['name']}, " if len(sets) > 1 else ''
            avoid = [r for r in rows if r['verdict'] == 'Avoid']
            best_partner = COLOR_NAME[rows[0]['other']].lower()
            if avoid:
                line = (f"{pre}look for {best_partner} and stay away from "
                        f"{' and '.join(COLOR_NAME[r['other']].lower() for r in avoid)}.")
            elif all(r['wr'] >= sd['avg'] for r in rows):
                line = f"{pre}every {A.lower()} pair beats the average, so follow the packs."
            else:
                line = f"{pre}{best_partner} is the best partner."
            lines.append(line[0].upper() + line[1:])
        out['anchor_text'] = [head, ' '.join(lines)]
        print(f'\n== Plan check: {A} first')
        print(f'   {head} {" ".join(lines)}')
        print('   | ' + A + ' + | ' + ' | '.join(f"{sd['name']} (avg {sd['avg']:.1f}%)" for sd in sets) + ' |')
        for other in [c for c in WUBRG if c != anchor]:
            cells = []
            for sd in sets:
                r = next((r for r in sd['anchor_rows'] if r['other'] == other), None)
                cells.append(f"{r['wr']:.1f}% (#{r['rank']} of {len(sd['pairs'])}, {r['verdict']})" if r else 'n/a')
            print(f'   | {COLOR_NAME[other]} | ' + ' | '.join(cells) + ' |')
        for sd in sets:
            print(f"   {A} decks in {sd['name']}: {wrs[sd['code']]}% (#{ranks[sd['code']]} of {len(sd['colors'])} colors)")

    json.dump(out, open(os.path.join(a.work, 'page_data.json'), 'w'))
    print(f"\nwrote {os.path.join(a.work, 'page_data.json')}")


if __name__ == '__main__':
    main()
