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

  const PANELS = [
    ["nav", ".Root__globalNav", "panel"],
    ["topo", ".Root__top-bar", "panel"],
    ["biblioteca", ".Root__nav-bar", "panel"],
    ["principal", ".Root__main-view", "panel"],
    ["direita", ".Root__right-sidebar", "panel"],
    ["player", ".Root__now-playing-bar", "player"],
  ];
  const ITEMS = [
    ["tab", '[role="tab"], .main-yourLibraryX-filterArea button', 12],
    ["card", '.main-card-card, [data-encore-id="card"]', 16],
    ["row", '.main-trackList-trackListRow, [data-testid="tracklist-row"]', 8],
  ];
  const AREAS = ".Root__main-view, .Root__nav-bar, .Root__right-sidebar";

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
    for (const [id, selector, kind] of PANELS) {
      const el = document.querySelector(selector);
      if (!el) continue;
      const rect = el.getBoundingClientRect();
      if (onScreen(rect)) out.push({ id, kind, ...box(rect) });
    }
    const seen = new Set();
    for (const [kind, selector, limit] of ITEMS) {
      let n = 0;
      for (const el of document.querySelectorAll(selector)) {
        if (n >= limit) break;
        const rect = el.getBoundingClientRect();
        if (!onScreen(rect)) continue;
        const area = el.closest(AREAS);
        if (area) {
          const a = area.getBoundingClientRect();
          if (rect.top < a.top || rect.top >= a.bottom) continue; // scrolled out of its panel
        }
        const link = el.querySelector("a[href]");
        const label = el.getAttribute("aria-label") || (link && link.getAttribute("href")) ||
          (el.textContent || "").trim().slice(0, 60);
        let id = hash(label || `${kind}${n}`);
        while (seen.has(kind + id)) id += "x";
        seen.add(kind + id);
        out.push({ id, kind, ...box(rect) });
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

  function send() {
    let body;
    try { body = JSON.stringify(snapshot()); } catch (e) { return; }
    const now = Date.now();
    if (body === last && now - lastAt < 4000) return; // nothing new: a heartbeat every 4 s
    last = body;
    lastAt = now;
    if (ws && ws.readyState === 1) {
      ws.send(body);
    } else if (fails >= 3) {
      // No WebSocket on the app's side: plain POST (text/plain needs no preflight).
      fetch(`http://${BASE}/bridge`, { method: "POST", headers: { "Content-Type": "text/plain" }, body })
        .catch(() => {});
    }
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
