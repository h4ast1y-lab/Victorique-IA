/*
 * Biblioteca: o salão em pixel art onde a Victorique passeia entre as
 * estantes. Cada seção é uma pasta (uma estante) e cada arquivo é um livro.
 *
 * O que ela faz nos arquivos (app/library/activity.py) vira cena: vai até a
 * estante e lê, consulta, escreve, carrega o livro para outra estante ou
 * para o carrinho da Reserva, e devolve quando algo é desfeito. Com a aba
 * fechada as ações ficam na fila (contador na aba) e são encenadas quando
 * ela abre. Sem nada para fazer, ela perambula, lê, toma chá, pensa, cochila.
 *
 * Usa de app.js: api, toast, escape, chatInput, autoGrow, sendMessage,
 * isGenerating, showSidebarTab.
 */
(function () {
  'use strict';

  const byId = (id) => document.getElementById(id);

  // ---------- Mundo (unidades de desenho; o canvas escala pela altura) ----------
  const DH = 360;            // altura de desenho
  const FLOOR = 300;         // encontro da parede com o chão
  const FEET = 326;          // onde ela pisa
  const CASE_TOP = 96;
  const CORNICE = 10;
  const ROWS = 4;
  const ROW_H = 44;
  const BOARD = 4;
  const CASE_GAP = 30;
  const SPRITE_SCALE = 0.5;
  const WALK_SPEED = 62;     // unidades por segundo
  const FPS = 6;
  const MAX_QUEUE = 14;
  const MIN_VIEW_W = 540;    // nunca mostrar menos que isso do salão na horizontal
  const SEQ_KEY = 'victorique.library.seq';
  const SERIF = '"Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif';

  const C = {
    wall: '#2b211b', panel: '#30251e', panelLine: '#3a2d24', wainscot: '#241a14',
    wood: '#5b3d28', woodLight: '#7a5435', woodDark: '#3b281b', back: '#21170f',
    floor: '#3f2d1e', floorLine: '#33241a', rug: '#2f4a3b', rugDark: '#263d31', rugEdge: '#b8975a',
    brass: '#c9a25a', brassDark: '#8f6f37', ink: '#2a1d10',
  };

  // Lombadas: cor pelo tipo de arquivo.
  const BOOK_COLORS = [
    [['pdf'], '#8e3b35'],
    [['txt', 'md', 'rtf', 'log'], '#c9b68a'],
    [['doc', 'docx', 'odt'], '#3d5a8a'],
    [['xls', 'xlsx', 'csv', 'ods'], '#4f7a4a'],
    [['ppt', 'pptx', 'odp', 'key'], '#b8683a'],
    [['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg', 'heic'], '#3f8c88'],
    [['mp3', 'wav', 'flac', 'ogg', 'm4a', 'aac'], '#6e4a7e'],
    [['mp4', 'mkv', 'avi', 'mov', 'webm', 'wmv'], '#4a4f8c'],
    [['zip', 'rar', '7z', 'tar', 'gz', 'iso'], '#7a5a3a'],
    [['py', 'js', 'ts', 'html', 'css', 'json', 'java', 'c', 'cpp', 'cs', 'go', 'rs', 'ipynb'], '#5f6b75'],
    [['exe', 'msi', 'bat', 'cmd', 'ps1', 'lnk'], '#6b4545'],
  ];

  const IDLE_LABELS = {
    walk: 'Passeando entre as estantes',
    read: 'Lendo algo da estante',
    tea: 'Tomando chá',
    think: 'Pensando em algum mistério',
    doze: 'Cochilando entre os livros',
    stand: 'Olhando as estantes',
  };

  // ---------- Estado ----------
  let isOpen = false;
  let shelves = [];          // seções com livros e posição no salão
  let world = { width: 600, door: 38, window: [80, 150], cart: 400 };
  let cart = [];             // livros na Reserva
  let atlas = null;
  let atlasImg = null;
  let atlasPromise = null;
  let canvas = null;
  let ctx = null;
  let view = { k: 1, dpr: 1, w: 0, h: 0, oy: 0, camX: 0, manualUntil: 0 };
  let rafId = 0;
  let lastTime = 0;
  let hover = null;
  let selected = null;
  let refreshTimer = 0;
  let pollTimer = 0;
  let pollCount = 0;
  let lastSeq = readSeq();
  let notifyTimer = 0;
  let loadingSections = null;
  const queue = [];
  const motes = [];
  const reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const her = {
    x: 120, facing: 1, anim: 'stand', t0: 0, carrying: null,
    task: null, idleUntil: 0, label: IDLE_LABELS.stand,
  };

  // ---------- Utilidades ----------
  function readSeq() {
    try {
      const v = localStorage.getItem(SEQ_KEY);
      return v === null ? null : Number(v) || 0;
    } catch (_) { return null; }
  }

  function writeSeq(value) {
    lastSeq = value;
    try { localStorage.setItem(SEQ_KEY, String(value)); } catch (_) { /* storage off */ }
  }

  function hash(text) {
    let h = 2166136261;
    for (let i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }

  function bookColor(ext) {
    for (const [exts, color] of BOOK_COLORS) if (exts.includes(ext)) return color;
    return '#8a7f70';
  }

  function shade(hex, amount) {
    const n = parseInt(hex.slice(1), 16);
    const f = (c) => Math.max(0, Math.min(255, Math.round(c + amount)));
    return `rgb(${f(n >> 16)}, ${f((n >> 8) & 255)}, ${f(n & 255)})`;
  }

  function baseName(path) {
    return String(path || '').split(/[\\/]/).filter(Boolean).pop() || String(path || '');
  }

  function humanSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    const units = ['KB', 'MB', 'GB', 'TB'];
    let v = bytes / 1024;
    let i = 0;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return `${v >= 10 ? Math.round(v) : v.toFixed(1).replace('.', ',')} ${units[i]}`;
  }

  function plural(n, one, many) { return `${n} ${n === 1 ? one : many}`; }

  // ---------- Livros e estantes ----------
  function makeBook(file) {
    const ext = (file.ext || (file.name.includes('.') ? file.name.split('.').pop() : '')).toLowerCase();
    const h = hash(file.name || '');
    const size = Number(file.size) || 0;
    const height = size < 10240 ? 26 : size < 1048576 ? 30 : size < 52428800 ? 34 : 38;
    return {
      name: file.name, path: file.path || '', ext, size, modified: file.modified || 0,
      color: bookColor(ext), w: 6 + (h % 3) * 2, h: height, band: h % 4, x: 0, y: 0, lift: 0, sparkle: 0,
    };
  }

  function layoutShelf(shelf) {
    const left = shelf.x + 7;
    const right = shelf.x + shelf.w - 7;
    let row = 0;
    let cx = left;
    shelf.overflow = 0;
    for (const book of shelf.books) {
      if (cx + book.w > right) { row++; cx = left; }
      if (row >= ROWS) { book.hidden = true; shelf.overflow++; continue; }
      book.hidden = false;
      const bottom = CASE_TOP + CORNICE + row * (ROW_H + BOARD) + ROW_H;
      book.x = cx;
      book.y = bottom - book.h;
      cx += book.w + 1;
    }
  }

  function layoutWorld() {
    let x = 176;
    for (const shelf of shelves) {
      const total = shelf.books.reduce((sum, b) => sum + b.w + 1, 0);
      shelf.w = Math.max(104, Math.min(340, Math.ceil(total / ROWS) + 22));
      shelf.x = x;
      x += shelf.w + CASE_GAP;
      layoutShelf(shelf);
    }
    if (!shelves.length) x += 220;
    world.cart = x + 6;
    world.width = world.cart + 72 + 34;
    her.x = Math.min(her.x, world.width - 40);
  }

  function shelfById(id) { return shelves.find(s => s.id === id) || null; }
  function shelfCenter(shelf) { return shelf.x + shelf.w / 2; }

  function findBook(shelf, name) {
    if (!shelf) return -1;
    return shelf.books.findIndex(b => b.name === name);
  }

  // ---------- Dados ----------
  async function loadSections() {
    if (loadingSections) return loadingSections;
    loadingSections = (async () => {
      let list = [];
      try {
        list = await api('/api/library/sections');
      } catch (err) {
        toast(`Não abri a Biblioteca: ${err.message}`, 'error');
      }
      const full = await Promise.all(list.map(async (s) => {
        try {
          const data = await api(`/api/library/sections/${encodeURIComponent(s.id)}/books`);
          return { ...s, files: data.files || [], total: data.total || 0 };
        } catch (_) {
          return { ...s, files: [], total: 0 };
        }
      }));
      shelves = full.map(s => ({
        id: s.id, name: s.name, path: s.path, kind: s.kind, exists: s.exists, total: s.total,
        books: s.files.map(makeBook), x: 0, w: 0, glow: 0, overflow: 0,
      }));
      layoutWorld();
      renderSectionList();
      renderCount();
      byId('libraryEmpty').hidden = shelves.length > 0;
    })();
    try { await loadingSections; } finally { loadingSections = null; }
  }

  function scheduleRefresh() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(() => {
      if (her.task && her.task.scene) { scheduleRefresh(); return; }  // after the scene
      loadSections();
    }, 1500);
  }

  function loadAtlas() {
    if (atlasPromise) return atlasPromise;
    atlasPromise = Promise.all([
      api('/api/mascot/atlas.json'),
      new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = reject;
        img.src = '/api/mascot/atlas';
      }),
    ]).then(([data, img]) => { atlas = data; atlasImg = img; })
      .catch(() => { atlasPromise = null; });
    return atlasPromise;
  }

  // ---------- Atividade (fila de cenas) ----------
  function hasSection(ev) { return !!(ev.src_section || ev.dst_section); }

  async function poll() {
    let data;
    try {
      data = await api(`/api/library/activity?since=${lastSeq || 0}`);
    } catch (_) { return; }
    if (lastSeq === null) { writeSeq(data.last); return; }      // first run: nothing to replay
    if (data.last < lastSeq) {                                   // the app restarted
      writeSeq(0);
      try { data = await api('/api/library/activity?since=0'); } catch (_) { return; }
    }
    const events = (data.events || []).filter(hasSection);
    if (isOpen) {
      writeSeq(data.last);
      setBadge(0);
      enqueue(events);
    } else {
      setBadge(events.length);
    }
  }

  function setBadge(n) {
    const badge = byId('libraryBadge');
    if (!badge) return;
    badge.hidden = !n;
    badge.textContent = n > 9 ? '9+' : String(n);
    badge.title = n ? `${plural(n, 'coisa nova', 'coisas novas')} para ela mostrar na Biblioteca` : '';
  }

  function enqueue(events) {
    for (const ev of events) {
      const prev = queue[queue.length - 1];
      // Many listings in a row of the same shelf are one visit.
      if (prev && ev.kind === 'list' && prev.kind === 'list' && prev.src_section === ev.src_section) continue;
      queue.push(ev);
    }
    while (queue.length > MAX_QUEUE) queue.shift();
    if (queue.length && her.task && !her.task.scene) her.task = null;  // drop idling
  }

  // ---------- Ela: tarefas ----------
  function setAnim(name, now) {
    if (her.anim !== name) { her.anim = name; her.t0 = now; }
  }

  function startTask(task, now) {
    task.i = 0;
    task.stepStart = now;
    her.task = task;
    setLabel(task.label);
  }

  function setLabel(text) {
    if (her.label === text) return;
    her.label = text;
    const el = byId('libraryStatus');
    if (el) el.textContent = text;
  }

  const walkTo = (fn) => ({ walk: fn });
  const play = (anim, dur) => ({ anim, dur });
  const run = (fn) => ({ fn });

  function sectionName(id) {
    const shelf = shelfById(id);
    return shelf ? shelf.name : null;
  }

  function takeBook(shelf, name, fallbackExt) {
    let book = null;
    if (shelf) {
      const i = findBook(shelf, name);
      if (i >= 0) {
        book = shelf.books.splice(i, 1)[0];
        layoutShelf(shelf);
      }
    }
    return book || makeBook({ name, ext: fallbackExt, size: 50000 });
  }

  function putBook(shelf, book, newName) {
    if (newName) book.name = newName;
    book.sparkle = 1;
    if (shelf) {
      shelf.books.unshift(book);
      layoutShelf(shelf);
    }
  }

  function placeOf(sectionId, path) {
    // Where a book comes from or goes to: a shelf, the Reserva's cart or the door.
    const shelf = shelfById(sectionId);
    if (shelf) return { shelf, x: () => shelfCenter(shelf), name: shelf.name };
    if (/_Quarentena/i.test(path || '')) return { cart: true, x: () => world.cart + 36, name: 'a Reserva' };
    return { door: true, x: () => world.door + 30, name: null };
  }

  function scene(ev) {
    const name = ev.name || baseName(ev.dst || ev.src);
    const ext = (name.split('.').pop() || '').toLowerCase();
    const src = placeOf(ev.src_section, ev.src);
    const dst = placeOf(ev.dst_section, ev.dst);
    const glow = (shelf, secs) => run(() => { if (shelf) shelf.glow = secs; });

    if (ev.kind === 'read' || ev.kind === 'list' || ev.kind === 'write') {
      const shelf = src.shelf;
      if (!shelf) return null;
      if (ev.kind === 'list') {
        return {
          label: `Consultando a estante ${shelf.name}`,
          steps: [walkTo(src.x), glow(shelf, 2), play('glance', 1.6), play('think', 1)],
        };
      }
      if (ev.kind === 'write') {
        return {
          label: `Escrevendo ${name} em ${shelf.name}`,
          steps: [walkTo(src.x), play('think', 1.4), run(() => {
            const i = findBook(shelf, name);
            if (i >= 0) { shelf.books[i].sparkle = 1; } else { putBook(shelf, makeBook({ name, ext, size: 2000 })); }
          }), play('glance', 0.8)],
        };
      }
      let book = null;
      return {
        label: `Lendo ${name}, de ${shelf.name}`,
        steps: [
          walkTo(src.x),
          run(() => { const i = findBook(shelf, name); book = i >= 0 ? shelf.books[i] : null; if (book) book.lift = 1; }),
          play('read', 4.2),
          play('close_book', 0.9),
          run(() => { if (book) book.lift = 0; }),
        ],
      };
    }

    if (ev.kind === 'rename') {
      const shelf = src.shelf || dst.shelf;
      if (!shelf) return null;
      const oldName = baseName(ev.src);
      return {
        label: `Renomeando um livro em ${shelf.name}: agora é ${name}`,
        steps: [walkTo(() => shelfCenter(shelf)), play('think', 1.3), run(() => {
          const i = findBook(shelf, oldName);
          if (i >= 0) { shelf.books[i].name = name; shelf.books[i].sparkle = 1; }
        }), play('glance', 0.6)],
      };
    }

    if (ev.kind === 'move' || ev.kind === 'reserve' || ev.kind === 'undo') {
      if (src.door && dst.door) return null;
      const oldName = baseName(ev.src);
      let label;
      if (ev.kind === 'reserve' || dst.cart) label = `Levando ${oldName} para a Reserva`;
      else if (ev.kind === 'undo') label = `Desfazendo: devolvendo ${name} ${dst.name ? `para ${dst.name}` : 'para fora da Biblioteca'}`;
      else if (src.door) label = `Trazendo ${name} para ${dst.name}`;
      else if (dst.door) label = `Levando ${oldName} para fora da Biblioteca`;
      else label = `Levando ${oldName} de ${src.name} para ${dst.name}`;
      return {
        label,
        steps: [
          walkTo(src.x),
          play('glance', 0.5),
          run(() => {
            if (src.cart) {
              const i = cart.findIndex(b => b.name === oldName);
              her.carrying = i >= 0 ? cart.splice(i, 1)[0] : makeBook({ name: oldName, ext, size: 50000 });
            } else {
              her.carrying = takeBook(src.shelf, oldName, ext);
            }
          }),
          walkTo(dst.x),
          run(() => {
            const book = her.carrying;
            her.carrying = null;
            if (!book) return;
            if (dst.cart) { book.name = name; cart.unshift(book); cart.splice(8); } else putBook(dst.shelf, book, name);
          }),
          play('glance', 0.6),
        ],
      };
    }
    return null;
  }

  function idleTask(now) {
    const r = Math.random();
    const shelf = shelves.length ? shelves[Math.floor(Math.random() * shelves.length)] : null;
    const night = new Date().getHours() >= 22 || new Date().getHours() < 6;
    if (shelf && r < 0.38) {
      return { label: `Lendo algo da estante ${shelf.name}`, steps: [
        walkTo(() => shelfCenter(shelf) + (Math.random() * 30 - 15)),
        play('read', 5 + Math.random() * 4), play('close_book', 0.9), play('stand', 1.5)] };
    }
    if (r < (night ? 0.62 : 0.5)) return { label: IDLE_LABELS.doze, steps: [play('doze', 6 + Math.random() * 4), play('stand', 1)] };
    if (r < 0.68) return { label: IDLE_LABELS.tea, steps: [play('tea', 5 + Math.random() * 3), play('stand', 1.2)] };
    if (r < 0.8) return { label: IDLE_LABELS.think, steps: [play('think', 2.5 + Math.random() * 2), play('stand', 1)] };
    const target = 70 + Math.random() * Math.max(40, world.width - 140);
    return { label: IDLE_LABELS.walk, steps: [walkTo(() => target), play('stand', 2 + Math.random() * 3)] };
  }

  function nextTask(now) {
    while (queue.length) {
      const ev = queue.shift();
      const task = scene(ev);
      if (task) {
        task.scene = true;
        startTask(task, now);
        scheduleRefresh();
        return;
      }
    }
    startTask(idleTask(now), now);
  }

  function update(dt, now) {
    if (!her.task) nextTask(now);
    const task = her.task;
    const step = task.steps[task.i];
    if (!step) {
      her.task = null;
      setAnim('stand', now);
      return;
    }
    const advance = () => { task.i++; task.stepStart = now; };
    if (step.walk) {
      const target = Math.max(24, Math.min(world.width - 24, step.walk()));
      const dx = target - her.x;
      if (Math.abs(dx) < 1.5) {
        her.x = target;
        advance();
      } else {
        her.facing = dx > 0 ? 1 : -1;
        setAnim('walk', now);
        her.x += Math.sign(dx) * Math.min(Math.abs(dx), WALK_SPEED * dt);
      }
    } else if (step.anim) {
      setAnim(step.anim, now);
      if (now - task.stepStart >= step.dur) advance();
    } else if (step.fn) {
      try { step.fn(); } catch (err) { console.error(err); }
      advance();
    }
    for (const shelf of shelves) {
      if (shelf.glow > 0) shelf.glow = Math.max(0, shelf.glow - dt);
      for (const book of shelf.books) if (book.sparkle > 0) book.sparkle = Math.max(0, book.sparkle - dt * 0.7);
    }
    if (task === her.task && task.i >= task.steps.length) {
      her.task = null;
    }
  }

  // ---------- Desenho ----------
  function rect(x, y, w, h, color) {
    ctx.fillStyle = color;
    ctx.fillRect(Math.round(x), Math.round(y), Math.round(w), Math.round(h));
  }

  function skyColors() {
    const hour = new Date().getHours();
    if (hour >= 7 && hour < 17) return { top: '#86a6c2', bottom: '#c9d8e2', night: false };
    if (hour >= 17 && hour < 19 || hour >= 6 && hour < 7) return { top: '#6a4b6e', bottom: '#d98c5f', night: false };
    return { top: '#121a2e', bottom: '#24325a', night: true };
  }

  function drawWall(x0, x1) {
    const top = -view.oy - 2;
    rect(x0, top, x1 - x0, FLOOR - top, C.wall);
    const start = Math.floor(x0 / 40) * 40;
    for (let x = start; x < x1; x += 40) {
      rect(x + 4, 18, 32, 200, C.panel);
      rect(x + 4, 18, 32, 2, C.panelLine);
      rect(x + 4, 216, 32, 2, C.panelLine);
      // A tall window of the stage shows more of the high wall above.
      for (let y = -12; y > top; y -= 128) {
        rect(x + 4, y - 112, 32, 112, C.panel);
        rect(x + 4, y - 112, 32, 2, C.panelLine);
        rect(x + 4, y - 2, 32, 2, C.panelLine);
      }
    }
    rect(x0, 236, x1 - x0, FLOOR - 236, C.wainscot);
    rect(x0, 236, x1 - x0, 3, C.woodDark);
    rect(x0, 8, x1 - x0, 4, C.woodDark);
  }

  function drawWindow(now) {
    const [x0, x1] = world.window;
    const w = x1 - x0;
    const top = 44;
    const bottom = 214;
    const sky = skyColors();
    // Pixel arch: stacked strips that narrow toward the top.
    const steps = [[0, 18], [4, 10], [8, 6], [14, 4], [22, 2]];
    rect(x0 - 6, top - 4, w + 12, bottom - top + 12, C.woodDark);
    const grad = ctx.createLinearGradient(0, top, 0, bottom);
    grad.addColorStop(0, sky.top);
    grad.addColorStop(1, sky.bottom);
    ctx.fillStyle = grad;
    ctx.fillRect(x0, top + 26, w, bottom - top - 26);
    let y = top + 26;
    for (const [inset, h] of steps) {
      y -= h;
      ctx.fillRect(x0 + inset, y, w - inset * 2, h);
    }
    if (sky.night) {
      for (let i = 0; i < 14; i++) {
        const sx = x0 + 6 + (hash('s' + i) % (w - 12));
        const sy = top + 8 + (hash('y' + i) % 120);
        const tw = reducedMotion ? 1 : 0.55 + 0.45 * Math.sin(now * 1.3 + i);
        ctx.globalAlpha = tw;
        rect(sx, sy, 2, 2, '#efe7cf');
      }
      ctx.globalAlpha = 1;
      rect(x0 + w - 26, top + 30, 10, 10, '#efe7c8');
      rect(x0 + w - 22, top + 30, 6, 8, sky.bottom);
    }
    // Mullions
    rect(x0 + w / 2 - 2, top, 4, bottom - top, C.wood);
    for (const my of [top + 62, top + 116]) rect(x0, my, w, 3, C.wood);
    rect(x0 - 8, bottom + 4, w + 16, 6, C.woodLight);
  }

  function drawDoor() {
    const x = world.door - 22;
    rect(x - 4, 146, 52, 154, C.woodDark);
    rect(x, 150, 44, 150, C.wood);
    rect(x + 5, 158, 15, 60, C.woodDark);
    rect(x + 24, 158, 15, 60, C.woodDark);
    rect(x + 5, 226, 15, 64, C.woodDark);
    rect(x + 24, 226, 15, 64, C.woodDark);
    rect(x + 36, 228, 4, 4, C.brass);
  }

  function drawLamp(x, now) {
    rect(x - 1, 172, 3, FLOOR - 172, C.brassDark);
    rect(x - 7, FLOOR - 4, 15, 4, C.brassDark);
    rect(x - 9, 160, 19, 12, '#a8623e');
    rect(x - 7, 158, 15, 2, '#c47a4c');
    const flicker = reducedMotion ? 1 : 0.92 + 0.08 * Math.sin(now * 2.1 + x);
    return { x, y: 170, r: 120 * flicker };
  }

  function drawShelf(shelf, now) {
    const { x, w } = shelf;
    const bottom = CASE_TOP + CORNICE + ROWS * (ROW_H + BOARD);
    rect(x - 3, CASE_TOP - 4, w + 6, 8, C.woodLight);
    rect(x, CASE_TOP, w, bottom - CASE_TOP, C.wood);
    rect(x + 5, CASE_TOP + CORNICE, w - 10, bottom - CASE_TOP - CORNICE, C.back);
    for (let r = 0; r < ROWS; r++) {
      const by = CASE_TOP + CORNICE + r * (ROW_H + BOARD) + ROW_H;
      rect(x + 5, by, w - 10, BOARD, C.woodLight);
      rect(x + 5, by + BOARD - 1, w - 10, 1, C.woodDark);
    }
    rect(x, CASE_TOP, 5, bottom - CASE_TOP, C.woodLight);
    rect(x + w - 5, CASE_TOP, 5, bottom - CASE_TOP, C.woodDark);
    for (const book of shelf.books) {
      if (book.hidden) continue;
      const y = book.y - (book.lift ? 5 : 0);
      const isHover = hover && hover.book === book;
      rect(book.x, y, book.w, book.h, isHover ? shade(book.color, 30) : book.color);
      rect(book.x, y, book.w, 2, shade(book.color, 26));
      rect(book.x + book.w - 1, y, 1, book.h, shade(book.color, -28));
      if (book.band) rect(book.x, y + 6 + book.band * 2, book.w, 2, shade(book.color, 45));
      if (book.band === 3) rect(book.x, y + book.h - 7, book.w, 2, shade(book.color, 45));
      if (book.sparkle > 0) {
        ctx.globalAlpha = book.sparkle;
        rect(book.x - 2, y - 4, 2, 2, '#f6e2a8');
        rect(book.x + book.w, y + 3, 2, 2, '#f6e2a8');
        rect(book.x + book.w / 2, y - 7, 2, 2, '#fff3cf');
        ctx.globalAlpha = 1;
      }
      if (selected && selected.book === book) {
        ctx.strokeStyle = C.brass;
        ctx.lineWidth = 1;
        ctx.strokeRect(book.x - 1.5, y - 1.5, book.w + 3, book.h + 3);
      }
    }
    if (!shelf.books.length) {
      ctx.fillStyle = 'rgba(242, 230, 207, 0.35)';
      ctx.font = `italic 8px ${SERIF}`;
      ctx.textAlign = 'center';
      ctx.fillText(shelf.exists ? 'estante vazia' : 'pasta não encontrada', x + w / 2, CASE_TOP + CORNICE + 28);
    }
    if (shelf.glow > 0) {
      ctx.globalAlpha = Math.min(1, shelf.glow) * (0.5 + 0.5 * Math.sin(now * 6));
      ctx.strokeStyle = C.brass;
      ctx.lineWidth = 2;
      ctx.strokeRect(x - 4, CASE_TOP - 6, w + 8, bottom - CASE_TOP + 8);
      ctx.globalAlpha = 1;
    }
    // Brass plaque with the section's name.
    ctx.font = `italic 600 9px ${SERIF}`;
    let label = shelf.name;
    const maxW = w - 10;
    while (ctx.measureText(label).width > maxW - 10 && label.length > 3) label = label.slice(0, -2) + '…';
    const pw = Math.min(maxW, ctx.measureText(label).width + 12);
    const px = Math.round(x + (w - pw) / 2);
    rect(px, CASE_TOP - 20, pw, 14, C.brassDark);
    rect(px + 1, CASE_TOP - 19, pw - 2, 12, C.brass);
    ctx.fillStyle = C.ink;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(label, x + w / 2, CASE_TOP - 13);
    ctx.textBaseline = 'alphabetic';
    if (shelf.overflow) {
      ctx.fillStyle = 'rgba(242, 230, 207, 0.5)';
      ctx.font = `8px ${SERIF}`;
      ctx.fillText(`+${shelf.overflow}`, x + w - 14, bottom - 6);
    }
  }

  function drawCart() {
    const x = world.cart;
    rect(x + 2, 262, 66, 30, C.woodDark);
    rect(x + 4, 264, 62, 26, C.wood);
    for (let i = 0; i < Math.min(cart.length, 8); i++) {
      const b = cart[i];
      rect(x + 8 + (i % 2) * 4, 258 - i * 5, 44, 5, b.color);
      rect(x + 8 + (i % 2) * 4, 258 - i * 5, 44, 1, shade(b.color, 30));
    }
    rect(x + 64, 244, 3, 24, C.brassDark);
    rect(x + 58, 242, 12, 3, C.brassDark);
    rect(x + 10, 292, 8, 8, '#1a120c');
    rect(x + 52, 292, 8, 8, '#1a120c');
    ctx.fillStyle = 'rgba(242, 230, 207, 0.8)';
    ctx.font = `italic 600 8px ${SERIF}`;
    ctx.textAlign = 'center';
    ctx.fillText('Reserva', x + 35, 280);
  }

  function drawFloor(x0, x1) {
    const bottom = view.h / view.k - view.oy + 2;
    rect(x0, FLOOR, x1 - x0, Math.max(DH, bottom) - FLOOR, C.floor);
    for (let y = DH + 22; y < bottom; y += 22) rect(x0, y, x1 - x0, 1, C.floorLine);
    const start = Math.floor(x0 / 48) * 48;
    for (let x = start; x < x1; x += 48) {
      rect(x, FLOOR, 1, Math.max(DH, bottom) - FLOOR, C.floorLine);
    }
    rect(x0, FLOOR + 22, x1 - x0, 1, C.floorLine);
    rect(x0, 312, x1 - x0, 26, C.rug);
    rect(x0, 312, x1 - x0, 2, C.rugEdge);
    rect(x0, 336, x1 - x0, 2, C.rugEdge);
    rect(x0, 318, x1 - x0, 1, C.rugDark);
    rect(x0, 331, x1 - x0, 1, C.rugDark);
  }

  function frameFor(now) {
    if (!atlas) return null;
    let name = her.anim;
    let index;
    if (name === 'stand') {
      // Standing: eyes open, with a quick blink every few seconds.
      const frames = atlas.anims.blink.frames;
      const cycle = (now - her.t0) % 3.6;
      index = cycle > 3.3 ? Math.min(frames.length - 1, Math.floor((cycle - 3.3) * 20)) : 0;
      name = 'blink';
      return { anim: atlas.anims[name], frame: frames[index] };
    }
    const anim = atlas.anims[name] || atlas.anims.blink;
    index = Math.floor((now - her.t0) * FPS) % anim.frames.length;
    return { anim, frame: anim.frames[index] };
  }

  function drawHer(now) {
    ctx.fillStyle = 'rgba(0, 0, 0, 0.28)';
    ctx.beginPath();
    ctx.ellipse(her.x, FEET + 1, 22, 4, 0, 0, Math.PI * 2);
    ctx.fill();
    const f = frameFor(now);
    if (!f || !atlasImg) {
      rect(her.x - 14, FEET - 110, 28, 110, '#1d1a18');
      return;
    }
    const [sx, sy, sw, sh, ax, ay] = f.frame;
    const s = SPRITE_SCALE;
    const mirror = f.anim.facing === 'left' ? her.facing > 0 : f.anim.facing === 'right' ? her.facing < 0 : false;
    ctx.save();
    ctx.translate(Math.round(her.x), FEET);
    if (mirror) ctx.scale(-1, 1);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(atlasImg, sx, sy, sw, sh, -ax * s, -ay * s, sw * s, sh * s);
    ctx.restore();
    if (her.carrying) {
      const b = her.carrying;
      const bx = her.x + her.facing * 12 - 6;
      rect(bx, FEET - 66, 12, 16, b.color);
      rect(bx, FEET - 66, 12, 2, shade(b.color, 30));
      rect(bx + 2, FEET - 62, 8, 1, shade(b.color, 45));
    }
  }

  function drawLights(lights) {
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    for (const l of lights) {
      const g = ctx.createRadialGradient(l.x, l.y, 4, l.x, l.y, l.r);
      g.addColorStop(0, 'rgba(255, 190, 110, 0.22)');
      g.addColorStop(1, 'rgba(255, 190, 110, 0)');
      ctx.fillStyle = g;
      ctx.fillRect(l.x - l.r, l.y - l.r, l.r * 2, l.r * 2);
    }
    ctx.restore();
  }

  function drawMotes(dt, lights) {
    if (reducedMotion || !lights.length) return;
    while (motes.length < 16) {
      const l = lights[Math.floor(Math.random() * lights.length)];
      motes.push({ x: l.x + (Math.random() - 0.5) * 120, y: 150 + Math.random() * 140, v: 2 + Math.random() * 4, a: 0 });
    }
    for (const m of motes) {
      m.y -= m.v * dt;
      m.x += Math.sin(m.y / 12) * 0.08;
      m.a = Math.min(0.55, m.a + dt * 0.3);
      ctx.globalAlpha = m.a * Math.max(0, (m.y - 60) / 120);
      rect(m.x, m.y, 1.5, 1.5, '#ffe2b0');
    }
    ctx.globalAlpha = 1;
    for (let i = motes.length - 1; i >= 0; i--) if (motes[i].y < 60) motes.splice(i, 1);
  }

  function render(now, dt) {
    const { k, dpr, w, h } = view;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = C.wall;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    const viewW = w / k;
    if (world.width <= viewW) {
      view.camX = -(viewW - world.width) / 2;
    } else if (now > view.manualUntil) {
      const target = Math.max(0, Math.min(world.width - viewW, her.x - viewW / 2));
      view.camX += (target - view.camX) * Math.min(1, dt * 2.5);
    }
    const s = k * dpr;
    ctx.setTransform(s, 0, 0, s, -view.camX * s, view.oy * s);
    const x0 = view.camX - 2;
    const x1 = view.camX + viewW + 2;
    drawWall(Math.min(x0, 0), Math.max(x1, world.width));
    drawWindow(now);
    drawDoor();
    const lights = [];
    let prevEnd = 160;
    for (const shelf of shelves) {
      if (shelf.x - prevEnd > 12) lights.push(drawLamp((prevEnd + shelf.x) / 2, now));
      prevEnd = shelf.x + shelf.w;
    }
    lights.push(drawLamp(world.cart - 14, now));
    for (const shelf of shelves) drawShelf(shelf, now);
    drawCart();
    drawFloor(Math.min(x0, 0), Math.max(x1, world.width));
    drawHer(now);
    drawLights(lights);
    drawMotes(dt, lights);
    // Vignette, in screen space.
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    const vg = ctx.createRadialGradient(canvas.width / 2, canvas.height * 0.45, canvas.height * 0.3,
      canvas.width / 2, canvas.height * 0.45, Math.max(canvas.width, canvas.height) * 0.75);
    vg.addColorStop(0, 'rgba(0, 0, 0, 0)');
    vg.addColorStop(1, 'rgba(0, 0, 0, 0.45)');
    ctx.fillStyle = vg;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  }

  function frame(t) {
    rafId = 0;
    if (!isOpen) return;
    const now = t / 1000;
    const dt = lastTime ? Math.min(0.1, now - lastTime) : 0.016;
    lastTime = now;
    if (view.w && view.h) {
      update(dt, now);
      render(now, dt);
      if (pointer && !drag) updateHover();   // books move too (taken, put back)
    }
    rafId = requestAnimationFrame(frame);
  }

  function resize() {
    const stage = byId('libraryStage');
    if (!stage || !canvas) return;
    const w = stage.clientWidth;
    const h = stage.clientHeight;
    const dpr = window.devicePixelRatio || 1;
    view.w = w;
    view.h = h;
    view.dpr = dpr;
    // Fit the room's height, but never show less than MIN_VIEW_W of it across;
    // the height left over goes to more wall above and more floor below.
    view.k = Math.max(0.1, Math.min(h / DH, w / MIN_VIEW_W));
    view.oy = Math.max(0, (h / view.k - DH) * 0.62);
    canvas.width = Math.max(1, Math.round(w * dpr));
    canvas.height = Math.max(1, Math.round(h * dpr));
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
  }

  // ---------- Interação ----------
  function worldPoint(e) {
    const r = canvas.getBoundingClientRect();
    return { x: (e.clientX - r.left) / view.k + view.camX, y: (e.clientY - r.top) / view.k - view.oy };
  }

  function screenPoint(x, y) {
    return { x: (x - view.camX) * view.k, y: (y + view.oy) * view.k };
  }

  function hitBook(p) {
    for (const shelf of shelves) {
      if (p.x < shelf.x || p.x > shelf.x + shelf.w) continue;
      for (const book of shelf.books) {
        if (book.hidden) continue;
        const y = book.y - (book.lift ? 5 : 0);
        if (p.x >= book.x && p.x <= book.x + book.w && p.y >= y && p.y <= y + book.h) return { shelf, book };
      }
    }
    return null;
  }

  function hitHer(p) {
    return Math.abs(p.x - her.x) < 22 && p.y > FEET - 118 && p.y < FEET + 4;
  }

  let drag = null;
  let pointer = null;        // last pointer position over the canvas (client coords)

  function onMove(e) {
    pointer = { clientX: e.clientX, clientY: e.clientY };
    // While the user points at the room the camera holds still, so the
    // books don't slide away from under the cursor.
    view.manualUntil = Math.max(view.manualUntil, performance.now() / 1000 + 2.5);
    if (drag) {
      const dx = (e.clientX - drag.x) / view.k;
      if (Math.abs(e.clientX - drag.x) > 3) drag.moved = true;
      if (drag.moved) {
        view.camX = Math.max(0, Math.min(world.width - view.w / view.k, drag.cam - dx));
        view.manualUntil = performance.now() / 1000 + 6;
      }
      return;
    }
    updateHover();
  }

  function updateHover() {
    if (!pointer) return;
    const p = worldPoint(pointer);
    const hit = hitBook(p);
    hover = hit;
    canvas.style.cursor = hit || hitHer(p) ? 'pointer' : (world.width > view.w / view.k ? 'grab' : 'default');
    const tip = byId('bookTip');
    if (hit) {
      tip.textContent = hit.book.name;
      const sp = screenPoint(hit.book.x + hit.book.w / 2, hit.book.y);
      tip.style.left = `${Math.round(sp.x)}px`;
      tip.style.top = `${Math.round(sp.y - 8)}px`;
      tip.hidden = false;
    } else {
      tip.hidden = true;
    }
  }

  function onDown(e) {
    if (e.button !== 0) return;
    drag = { x: e.clientX, cam: view.camX, moved: false };
  }

  function onUp(e) {
    const wasDrag = drag && drag.moved;
    drag = null;
    if (wasDrag) return;
    const p = worldPoint(e);
    const hit = hitBook(p);
    if (hit) { showCard(hit); return; }
    if (hitHer(p)) {
      if (!her.task || !her.task.scene) {
        startTask({ label: 'Hmph. Estou ocupada com um livro.', steps: [play('glance', 1.2), play('think', 1.2)] },
          performance.now() / 1000);
      }
      return;
    }
    hideCard();
  }

  function onWheel(e) {
    const viewW = view.w / view.k;
    if (world.width <= viewW) return;
    e.preventDefault();
    const delta = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
    view.camX = Math.max(0, Math.min(world.width - viewW, view.camX + delta / view.k));
    view.manualUntil = performance.now() / 1000 + 6;
  }

  function onKey(e) {
    const viewW = view.w / view.k;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      if (world.width <= viewW) return;
      e.preventDefault();
      view.camX = Math.max(0, Math.min(world.width - viewW, view.camX + (e.key === 'ArrowRight' ? 60 : -60)));
      view.manualUntil = performance.now() / 1000 + 6;
    } else if (e.key === 'Escape') {
      hideCard();
    }
  }

  function showCard(hit) {
    selected = hit;
    const { book, shelf } = hit;
    byId('bookCardTitle').textContent = book.name;
    const when = book.modified ? new Date(book.modified * 1000).toLocaleString('pt-BR', {
      day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
    }) : '—';
    byId('bookCardMeta').innerHTML = `
      <dt>Estante</dt><dd>${escape(shelf.name)}</dd>
      <dt>Tamanho</dt><dd>${escape(humanSize(book.size))}</dd>
      <dt>Modificado</dt><dd>${escape(when)}</dd>
      <dt>Caminho</dt><dd class="book-path">${escape(book.path)}</dd>`;
    const card = byId('bookCard');
    card.hidden = false;
    const stage = byId('libraryStage');
    const sp = screenPoint(book.x + book.w + 6, book.y);
    const left = Math.max(12, Math.min(stage.clientWidth - card.offsetWidth - 12, sp.x));
    const top = Math.max(12, Math.min(stage.clientHeight - card.offsetHeight - 12, sp.y - 20));
    card.style.left = `${Math.round(left)}px`;
    card.style.top = `${Math.round(top)}px`;
    card.focus({ preventScroll: true });
  }

  function hideCard() {
    selected = null;
    byId('bookCard').hidden = true;
  }

  function askToRead() {
    if (!selected) return;
    const book = selected.book;
    if (typeof isGenerating !== 'undefined' && isGenerating) {
      toast('Espere ela terminar a resposta atual.', 'error');
      return;
    }
    hideCard();
    showSidebarTab('conversations');
    chatInput.value = `Leia o arquivo "${book.path}" e me conte, com as suas palavras, do que se trata.`;
    if (typeof autoGrow === 'function') autoGrow();
    sendMessage();
  }

  // ---------- Painel de seções (barra lateral) ----------
  function renderSectionList() {
    const list = byId('hallSections');
    if (!list) return;
    list.innerHTML = '';
    if (!shelves.length) {
      list.innerHTML = '<p class="empty-hint">Nenhuma seção ainda. Vincule uma pasta para ela ganhar uma estante.</p>';
      return;
    }
    for (const shelf of shelves) {
      const item = document.createElement('div');
      item.className = 'list-item hall-section';
      item.innerHTML = `
        <button type="button" class="hall-section-main" title="Ir até a estante">
          <span class="hall-section-name">${escape(shelf.name)}</span>
          <span class="hall-section-path">${escape(shelf.exists ? shelf.path : 'Pasta não encontrada: ' + shelf.path)}</span>
        </button>
        <span class="hall-section-count" title="${escape(plural(shelf.total, 'arquivo', 'arquivos'))}">${shelf.total}</span>
        <button type="button" class="icon-btn hall-unlink" title="Desvincular a seção (a pasta continua intacta)" aria-label="Desvincular ${escape(shelf.name)}">
          <svg class="ic ic-sm"><use href="#i-x"/></svg>
        </button>`;
      item.querySelector('.hall-section-main').addEventListener('click', () => visit(shelf));
      const unlinkBtn = item.querySelector('.hall-unlink');
      unlinkBtn.addEventListener('click', () => confirmUnlink(shelf, unlinkBtn));
      list.appendChild(item);
    }
  }

  function visit(shelf) {
    if (!isOpen) showSidebarTab('hall');
    view.manualUntil = 0;
    if (her.task && her.task.scene) return;
    startTask({ label: `Indo até a estante ${shelf.name}`, steps: [
      walkTo(() => shelfCenter(shelf)), run(() => { shelf.glow = 1.6; }), play('glance', 1.4)] },
    performance.now() / 1000);
  }

  function confirmUnlink(shelf, button) {
    if (!button.classList.contains('armed')) {
      button.classList.add('armed');
      button.title = 'Clique de novo para desvincular';
      setTimeout(() => { button.classList.remove('armed'); button.title = 'Desvincular a seção (a pasta continua intacta)'; }, 3000);
      return;
    }
    api(`/api/library/sections/${encodeURIComponent(shelf.id)}`, { method: 'DELETE' })
      .then(() => { toast(`Seção ${shelf.name} desvinculada. A pasta não foi alterada.`); return loadSections(); })
      .catch(err => toast(`Não desvinculei: ${err.message}`, 'error'));
  }

  function toggleAddForm(show) {
    const form = byId('hallAddForm');
    form.hidden = !show;
    byId('hallAddError').hidden = true;
    if (show) {
      if (!isOpen) showSidebarTab('hall');
      byId('hallPath').focus();
    } else {
      form.reset();
    }
  }

  async function pickFolder() {
    try {
      const res = await api('/api/library/pick-folder', { method: 'POST' });
      if (!res.available) {
        toast('O seletor de pastas só existe no aplicativo. Digite o caminho da pasta.');
        byId('hallPath').focus();
      } else if (res.path) {
        byId('hallPath').value = res.path;
      }
    } catch (err) {
      toast(`Não abri o seletor: ${err.message}`, 'error');
    }
  }

  async function addSection(e) {
    e.preventDefault();
    const path = byId('hallPath').value.trim();
    const name = byId('hallName').value.trim();
    const error = byId('hallAddError');
    error.hidden = true;
    if (!path) {
      error.textContent = 'Informe a pasta.';
      error.hidden = false;
      return;
    }
    try {
      const section = await api('/api/library/sections', { method: 'POST', body: { path, name: name || null } });
      toggleAddForm(false);
      toast(`Seção ${section.name} criada.`);
      await loadSections();
      const shelf = shelfById(section.id);
      if (shelf) visit(shelf);
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
    }
  }

  function renderCount() {
    const books = shelves.reduce((n, s) => n + s.total, 0);
    byId('libraryCount').textContent = shelves.length
      ? `${plural(shelves.length, 'estante', 'estantes')}, ${plural(books, 'livro', 'livros')}`
      : '';
  }

  // ---------- Abrir / fechar ----------
  async function open() {
    if (isOpen) return;
    isOpen = true;
    byId('chatMain').classList.add('library-open');
    byId('libraryView').hidden = false;
    resize();
    setLabel(her.label);
    await Promise.all([loadAtlas(), loadSections()]);
    if (!isOpen) return;
    await poll();
    lastTime = 0;
    if (!rafId) rafId = requestAnimationFrame(frame);
    canvas.focus({ preventScroll: true });
  }

  function close() {
    if (!isOpen) return;
    isOpen = false;
    byId('chatMain').classList.remove('library-open');
    byId('libraryView').hidden = true;
    hideCard();
    byId('bookTip').hidden = true;
    if (rafId) cancelAnimationFrame(rafId);
    rafId = 0;
  }

  function notifyActivity() {
    clearTimeout(notifyTimer);
    notifyTimer = setTimeout(poll, 400);
  }

  function init() {
    canvas = byId('libraryCanvas');
    if (!canvas) return;
    ctx = canvas.getContext('2d');
    canvas.addEventListener('pointermove', onMove);
    canvas.addEventListener('pointerdown', onDown);
    canvas.addEventListener('pointerup', onUp);
    canvas.addEventListener('pointerleave', () => { hover = null; drag = null; pointer = null; byId('bookTip').hidden = true; });
    canvas.addEventListener('wheel', onWheel, { passive: false });
    canvas.addEventListener('keydown', onKey);
    if (window.ResizeObserver) new ResizeObserver(() => { if (isOpen) resize(); }).observe(byId('libraryStage'));
    else window.addEventListener('resize', () => { if (isOpen) resize(); });
    byId('btnBookRead').addEventListener('click', askToRead);
    byId('btnBookClose').addEventListener('click', hideCard);
    byId('bookCard').addEventListener('keydown', (e) => { if (e.key === 'Escape') { hideCard(); canvas.focus(); } });
    byId('btnHallAdd').addEventListener('click', () => toggleAddForm(byId('hallAddForm').hidden));
    byId('btnHallCancel').addEventListener('click', () => toggleAddForm(false));
    byId('btnHallPick').addEventListener('click', pickFolder);
    byId('hallAddForm').addEventListener('submit', addSection);
    byId('btnLibraryEmptyAdd').addEventListener('click', () => toggleAddForm(true));
    byId('btnLibrarySidebar').addEventListener('click', () => byId('btnExpandSidebar').click());
    // Cheap polling: often while open, now and then for the tab's counter.
    pollTimer = setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      pollCount++;
      if (isOpen || pollCount % 3 === 0) poll();
    }, 2500);
    loadSections();
    poll();
  }

  window.VictoriqueLibrary = { open, close, notifyActivity, isOpen: () => isOpen, refresh: loadSections };
  document.addEventListener('DOMContentLoaded', init);
})();
