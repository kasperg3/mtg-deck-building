(function () {
  var DATA = JSON.parse(document.getElementById('card-index').textContent);
  var KEY = 'draft-sheet-set';
  var codes = Object.keys(DATA.sets);

  // Set switch (absent when the page covers one set)
  var buttons = document.querySelectorAll('.seg button');
  var views = document.querySelectorAll('.setview');
  function showSet(s, save) {
    buttons.forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.set === s ? 'true' : 'false'); });
    views.forEach(function (v) { v.hidden = v.dataset.set !== s; });
    if (save) { try { localStorage.setItem(KEY, s); } catch (e) {} }
  }
  buttons.forEach(function (b) { b.addEventListener('click', function () { showSet(b.dataset.set, true); }); });
  var start = DATA.start;
  var fromHash = codes.filter(function (c) { return '#' + c.toLowerCase() === location.hash; })[0];
  if (fromHash) start = fromHash;
  else { try { var saved = localStorage.getItem(KEY); if (codes.indexOf(saved) !== -1) start = saved; } catch (e) {} }
  showSet(start, false);

  // Search across every set
  var input = document.getElementById('card-search');
  var list = document.getElementById('search-results');
  var clear = document.querySelector('.search .clear');
  var norm = function (s) { return s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9 ]/g, ''); };
  DATA.cards.forEach(function (c) { c._n = norm(c.n); c._b = norm(c.b || ''); });
  var RAR = { C: 'Common', U: 'Uncommon', R: 'Rare', M: 'Mythic' };
  function esc(s) { return String(s).replace(/[&<>"]/g, function (ch) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]; }); }
  function pipsHtml(c) {
    if (!c) return '<span class="pip sm m-c" title="Colorless">◇</span>';
    return c.split('').map(function (x) { return '<span class="pip sm m-' + x.toLowerCase() + '">' + x + '</span>'; }).join('');
  }
  function render(q) {
    var nq = norm(q).trim();
    clear.hidden = !q;
    if (nq.length < 2) { list.hidden = true; list.innerHTML = ''; return; }
    var words = nq.split(/\s+/);
    var hits = DATA.cards.filter(function (c) {
      var hay = c._n + ' ' + c._b;
      return words.every(function (w) { return hay.indexOf(w) !== -1; });
    });
    hits.sort(function (a, b) {
      var as = a._n.indexOf(nq) === 0 ? 0 : 1, bs = b._n.indexOf(nq) === 0 ? 0 : 1;
      return as - bs || b.g - a.g;
    });
    if (!hits.length) {
      list.innerHTML = '<li class="empty">No card matches "' + esc(q) + '". Check the spelling, or try part of the name.</li>';
    } else {
      list.innerHTML = hits.slice(0, 12).map(function (c) {
        var tierCls = 't-' + c.t.toLowerCase().replace(' ', '-');
        var rank = c.k ? '#' + c.k + ' of ' + DATA.sets[c.s].ranked : 'small sample';
        var setchip = codes.length > 1 ? '<span class="setchip" style="--set:' + DATA.sets[c.s].color + '">' + esc(DATA.sets[c.s].name) + '</span>' : '';
        return '<li>' +
          '<span class="tier rtier ' + tierCls + '">' + esc(c.t) + '</span>' +
          '<a class="rname" href="' + esc(c.u) + '" target="_blank" rel="noopener">' + esc(c.n) + '</a>' +
          '<span class="rstat"><span class="gih">' + c.g.toFixed(1) + '%</span><span class="rank">' + rank + '</span></span>' +
          '<span class="rsub">' + setchip + pipsHtml(c.c) + '<span>' + RAR[c.r] + '</span></span>' +
          '</li>';
      }).join('');
    }
    list.hidden = false;
  }
  input.addEventListener('input', function () { render(input.value); });
  input.addEventListener('keydown', function (e) { if (e.key === 'Escape') { input.value = ''; render(''); } });
  clear.addEventListener('click', function () { input.value = ''; render(''); input.focus(); });
  document.addEventListener('click', function (e) { if (!e.target.closest('.search')) list.hidden = true; });
  input.addEventListener('focus', function () { if (norm(input.value).trim().length >= 2) render(input.value); });

  // Open or close every section in a set
  document.querySelectorAll('.toggle-all').forEach(function (btn) {
    var view = btn.closest('.setview');
    var folds = view.querySelectorAll('details.fold');
    function allOpen() { return Array.prototype.every.call(folds, function (d) { return d.open; }); }
    function sync() { btn.textContent = allOpen() ? 'Close all' : 'Open all'; }
    btn.addEventListener('click', function () { var open = !allOpen(); folds.forEach(function (d) { d.open = open; }); sync(); });
    folds.forEach(function (d) { d.addEventListener('toggle', sync); });
    sync();
  });

  // Tap a thumbnail to see the full card
  var zoom = document.getElementById('zoom'), zimg = document.getElementById('zoom-img');
  document.querySelectorAll('.thumb[data-zoom]').forEach(function (t) {
    t.addEventListener('click', function () {
      zimg.src = t.dataset.zoom; zimg.alt = t.dataset.name + ' card';
      zoom.hidden = false; zoom.querySelector('button').focus();
      zoom._from = t;
    });
  });
  function closeZoom() { zoom.hidden = true; zimg.removeAttribute('src'); if (zoom._from) zoom._from.focus(); }
  zoom.addEventListener('click', closeZoom);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !zoom.hidden) closeZoom(); });
})();
