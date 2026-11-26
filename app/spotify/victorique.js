// Victorique · ponte do Spicetify
// Gerado pelo assistente Victorique (app/spotify/spicetify.py). Não edite à mão:
// reinstale pelas Configurações → Na área de trabalho.
// Conta ao app, só no seu computador (127.0.0.1), onde ficam os painéis, as abas,
// as capas e as faixas da página do Spotify e qual música está tocando, e faz o
// que você pede nos chats da Victorique (tocar, pausar, buscar, fila, volume...).
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

  // Spotify's own player (Spicetify.Platform.PlayerAPI) is there from the start;
  // Spicetify.Player is only complete once Spicetify finishes loading, which can
  // take a while after Spotify opens.
  function playerApi() {
    return attempt(() => Spicetify.Platform.PlayerAPI, null);
  }

  function playerData() {
    const api = playerApi();
    return (api && api._state) || attempt(() => Spicetify.Player.data, null) || {};
  }

  function isPlaying() {
    const data = playerData();
    if (typeof data.isPaused === "boolean") return !data.isPaused;
    return attempt(() => !!Spicetify.Player.isPlaying(), false);
  }

  function track() {
    const data = playerData();
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
    return {
      token: TOKEN,
      view: { w: window.innerWidth, h: window.innerHeight },
      elements: elements(),
      track: track(),
      playing: isPlaying(),
    };
  }

  // ---- What the chats ask (play, pause, search...): app/spotify/control.py ----
  // Requests only come over the WebSocket the app accepted with the token.
  const URI = /^spotify:(track|album|artist|playlist|show|episode):[A-Za-z0-9]{22}$/;
  const SEARCHES = {
    track: "searchTracks", artist: "searchArtists", album: "searchAlbums",
    playlist: "searchPlaylists", show: "searchPodcasts", episode: "searchEpisodes",
  };
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
  const clamp = (n, low, high) => Math.min(high, Math.max(low, n));
  const fold = s => String(s || "").toLowerCase().normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "").replace(/\s+/g, " ").trim();

  function attempt(read, fallback) {
    try {
      const value = read();
      return value === undefined ? fallback : value;
    } catch (e) {
      return fallback;
    }
  }

  function currentUri() {
    const data = playerData();
    const item = data.item || data.track;
    return item ? String(item.uri || "") : "";
  }

  async function songChange(before, ms) {
    const end = Date.now() + ms;
    while (Date.now() < end) {
      await wait(150);
      const now = currentUri();
      if (now && now !== before) return true;
    }
    return false;
  }

  function nameOf(node) {
    return String(node.name || (node.profile && node.profile.name) || "").slice(0, 200);
  }

  function byOf(node) {
    const a = node.artists;
    const list = Array.isArray(a) ? a : (a && Array.isArray(a.items) ? a.items : []);
    const names = list.map(x => x && (x.name || (x.profile && x.profile.name))).filter(Boolean);
    if (names.length) return names.slice(0, 3).join(", ");
    const owner = (node.ownerV2 && node.ownerV2.data) || node.owner || node.publisher || {};
    return String(owner.name || owner.display_name || "").slice(0, 120);
  }

  // Spotify's results in the order it ranked them, whatever the response's shape.
  function collect(node, want, out, max, depth = 0) {
    if (!node || typeof node !== "object" || depth > 16 || out.length >= max) return;
    if (Array.isArray(node)) {
      for (const x of node) collect(x, want, out, max, depth + 1);
      return;
    }
    const match = typeof node.uri === "string" ? URI.exec(node.uri) : null;
    if (match && match[1] === want) {
      const name = nameOf(node);
      if (name && !out.some(o => o.uri === node.uri)) out.push({ uri: node.uri, type: match[1], name, by: byOf(node) });
      return;
    }
    for (const key of Object.keys(node)) collect(node[key], want, out, max, depth + 1);
  }

  // Right after Spotify opens, Spicetify is still finding its player and queries.
  async function ready(read, ms) {
    const end = Date.now() + ms;
    let value = attempt(read, null);
    while (!value && Date.now() < end) {
      await wait(250);
      value = attempt(read, null);
    }
    return value;
  }

  async function graphQL(def, variables, type, limit) {
    const request = await ready(() => Spicetify.Platform.GraphQLLoader || Spicetify.GraphQL.Request, 10000);
    if (!request) throw new Error("sem GraphQL.Request");
    const res = await request(def, variables);
    if (res && res.errors && res.errors.length && !res.data) {
      throw new Error(String(res.errors[0].message || "erro na busca").slice(0, 120));
    }
    const out = [];
    collect(res && res.data, type, out, limit);
    return out;
  }

  // Spotify's own search. The search page's queries (searchTracks...) only
  // load once that page is opened; the search box's (searchSuggestions) is
  // there from the start and ranks tracks, artists, albums and playlists.
  function searchesByGraphQL(type) {
    const defs = (Spicetify.GraphQL && Spicetify.GraphQL.Definitions) || {};
    const out = [];
    const own = defs[SEARCHES[type]];
    if (own) {
      out.push((query, limit) => graphQL(own, {
        searchTerm: query, offset: 0, limit, numberOfTopResults: limit,
        includeAudiobooks: false, includeArtistHasConcertsField: false, includePreReleases: true,
        includeAlbumPreReleases: false, includeAuthors: false, includeEpisodeContentRatingsV2: false,
        includeLocalConcertsField: false,
      }, type, limit));
    }
    if (defs.searchSuggestions) {
      out.push((query, limit) => graphQL(defs.searchSuggestions, {
        query, limit: 30, numberOfTopResults: 30, offset: 0,
        includeAuthors: false, includeAlbumPreReleases: false, includeEpisodeContentRatingsV2: false,
      }, type, limit));
    }
    return out;
  }

  async function webToken() {
    const platform = Spicetify.Platform || {};
    const auth = platform.AuthorizationAPI;
    const found = [
      () => platform.Session && platform.Session.accessToken,
      () => auth && auth.getState && auth.getState().token.accessToken,
      () => auth && auth._state && auth._state.token.accessToken,
    ].map(read => attempt(read, "")).find(Boolean);
    if (found) return found;
    try {
      const t = auth && auth._tokenProvider && await auth._tokenProvider();
      return (t && t.accessToken) || "";
    } catch (e) {
      return "";
    }
  }

  // The Web API with Spotify's own login, if Spotify's own queries change.
  async function searchWeb(query, type, limit) {
    const url = `https://api.spotify.com/v1/search?q=${encodeURIComponent(query)}&type=${type}&limit=${limit}`;
    let res;
    if (Spicetify.CosmosAsync) {
      res = await Spicetify.CosmosAsync.get(url);
    } else {
      const token = await webToken();
      if (!token) throw new Error("sem token da Web API");
      const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      if (!r.ok) throw new Error(`Web API ${r.status}`);
      res = await r.json();
    }
    const out = [];
    collect(res, type, out, limit);
    return out;
  }

  async function search(query, type, limit) {
    const problems = [];
    let answered = false;
    for (const how of [...searchesByGraphQL(type), (q, n) => searchWeb(q, type, n)]) {
      try {
        const found = await how(query, limit);
        if (found.length) return found;
        answered = true;
      } catch (e) {
        problems.push(String((e && e.message) || e).slice(0, 120));
      }
    }
    if (!answered) {
      const defs = Object.keys((Spicetify.GraphQL && Spicetify.GraphQL.Definitions) || {})
        .filter(k => /^search/.test(k)).slice(0, 6).join(",") || "nenhuma";
      throw new Error(`a busca do Spotify falhou (${problems.join("; ")}; buscas carregadas: ${defs})`);
    }
    return [];
  }

  // One of the user's own playlists (or ones they saved), by name.
  async function myPlaylist(query) {
    const api = Spicetify.Platform && Spicetify.Platform.RootlistAPI;
    if (!api || !api.getContents) return null;
    const all = [];
    collect(await api.getContents(), "playlist", all, 500);
    const q = fold(query);
    return all.find(p => fold(p.name) === q) || all.find(p => fold(p.name).startsWith(q)) ||
      all.find(p => fold(p.name).includes(q)) || null;
  }

  async function likedUri() {
    let user = attempt(() => Spicetify.Platform.username, "");
    if (!user) {
      try { user = (await Spicetify.Platform.UserAPI.getUser()).username; } catch (e) { /* below */ }
    }
    if (!user) throw new Error("não achei o usuário do Spotify");
    return `spotify:user:${encodeURIComponent(user)}:collection`;
  }

  async function resolve(args) {
    if (args.uri) {
      const match = URI.exec(String(args.uri));
      if (!match) throw new Error("link do Spotify inválido");
      return { chosen: { uri: match[0], type: match[1], name: "", by: "" }, others: [] };
    }
    const type = String(args.type || "track");
    if (type === "liked") {
      return { chosen: { uri: await likedUri(), type: "liked", name: "Músicas Curtidas", by: "" }, others: [] };
    }
    if (!SEARCHES[type]) throw new Error("tipo inválido");
    const query = String(args.query || "").trim().slice(0, 200);
    if (!query) throw new Error("faltou dizer o que procurar");
    if (type === "playlist") {
      const mine = await myPlaylist(query).catch(() => null);
      if (mine) return { chosen: { ...mine, mine: true }, others: [] };
    }
    const found = await search(query, type, 5);
    if (!found.length) throw new Error(`nada encontrado no Spotify para "${query}"`);
    return { chosen: found[0], others: found.slice(1, 4) };
  }

  function nowPlaying() {
    const t = track();
    return t ? { ...t, playing: isPlaying() } : null;
  }

  function volume() {
    return attempt(() => Spicetify.Platform.PlaybackAPI._volume, null) ??
      attempt(() => Spicetify.Player.getVolume(), null);
  }

  function queueState() {
    const q = attempt(() => playerApi()._queue, null);
    return (q && (q._state || q._queue)) || attempt(() => Spicetify.Queue, null) || {};
  }

  async function liked(uri) {
    const library = attempt(() => Spicetify.Platform.LibraryAPI, null);
    if (uri && library && library.contains) {
      try {
        const [yes] = await library.contains(uri);
        return !!yes;
      } catch (e) { /* below */ }
    }
    const item = playerData().item || {};
    return item.metadata ? item.metadata["collection.in_collection"] === "true" : null;
  }

  async function state() {
    const data = playerData();
    const seconds = ms => (typeof ms === "number" && isFinite(ms) ? Math.round(ms / 1000) : null);
    const position = data.isPaused ? data.positionAsOfTimestamp
      : (data.positionAsOfTimestamp || 0) + (Date.now() - (data.timestamp || Date.now()));
    const next = attempt(() => (queueState().nextTracks || []).slice(0, 5).map(t => {
      const c = (t && t.contextTrack) || t || {};
      const m = c.metadata || {};
      return { title: String(m.title || ""), artist: String(m.artist_name || "") };
    }).filter(t => t.title), []);
    const level = volume();
    return {
      now: nowPlaying(),
      uri: currentUri(),
      progress: seconds(position),
      duration: seconds(data.duration),
      volume: typeof level === "number" ? Math.round(level * 100) : null,
      shuffle: typeof data.shuffle === "boolean" ? data.shuffle : null,
      repeat: [0, 1, 2].includes(data.repeat) ? data.repeat : null,
      liked: await liked(currentUri()),
      context: String((data.context && data.context.uri) || ""),
      next,
    };
  }

  async function settled(ms) {
    await wait(ms);
    return state();
  }

  async function skip(go, ms) {
    const before = currentUri();
    await go();
    await songChange(before, ms);
    return settled(100);
  }

  const COMMANDS = {
    state: async () => state(),
    search: async a => ({
      items: await search(String(a.query || "").trim().slice(0, 200),
        SEARCHES[a.type] ? a.type : "track", clamp(Number(a.limit) || 5, 1, 10)),
    }),
    play: async a => {
      const pick = await resolve(a);
      const before = currentUri();
      await playerApi().play({ uri: pick.chosen.uri }, {}, {});
      await songChange(before, 4000);
      await wait(250);
      return { ...pick, now: nowPlaying() };
    },
    queue: async a => {
      const pick = await resolve(a);
      if (pick.chosen.type !== "track" && pick.chosen.type !== "episode") {
        throw new Error("só músicas e episódios entram na fila");
      }
      const q = playerApi()._queue;
      if (q && q.addToQueue) await q.addToQueue([{ uri: pick.chosen.uri }]);
      else await Spicetify.addToQueue([{ uri: pick.chosen.uri }]);
      return pick;
    },
    pause: async () => { await playerApi().pause(); return settled(200); },
    resume: async () => { await playerApi().resume(); return settled(200); },
    toggle: async () => {
      await (isPlaying() ? playerApi().pause() : playerApi().resume());
      return settled(200);
    },
    next: async () => skip(() => playerApi().skipToNext(), 3000),
    previous: async () => skip(() => playerApi().skipToPrevious(), 1500),
    volume: async a => {
      const now = volume();
      const level = typeof a.level === "number" ? a.level / 100
        : (typeof now === "number" ? now : 0.5) + (Number(a.delta) || 0) / 100;
      await Spicetify.Platform.PlaybackAPI.setVolume(clamp(level, 0, 1));
      return settled(150);
    },
    shuffle: async a => {
      await playerApi().setShuffle(typeof a.on === "boolean" ? a.on : !playerData().shuffle);
      return settled(150);
    },
    repeat: async a => {
      await playerApi().setRepeat([0, 1, 2].includes(a.mode) ? a.mode : ((playerData().repeat || 0) + 1) % 3);
      return settled(150);
    },
    like: async a => {
      const uri = currentUri();
      if (!uri) throw new Error("nada tocando para curtir");
      const library = Spicetify.Platform.LibraryAPI;
      await (a.on !== false ? library.add({ uris: [uri] }) : library.remove({ uris: [uri] }));
      return settled(300);
    },
  };

  async function obey(msg, socket) {
    let reply;
    try {
      if (!Object.prototype.hasOwnProperty.call(COMMANDS, msg.cmd)) throw new Error("pedido desconhecido");
      if (!await ready(() => Spicetify.Platform.PlayerAPI, 10000)) throw new Error("o player do Spotify ainda não carregou");
      const args = msg.args && typeof msg.args === "object" ? msg.args : {};
      reply = { ok: true, result: await COMMANDS[msg.cmd](args) };
    } catch (e) {
      reply = { ok: false, error: String((e && e.message) || e).slice(0, 300) };
    }
    reply.token = TOKEN;
    reply.reply = msg.id;
    if (socket.readyState === 1) socket.send(JSON.stringify(reply));
  }

  let ws = null;
  let fails = 0;
  let last = "";
  let lastAt = 0;

  function connect() {
    let socket;
    try {
      socket = new WebSocket(`ws://${BASE}/ws?t=${encodeURIComponent(TOKEN)}`);
    } catch (e) {
      ws = null;
      fails++;
      setTimeout(connect, 30000);
      return;
    }
    ws = socket;
    socket.onopen = () => { fails = 0; last = ""; send(); };
    socket.onclose = () => {
      if (ws === socket) ws = null;
      fails++;
      setTimeout(connect, Math.min(30000, 2000 * fails));
    };
    socket.onerror = () => {};
    socket.onmessage = ev => {
      let msg = null;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      if (msg && typeof msg.cmd === "string" && typeof msg.id === "string") obey(msg, socket);
    };
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
