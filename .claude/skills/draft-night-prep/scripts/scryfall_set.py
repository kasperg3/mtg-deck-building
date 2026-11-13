#!/usr/bin/env python3
"""Fetch a set's booster cards from Scryfall.

Usage: python3 scryfall_set.py --work <dir> --set DSK [--refresh]

Writes <work>/data/sf_<SET>.json: {card name: {rarity, colors, ci, type, cost, cmc, num, uri,
layout, text, front}}. `text` is the oracle text (both faces for double-faced cards), which you
use to write the keyword glossary. Scryfall asks for a User-Agent and Accept header and
about 10 requests a second at most, hence the pause between pages.
"""
import argparse, json, os, time, urllib.parse, urllib.request

H = {"User-Agent": "draft-night-prep/1.0", "Accept": "application/json"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', required=True)
    ap.add_argument('--set', required=True)
    ap.add_argument('--refresh', action='store_true')
    a = ap.parse_args()
    s = a.set.upper()
    os.makedirs(os.path.join(a.work, 'data'), exist_ok=True)
    out = os.path.join(a.work, 'data', f'sf_{s}.json')
    if os.path.exists(out) and not a.refresh:
        print(f'{s}: {out} exists')
        return
    url = "https://api.scryfall.com/cards/search?" + urllib.parse.urlencode(
        {"q": f"set:{s.lower()} is:booster", "unique": "cards"})
    res = {}
    while url:
        d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=30))
        for c in d["data"]:
            f0 = (c.get("card_faces") or [c])[0]
            res[c["name"]] = dict(
                rarity=c["rarity"], colors=c.get("colors") or f0.get("colors") or [],
                ci=c.get("color_identity", []), type=c["type_line"],
                cost=c.get("mana_cost") or f0.get("mana_cost") or "", cmc=c.get("cmc"),
                num=c["collector_number"], uri=c["scryfall_uri"].split("?")[0], layout=c["layout"],
                text=c.get("oracle_text") or " // ".join(f.get("oracle_text", "") for f in c.get("card_faces", [])),
                keywords=c.get("keywords", []), front=f0["name"])
        url = d.get("next_page")
        time.sleep(0.12)
    json.dump(res, open(out, "w"))
    kw = {}
    for v in res.values():
        for k in v['keywords']:
            kw[k] = kw.get(k, 0) + 1
    print(f'{s}: {len(res)} booster cards -> {out}')
    print(f'{s}: most common keywords: ' + ', '.join(f'{k} ({n})' for k, n in sorted(kw.items(), key=lambda x: -x[1])[:15]))


if __name__ == '__main__':
    main()
