#!/usr/bin/env python3
"""Download one set's 17lands public game data and aggregate it.

Usage: python3 aggregate.py --work <dir> --set DSK [--format PremierDraft] [--refresh]

Writes <work>/data/agg_<SET>.json with:
  games, wins, tmin, tmax                 dataset size and draft_time range
  pairs   {main_colors: [games, wins]}    every main_colors value (mono, pairs, 3-color)
  cards   {name: {"g": gih_games, "w": gih_wins, "p": {pair: [gih_games, gih_wins]}}}

GIH = the card was in the opening hand or drawn that game (17lands' "games in hand").
Per-pair numbers only count games whose main_colors is exactly that pair.
"""
import argparse, json, os, sys, urllib.request, shutil
import numpy as np
import pandas as pd

URL = "https://17lands-public.s3.amazonaws.com/analysis_data/game_data/game_data_public.{set}.{fmt}.csv.gz"
PAIRS = ['WU', 'WB', 'WR', 'WG', 'UB', 'UR', 'UG', 'BR', 'BG', 'RG']


def download(url, dest):
    tmp = dest + '.part'
    req = urllib.request.Request(url, headers={'User-Agent': 'draft-night-prep/1.0'})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, 'wb') as f:
        shutil.copyfileobj(r, f, 1 << 20)
    os.replace(tmp, dest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', required=True)
    ap.add_argument('--set', required=True)
    ap.add_argument('--format', default='PremierDraft')
    ap.add_argument('--refresh', action='store_true', help='re-download and re-aggregate')
    a = ap.parse_args()
    s = a.set.upper()
    data_dir = os.path.join(a.work, 'data')
    os.makedirs(data_dir, exist_ok=True)
    gz = os.path.join(data_dir, f'game_{s}.{a.format}.csv.gz')
    out = os.path.join(data_dir, f'agg_{s}.json')
    if os.path.exists(out) and not a.refresh:
        print(f'{s}: {out} exists (use --refresh to rebuild)')
        return
    if not os.path.exists(gz) or a.refresh:
        url = URL.format(set=s, fmt=a.format)
        print(f'{s}: downloading {url}')
        try:
            download(url, gz)
        except Exception as e:  # a set 17lands hasn't published yet, or a typo in the code
            sys.exit(f'{s}: could not download game data ({e}). Check the set code; '
                     f'17lands may not have published this set yet.')
    print(f'{s}: {os.path.getsize(gz) / 1e6:.0f} MB, aggregating')

    hdr = pd.read_csv(gz, nrows=0).columns
    cards = [c[len('deck_'):] for c in hdr if c.startswith('deck_')]
    oh = [f'opening_hand_{c}' for c in cards]
    dr = [f'drawn_{c}' for c in cards]
    n = len(cards)
    gih_g = np.zeros(n, np.int64); gih_w = np.zeros(n, np.int64)
    pair_acc = {p: [np.zeros(n, np.int64), np.zeros(n, np.int64)] for p in PAIRS}
    mc_acc = {}
    games = wins = 0
    tmin = tmax = None
    dtypes = {k: 'float32' for k in oh + dr}
    dtypes.update({'main_colors': 'string', 'draft_time': 'string'})
    for ch in pd.read_csv(gz, usecols=['draft_time', 'main_colors', 'won'] + oh + dr,
                          dtype=dtypes, chunksize=50000):
        won = ch['won'].astype(str).str.lower().isin(['true', '1', '1.0']).to_numpy()
        mc = ch['main_colors'].fillna('').astype(str).to_numpy()
        games += len(ch); wins += int(won.sum())
        t = ch['draft_time'].dropna()
        if len(t):
            tmin = min(tmin or t.min(), t.min()); tmax = max(tmax or t.max(), t.max())
        g = pd.DataFrame({'k': mc, 'w': won}).groupby('k')['w'].agg(['size', 'sum'])
        for k, r in g.iterrows():
            acc = mc_acc.setdefault(k, [0, 0]); acc[0] += int(r['size']); acc[1] += int(r['sum'])
        G = (np.nan_to_num(ch[oh].to_numpy()) + np.nan_to_num(ch[dr].to_numpy())) > 0
        gih_g += G.sum(0); gih_w += G[won].sum(0)
        for p in PAIRS:
            m = mc == p
            if m.any():
                pair_acc[p][0] += G[m].sum(0); pair_acc[p][1] += G[m & won].sum(0)
        print('.', end='', flush=True)
    print()
    res = dict(set=s, format=a.format, games=games, wins=wins, tmin=str(tmin), tmax=str(tmax), pairs=mc_acc,
               cards={c: dict(g=int(gih_g[i]), w=int(gih_w[i]),
                              p={p: [int(pair_acc[p][0][i]), int(pair_acc[p][1][i])] for p in PAIRS})
                      for i, c in enumerate(cards)})
    json.dump(res, open(out, 'w'))
    print(f'{s}: {games:,} games, avg {wins / games * 100:.1f}%, drafted {str(tmin)[:10]} to {str(tmax)[:10]} -> {out}')


if __name__ == '__main__':
    main()
