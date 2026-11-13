#!/usr/bin/env python3
"""Download Scryfall images for every card the page lists, and write the publish file map.

Usage: python3 fetch_images.py --work <dir> [--prune]

Listed cards = each set's bombs + every featured pair's top 10 and commons. For each one it saves
  <work>/site/img/sm/<set>-<num>.jpg   (Scryfall "small", 146x204, the list thumbnail)
  <work>/site/img/lg/<set>-<num>.jpg   (Scryfall "normal", 488x680, the tap-to-zoom image)
skipping files that already exist. The artifact CSP blocks images from other hosts, so the
images ship with the page as published files.

--prune deletes images no longer listed and marks them null in the map, so a republish removes
them from the artifact too. Writes <work>/files_map.json: {published path: source path | null},
ready to pass as the Artifact tool's `files` with root=<work>/site.
"""
import argparse, json, os, time, urllib.request

H = {"User-Agent": "draft-night-prep/1.0"}


def get(url, accept):
    with urllib.request.urlopen(urllib.request.Request(url, headers={**H, "Accept": accept}), timeout=30) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', required=True)
    ap.add_argument('--prune', action='store_true')
    a = ap.parse_args()
    pd_path = os.path.join(a.work, 'page_data.json')
    d = json.load(open(pd_path))
    img = os.path.join(a.work, 'site', 'img')
    for sub in ('sm', 'lg'):
        os.makedirs(os.path.join(img, sub), exist_ok=True)
    needed, fetched = set(), 0
    for s, sd in d['sets'].items():
        names = set(sd['bombs'])
        for pl in sd['pairlists'].values():
            names |= {x['name'] for x in pl['top'] + pl['com']}
        for c in sd['cards']:
            if c['name'] not in names:
                c.pop('img', None); continue
            slug = f"{s.lower()}-{c['num']}"
            c['img'] = slug; needed.add(slug)
            if all(os.path.exists(os.path.join(img, sub, slug + '.jpg')) for sub in ('sm', 'lg')):
                continue
            j = json.loads(get(f"https://api.scryfall.com/cards/{s.lower()}/{c['num']}", "application/json"))
            if j['name'] != c['name']:
                raise SystemExit(f"Scryfall returned {j['name']} for {s} #{c['num']}, expected {c['name']}")
            iu = j.get('image_uris') or j['card_faces'][0]['image_uris']
            for size, sub in (('small', 'sm'), ('normal', 'lg')):
                time.sleep(0.11)
                data = get(iu[size], "image/*")
                if not data.startswith(b'\xff\xd8'):
                    raise SystemExit(f'{slug} {size}: not a JPEG')
                open(os.path.join(img, sub, slug + '.jpg'), 'wb').write(data)
            fetched += 1
            time.sleep(0.11)
    json.dump(d, open(pd_path, 'w'))
    fmap, removed = {}, []
    for sub in ('sm', 'lg'):
        for f in sorted(os.listdir(os.path.join(img, sub))):
            if f[:-4] in needed:
                fmap[f'img/{sub}/{f}'] = f'img/{sub}/{f}'
            elif a.prune:
                os.remove(os.path.join(img, sub, f)); fmap[f'img/{sub}/{f}'] = None; removed.append(f)
    json.dump(fmap, open(os.path.join(a.work, 'files_map.json'), 'w'), indent=0)
    print(f'listed cards {len(needed)}, downloaded {fetched}, pruned {len(removed) // 2}, '
          f'files_map entries {len(fmap)} -> {os.path.join(a.work, "files_map.json")}')
    if len(fmap) > 255:
        print('WARNING: more than 255 files; publish in two calls to the same url')


if __name__ == '__main__':
    main()
