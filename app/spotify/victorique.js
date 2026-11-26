// Victorique · ponte do Spicetify
// Gerado pelo assistente Victorique (app/spotify/spicetify.py). Não edite à mão:
// reinstale pelas Configurações → Na área de trabalho.
// Conta ao app, só no seu computador (127.0.0.1), onde ficam os painéis, as abas,
// as capas e as faixas da página do Spotify e qual música está tocando.
(function victorique() {
  "use strict";
  const PORT = __PORT__;
  const TOKEN = __TOKEN__;
  const BASE = `127.0.0.1:${PORT}/api/spotify`;
  if (!window.Spicetify || !Spicetify.Player || !Spicetify.Player.addEventListener || !document.body) {
    setTimeout(victorique, 500);
    return;
  }

  // Spotify lays its window out as a CSS grid with named areas. Its class names
  // change with every build (1.3.x dropped the old Root__* ones), the area names
  // do not; the old classes are still tried for older builds.
  const GRID = {
    "global-nav": ["nav", "panel"],
    "left-sidebar": ["biblioteca", "panel"],
    "main-view": ["principal", "panel"],
    "right-sidebar": ["direita", "panel"],
    "now-playing-bar": ["player", "player"],
  };
  const PANELS = [
    ["nav", ".Root__globalNav", "panel"],
    ["topo", ".Root__top-bar", "panel"],
    ["biblioteca", ".Root__nav-bar", "panel"],
    ["principal", ".Root__main-view", "panel"],
    ["direita", ".Root__right-sidebar", "panel"],
    ["player", ".Root__now-playing-bar", "player"],
  ];
  const ITEMS = [
    ["tab", '[role="tab"], [data-encore-id="chip"], .main-yourLibraryX-filterArea button', 12],
    ["card", '[data-encore-id="card"], .main-card-card', 16],
    ["row", '[data-testid="tracklist-row"], [data-encore-id="listRow"], .main-trackList-trackListRow', 8],
  ];
  const OLD_AREAS = ".Root__main-view, .Root__nav-bar, .Root__right-sidebar";

  let grid = null;
  let gridLookedAt = 0;

  function findGrid() {
    if (grid && grid.isConnected) return grid;
    const now = Date.now();
    if (now - gridLookedAt < 5000) return null;
    gridLookedAt = now;
    grid = null;
    let level = [document.body];
    for (let depth = 0; depth < 10 && level.length && !grid; depth++) {
      const next = [];
      for (const el of level) {
        if (getComputedStyle(el).gridTemplateAreas.includes("now-playing-bar")) { grid = el; break; }
        next.push(...el.children);
      }
      level = next.slice(0, 600);
    }
    return grid;
  }

  // The grid's children that fill one named area exactly: [element, id, kind].
  function gridAreas() {
    const g = findGrid();
    const out = [];
    if (!g) return out;
    for (const child of g.children) {
      const s = getComputedStyle(child);
      const name = s.gridRowStart;
      if (!GRID[name] || s.gridColumnStart !== name || s.gridRowEnd !== name || s.gridColumnEnd !== name) continue;
      out.push([child, ...GRID[name]]);
    }
    return out;
  }

  function hash(text) {
    let h = 5381;
    for (let i = 0; i < text.length; i++) h = ((h * 33) ^ text.charCodeAt(i)) >>> 0;
    return h.toString(36);
  }

  function box(rect) {
    return { x: Math.round(rect.left), y: Math.round(rect.top), w: Math.round(rect.width), h: Math.round(rect.height) };
  }

  function onScreen(rect) {
    return rect.width >= 40 && rect.height >= 16 && rect.bottom > 0 && rect.right > 0 &&
      rect.top < window.innerHeight && rect.left < window.innerWidth;
  }

  function elements() {
    const out = [];
    const areas = gridAreas();
    const panels = areas.length ? areas
      : PANELS.map(([id, selector, kind]) => [document.querySelector(selector), id, kind]).filter(p => p[0]);
    for (const [el, id, kind] of panels) {
      const rect = el.getBoundingClientRect();
      if (onScreen(rect)) out.push({ id, kind, ...box(rect) });
    }
    // The scrolling panels an item may belong to (the player bar does not scroll).
    const holders = areas.filter(a => a[2] === "panel").map(a => a[0]);
    const holderOf = el => (holders.length ? holders.find(h => h.contains(el)) : el.closest(OLD_AREAS)) || null;
    const seen = new Set();
    for (const [kind, selector, limit] of ITEMS) {
      let n = 0;
      for (const el of document.querySelectorAll(selector)) {
        if (n >= limit) break;
        const rect = el.getBoundingClientRect();
        if (!onScreen(rect)) continue;
        let left = rect.left;
        let right = rect.right;
        const area = holderOf(el);
        if (area) {
          const a = area.getBoundingClientRect();
          if (rect.top < a.top || rect.top >= a.bottom) continue; // scrolled out of its panel
          // A carousel's covers past the panel's side are clipped (invisible): cut them too.
          left = Math.max(left, a.left);
          right = Math.min(right, a.right);
          if (right - left < 40) continue;
        }
        const link = el.querySelector("a[href]");
        const label = el.getAttribute("aria-label") || (link && link.getAttribute("href")) ||
          (el.textContent || "").trim().slice(0, 60);
        let id = hash(label || `${kind}${n}`);
        while (seen.has(kind + id)) id += "x";
        seen.add(kind + id);
        out.push({ id, kind, ...box({ left, top: rect.top, width: right - left, height: rect.height }) });
        n++;
      }
    }
    return out;
  }

  function track() {
    const data = Spicetify.Player.data || {};
    const item = data.item || data.track;
    if (!item) return null;
    const uri = String(item.uri || "");
    if (uri.startsWith("spotify:ad") || item.type === "ad" || item.isAd) return null;
    const meta = item.metadata || {};
    const artists = Array.isArray(item.artists)
      ? item.artists.map(a => a && a.name).filter(Boolean).join(", ") : "";
    return {
      title: item.name || meta.title || "",
      artist: artists || meta.artist_name || "",
      album: (item.album && item.album.name) || meta.album_title || "",
    };
  }

  function snapshot() {
    let playing = false;
    try { playing = !!Spicetify.Player.isPlaying(); } catch (e) { /* older Spicetify */ }
    return {
      token: TOKEN,
      view: { w: window.innerWidth, h: window.innerHeight },
      elements: elements(),
      track: track(),
      playing,
    };
  }

  let ws = null;
  let fails = 0;
  let last = "";
  let lastAt = 0;

  function connect() {
    try {
      ws = new WebSocket(`ws://${BASE}/ws?t=${encodeURIComponent(TOKEN)}`);
    } catch (e) {
      ws = null;
      fails++;
      setTimeout(connect, 30000);
      return;
    }
    ws.onopen = () => { fails = 0; last = ""; send(); };
    ws.onclose = () => { ws = null; fails++; setTimeout(connect, Math.min(30000, 2000 * fails)); };
    ws.onerror = () => {};
  }

  let postFails = 0;
  let postAfter = 0;

  function send() {
    let body;
    try { body = JSON.stringify(snapshot()); } catch (e) { return; }
    const now = Date.now();
    if (body === last && now - lastAt < 4000) return; // nothing new: a heartbeat every 4 s
    if (ws && ws.readyState === 1) {
      ws.send(body);
    } else if (fails >= 3 && now >= postAfter) {
      // No WebSocket on the app's side: plain POST (text/plain needs no preflight).
      // The app closed (or refusing an old token): wait longer after each failure.
      fetch(`http://${BASE}/bridge`, { method: "POST", headers: { "Content-Type": "text/plain" }, body })
        .then(r => { postFails = r.ok ? 0 : postFails + 1; }, () => { postFails++; })
        .then(() => { postAfter = postFails ? Date.now() + Math.min(60000, 2000 * postFails) : 0; });
    } else {
      return;
    }
    last = body;
    lastAt = now;
  }

  let queued = false;
  function soon() {
    if (queued) return;
    queued = true;
    setTimeout(() => { queued = false; send(); }, 100);
  }

  Spicetify.Player.addEventListener("songchange", () => { last = ""; soon(); });
  Spicetify.Player.addEventListener("onplaypause", () => { last = ""; soon(); });
  window.addEventListener("resize", soon);
  document.addEventListener("scroll", soon, { capture: true, passive: true });
  setInterval(send, 1000);
  connect();
})();
