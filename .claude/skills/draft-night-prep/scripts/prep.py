#!/usr/bin/env python3
"""Run the whole pipeline for a prep config.

Usage: python3 prep.py --work <dir> --config prep.json [--refresh] [--no-check] [--search "Card Name"]

Steps: aggregate.py and scryfall_set.py per set (skipped when their output exists, unless
--refresh), build_data.py, fetch_images.py --prune, gen_page.py, render_check.js.
Keep <work> outside the repo (the game data is tens of MB per set); delete <work>/data/*.csv.gz
when you're done.
"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(args):
    print('$ ' + ' '.join(args), flush=True)
    r = subprocess.run(args)
    if r.returncode:
        sys.exit(r.returncode)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', required=True)
    ap.add_argument('--config', required=True)
    ap.add_argument('--refresh', action='store_true')
    ap.add_argument('--no-check', action='store_true')
    ap.add_argument('--search', help='card name the render check searches for')
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    py = sys.executable
    for sc in cfg['sets']:
        extra = ['--refresh'] if a.refresh else []
        run([py, os.path.join(HERE, 'aggregate.py'), '--work', a.work, '--set', sc['code']] + extra)
        run([py, os.path.join(HERE, 'scryfall_set.py'), '--work', a.work, '--set', sc['code']] + extra)
    run([py, os.path.join(HERE, 'build_data.py'), '--work', a.work, '--config', a.config])
    run([py, os.path.join(HERE, 'fetch_images.py'), '--work', a.work, '--prune'])
    page = os.path.join(a.work, 'site', 'draft-night-cheat-sheet.html')
    run([py, os.path.join(HERE, 'gen_page.py'), '--work', a.work, '--config', a.config, '--out', page])
    if not a.no_check:
        run(['node', os.path.join(HERE, 'render_check.js'), page, os.path.join(a.work, 'shots')] + ([a.search] if a.search else []))
    print(f'\npage: {page}\nroot: {os.path.dirname(page)}\nfiles map: {os.path.join(a.work, "files_map.json")}')


if __name__ == '__main__':
    main()
