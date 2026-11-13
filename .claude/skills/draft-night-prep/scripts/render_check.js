// Render check for a generated cheat sheet. Usage:
//   node render_check.js <page.html> <out-dir> [search term]
// Wraps the page body in a bare skeleton (deliberately WITHOUT the artifact host's [hidden] reset,
// so a page that forgets its own guard fails here instead of on the user's phone), then checks at
// 1280px and 400px: no horizontal overflow, no broken images, no console or page errors, no
// placeholder text, the zoom overlay starts hidden, and the set switch, search, Open all /
// Close all and tap-to-zoom all work in every set. Exits 1 on any failure.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const [page, outDir, termArg] = process.argv.slice(2);
  if (!page || !outDir) { console.error('usage: node render_check.js <page.html> <out-dir> [search term]'); process.exit(2); }
  fs.mkdirSync(outDir, { recursive: true });
  const body = fs.readFileSync(page, 'utf8');
  const wrapped = path.join(path.dirname(path.resolve(page)), '_render_check.html');
  fs.writeFileSync(wrapped, '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"></head><body>' + body + '</body></html>');
  const url = 'file://' + wrapped;
  const fails = [], notes = {};
  const fail = (m) => fails.push(m);
  const browser = await chromium.launch();

  async function open(width) {
    const p = await browser.newPage({ viewport: { width, height: 900 } });
    const errs = [];
    p.on('pageerror', (e) => errs.push(String(e)));
    p.on('console', (m) => { if (m.type() === 'error' && !/fonts\.g/.test(m.text())) errs.push(m.text()); });
    p.on('requestfailed', (r) => { if (r.url().startsWith('file:')) errs.push('missing file ' + r.url()); });
    await p.goto(url, { waitUntil: 'load' });
    p._errs = errs;
    return p;
  }
  async function eager(p) {
    await p.evaluate(() => document.querySelectorAll('img[loading=lazy]').forEach((i) => { i.loading = 'eager'; }));
    await p.evaluate(() => Promise.all([...document.querySelectorAll('.setview:not([hidden]) img')].map((i) => i.complete ? 0 : new Promise((r) => { i.onload = i.onerror = r; }))));
  }

  // Desktop
  const d = await open(1280);
  await eager(d);
  const dInfo = await d.evaluate(() => ({
    overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    zoomHidden: getComputedStyle(document.getElementById('zoom')).display === 'none',
    text: document.body.innerText,
    sets: [...document.querySelectorAll('.setview')].map((v) => v.dataset.set),
  }));
  if (dInfo.overflow) fail('desktop: horizontal overflow');
  if (!dInfo.zoomHidden) fail('zoom overlay is visible at load (missing [hidden] guard?)');
  const ph = dInfo.text.match(/\b(TODO|TBD|FIXME|lorem ipsum|PLACEHOLDER|undefined|NaN)\b|\{\{|\}\}/i);
  if (ph) fail('placeholder or broken text on page: "' + ph[0] + '"');
  await d.screenshot({ path: path.join(outDir, 'desktop.png'), fullPage: true });
  notes.sets = dInfo.sets;

  // Phone: every set
  const p = await open(400);
  for (const s of dInfo.sets) {
    const btn = await p.$(`.seg button[data-set="${s}"]`);
    if (btn) await btn.click();
    const shown = await p.evaluate((s) => !document.querySelector(`.setview[data-set="${s}"]`).hidden, s);
    if (!shown) { fail(`${s}: set view not shown after switching`); continue; }
    await p.click(`.setview[data-set="${s}"] .toggle-all`);
    const opened = await p.evaluate((s) => { const f = [...document.querySelectorAll(`.setview[data-set="${s}"] details`)]; return [f.filter((x) => x.open).length, f.length]; }, s);
    if (opened[0] !== opened[1]) fail(`${s}: Open all opened ${opened[0]} of ${opened[1]} sections`);
    await eager(p);
    const info = await p.evaluate((s) => ({
      overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      imgs: document.querySelectorAll(`.setview[data-set="${s}"] img`).length,
      broken: [...document.querySelectorAll(`.setview[data-set="${s}"] img`)].filter((i) => !i.naturalWidth).map((i) => i.getAttribute('src')),
      rows: document.querySelectorAll(`.setview[data-set="${s}"] .crow`).length,
    }), s);
    if (info.overflow) fail(`${s}: horizontal overflow at 400px`);
    if (info.broken.length) fail(`${s}: ${info.broken.length} broken images, e.g. ${info.broken[0]}`);
    if (!info.rows) fail(`${s}: no card rows`);
    notes[s] = { rows: info.rows, images: info.imgs };
    if (s === dInfo.sets[0]) await p.screenshot({ path: path.join(outDir, 'phone.png'), fullPage: true });
    const thumb = await p.$(`.setview[data-set="${s}"] .thumb[data-zoom]`);
    if (thumb) {
      await thumb.click();
      await p.waitForTimeout(300);
      const z = await p.evaluate(() => ({ shown: !document.getElementById('zoom').hidden, w: document.getElementById('zoom-img').naturalWidth }));
      if (!z.shown || !z.w) fail(`${s}: zoom did not show the card image`);
      await p.keyboard.press('Escape');
      if (!(await p.evaluate(() => document.getElementById('zoom').hidden))) fail(`${s}: Escape did not close zoom`);
    } else fail(`${s}: no zoomable thumbnails`);
    await p.click(`.setview[data-set="${s}"] .toggle-all`);
    const closed = await p.evaluate((s) => document.querySelectorAll(`.setview[data-set="${s}"] details[open]`).length, s);
    if (closed) fail(`${s}: Close all left ${closed} sections open`);
  }

  // Search
  const term = termArg || (await p.evaluate(() => (document.querySelector('.cname') || {}).textContent || '')).split(/[ ,]/)[0];
  await p.fill('#card-search', term);
  await p.waitForTimeout(150);
  const results = await p.evaluate(() => [...document.querySelectorAll('#search-results li:not(.empty)')].map((l) => l.innerText.replace(/\s+/g, ' ')));
  if (!results.length) fail(`search for "${term}" returned nothing`);
  notes.search = { term, first: results[0] || null, count: results.length };

  for (const [name, pg] of [['desktop', d], ['phone', p]]) if (pg._errs.length) fail(`${name} errors: ${pg._errs.slice(0, 3).join(' | ')}`);
  await browser.close();
  fs.unlinkSync(wrapped);
  console.log(JSON.stringify({ ok: !fails.length, fails, notes }, null, 1));
  process.exit(fails.length ? 1 : 0);
})();
