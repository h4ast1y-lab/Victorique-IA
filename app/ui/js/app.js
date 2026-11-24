// Application State
let currentConversationId = null;
let currentProjectId = null;
let currentPersonalityId = null;
let selectedModel = null;
let activeAbortController = null;
let isGenerating = false;
let projectsCache = [];
let profilesCache = [];
let conversationsCache = [];
let authPollTimer = null;
let sttAvailable = false;
let ttsAvailable = false;
let micAvailable = false;
let currentBackend = null;
let prefs = {};

const $ = (id) => document.getElementById(id);
const escape = (t) => (window.escapeHtml ? window.escapeHtml(t) : String(t || ''));
const md = (t) => (window.renderMarkdown ? window.renderMarkdown(t) : escape(t));
const icon = (name, cls = 'ic') => `<svg class="${cls}"><use href="#i-${name}"/></svg>`;

// DOM Elements
const chatInput = $('chatInput');
const chatForm = $('chatForm');
const chatMain = $('chatMain');
const btnSend = $('btnSend');
const btnStop = $('btnStop');
const btnVoiceListen = $('btnVoiceListen');
const messagesList = $('messagesList');
const conversationsList = $('conversationsList');
const currentChatTitle = $('currentChatTitle');
const authBar = $('authBar');
const authTitle = $('authTitle');
const authDesc = $('authDesc');
const authPayload = $('authPayload');
const btnApproveAction = $('btnApproveAction');
const btnRejectAction = $('btnRejectAction');
const fileInput = $('fileInput');
const chatFileInput = $('chatFileInput');
const attachTray = $('attachTray');

const SUGGESTIONS = [
  { icon: 'folder', label: 'Organizar uma pasta', prompt: 'Liste os arquivos da minha pasta Documentos e sugira uma forma de organizá-los.' },
  { icon: 'book', label: 'Consultar documentos', action: () => openLibraryModal() },
  { icon: 'pencil', label: 'Revisar um texto', prompt: 'Revise o texto abaixo e aponte problemas de clareza, gramática e tom:\n\n' },
  { icon: 'sparkle', label: 'O que você sabe fazer?', prompt: 'Resuma as ferramentas que você tem, o que cada uma faz e quais exigem minha autorização.' },
];

// ----------------- Initialization -----------------
document.addEventListener('DOMContentLoaded', async () => {
  restoreSidebarState();
  setupEventListeners();
  setupSliders();
  setupSettingsControls();
  setupDeepThinkingButton();
  renderSuggestions();
  applyAvatarPhoto();
  loadAvatarPhoto();
  await loadPreferences();
  await loadBackendMode();
  await loadProfiles();
  await loadProjects();
  await Promise.all([loadConversations(), loadDocuments(), loadMemories()]);
  startNewChat();
  checkPendingAuthorizations();
  // Engine probes can take seconds (Ollama offline): never block the UI on them.
  checkHealth();
  loadModels();
  await initVoice();
  initVisualState();
  initLife();
  authPollTimer = setInterval(checkPendingAuthorizations, 5000);
  setInterval(checkHealth, 30000);
});

function setupEventListeners() {
  document.querySelectorAll('.nav-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      const paneId = `pane${tab.dataset.tab.charAt(0).toUpperCase() + tab.dataset.tab.slice(1)}`;
      const targetPane = $(paneId);
      if (targetPane) targetPane.classList.add('active');
      if (tab.dataset.tab === 'organizer') loadOperations();
      if (window.VictoriqueLibrary) {
        if (tab.dataset.tab === 'hall') window.VictoriqueLibrary.open();
        else window.VictoriqueLibrary.close();
      }
    });
  });

  $('modeSelect').addEventListener('change', (e) => changeBackend(e.target.value));

  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    sendMessage();
  });

  chatInput.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' || e.isComposing) return;
    const enterSends = prefs.enter_to_send !== false;
    if ((enterSends && !e.shiftKey) || (!enterSends && (e.ctrlKey || e.metaKey))) {
      e.preventDefault();
      sendMessage();
    }
  });
  chatInput.addEventListener('input', () => { autoGrow(); updateSendState(); });

  $('btnNewChat').addEventListener('click', startNewChat);
  $('btnStop').addEventListener('click', () => abortGeneration());
  $('btnCollapseSidebar').addEventListener('click', toggleSidebar);
  $('btnExpandSidebar').addEventListener('click', toggleSidebar);

  $('btnOpenSettings').addEventListener('click', () => openSettingsModal());
  $('btnSavePersonality').addEventListener('click', saveProfileFromEditor);
  $('btnCreateBackup').addEventListener('click', createBackupNow);

  $('btnCreateProject').addEventListener('click', () => openProjectModal());
  $('btnCreateMemory').addEventListener('click', () => openMemoryModal());
  $('btnSaveProject').addEventListener('click', saveProject);
  $('btnSaveMemory').addEventListener('click', saveMemory);

  $('btnAttachChat').addEventListener('click', () => chatFileInput.click());
  chatFileInput.addEventListener('change', (e) => {
    addChatFiles(e.target.files);
    e.target.value = '';
  });
  setupAttachmentDrop();
  chatInput.addEventListener('paste', (e) => {
    const files = [...(e.clipboardData?.files || [])];
    if (!files.length) return;
    e.preventDefault();
    addChatFiles(files.map(pastedName));
  });
  $('btnCloseLightbox').addEventListener('click', closeLightbox);
  $('imageLightbox').addEventListener('click', (e) => { if (e.target.id === 'imageLightbox') closeLightbox(); });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !$('imageLightbox').hidden) closeLightbox();
  });
  $('btnUploadDoc').addEventListener('click', () => fileInput.click());
  $('btnModalUploadDoc').addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', handleFileUpload);
  $('btnAvatarPhotoUpload').addEventListener('click', () => $('avatarPhotoInput').click());
  $('avatarPhotoInput').addEventListener('change', async (e) => {
    await uploadAvatarPhoto(e.target.files[0]);
    e.target.value = '';
  });
  $('btnAvatarPhotoReset').addEventListener('click', resetAvatarPhoto);

  $('searchConversations').addEventListener('input', renderConversationList);

  $('btnExportChat').addEventListener('click', exportCurrentChat);
  $('btnDeleteChat').addEventListener('click', deleteCurrentChat);
  currentChatTitle.addEventListener('click', startTitleEdit);

  $('settingModel').addEventListener('change', (e) => changeModel(e.target.value));

  $('btnProfileMenu').addEventListener('click', (e) => {
    e.stopPropagation();
    toggleProfileMenu();
  });
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.menu-anchor')) $('profileMenu').hidden = true;
  });

  document.querySelectorAll('[data-close]').forEach(btn => {
    btn.addEventListener('click', () => closeModal(btn.dataset.close));
  });
  document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
    backdrop.addEventListener('mousedown', (e) => {
      if (e.target === backdrop) closeModal(backdrop.id);
    });
  });
  document.addEventListener('keydown', handleShortcuts);

  if (btnVoiceListen) btnVoiceListen.addEventListener('click', toggleVoiceListen);
}

function handleShortcuts(e) {
  const ctrl = e.ctrlKey || e.metaKey;
  if (e.key === 'Escape') {
    $('profileMenu').hidden = true;
    document.querySelectorAll('.modal-backdrop').forEach(m => { if (!m.hidden) closeModal(m.id); });
    return;
  }
  if (!ctrl) return;
  const key = e.key.toLowerCase();
  if (e.shiftKey && key === 'o') { e.preventDefault(); startNewChat(); }
  else if (key === 'k') { e.preventDefault(); showSidebarTab('conversations'); $('searchConversations').focus(); }
  else if (key === 'b') { e.preventDefault(); toggleSidebar(); }
  else if (key === ',') { e.preventDefault(); openSettingsModal(); }
}

function setupSliders() {
  [
    { id: 'sliderFormality', valId: 'valFormality' },
    { id: 'sliderObjectivity', valId: 'valObjectivity' },
    { id: 'sliderDetail', valId: 'valDetail' }
  ].forEach(s => {
    const el = $(s.id);
    const valEl = $(s.valId);
    if (el && valEl) {
      el.addEventListener('input', () => { valEl.textContent = el.value; });
    }
  });
}

function autoGrow() {
  chatInput.style.height = 'auto';
  if (!chatInput.value) return; // empty: keep the one-line CSS height
  chatInput.style.height = Math.min(chatInput.scrollHeight, 240) + 'px';
}

function updateSendState() {
  const uploading = pendingAttachments.some(a => a.status === 'uploading');
  const ready = pendingAttachments.some(a => a.status === 'ready');
  btnSend.disabled = uploading || !(chatInput.value.trim() || ready);
}

// ----------------- Chat attachments (stay in the chat, never in Documentos) -----------------
const ATTACH_IMAGE_EXTS = ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'];
const ATTACH_DOC_EXTS = ['.pdf', '.docx', '.xlsx', '.xlsm', '.xls', '.pptx', '.csv', '.tsv', '.epub',
  '.txt', '.md', '.json', '.xml', '.html', '.htm', '.yaml', '.yml', '.log', '.py', '.js', '.ts', '.css',
  '.ini', '.cfg', '.toml', '.sql'];
const ATTACH_MAX = 10;
let pendingAttachments = [];
let attachSeq = 0;

function fileExt(name) {
  return ((name || '').match(/\.[^.]+$/) || [''])[0].toLowerCase();
}

function formatBytes(n) {
  if (!n && n !== 0) return '';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function pastedName(file) {
  // Screenshots arrive as "image.png": give them a readable, unique name.
  if (!/^image\.(png|jpe?g|gif|webp|bmp)$/i.test(file.name || '')) return file;
  const stamp = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '');
  const ext = fileExt(file.name) || '.png';
  try { return new File([file], `colado-${stamp}${ext}`, { type: file.type }); } catch (_) { return file; }
}

function addChatFiles(fileList) {
  const files = [...(fileList || [])];
  for (const file of files) {
    if (pendingAttachments.length >= ATTACH_MAX) {
      toast(`No máximo ${ATTACH_MAX} anexos por mensagem.`, 'error');
      break;
    }
    const ext = fileExt(file.name);
    const kind = ATTACH_IMAGE_EXTS.includes(ext) ? 'image' : (ATTACH_DOC_EXTS.includes(ext) ? 'document' : null);
    if (!kind) {
      toast(`${file.name}: formato não aceito. Envie imagens, PDF, Word, Excel, PowerPoint ou textos.`, 'error');
      continue;
    }
    const limit = kind === 'image' ? 20 : 50;
    if (file.size > limit * 1024 * 1024) {
      toast(`${file.name} passa de ${limit} MB.`, 'error');
      continue;
    }
    const item = { localId: ++attachSeq, name: file.name, kind, size: file.size, status: 'uploading', preview: '' };
    pendingAttachments.push(item);
    if (kind === 'image') {
      const reader = new FileReader();
      reader.onload = () => { item.preview = reader.result; renderAttachTray(); };
      reader.readAsDataURL(file);
    }
    uploadChatFile(item, file);
  }
  renderAttachTray();
  chatInput.focus();
}

async function uploadChatFile(item, file) {
  const form = new FormData();
  form.append('file', file);
  try {
    const meta = await api('/api/chat/attachments', { method: 'POST', body: form });
    if (!pendingAttachments.includes(item)) {
      // Removed while uploading: discard it on the server too.
      api(`/api/chat/attachments/${meta.id}`, { method: 'DELETE' }).catch(() => {});
      return;
    }
    Object.assign(item, { id: meta.id, url: meta.url, mime: meta.mime, status: 'ready' });
  } catch (err) {
    item.status = 'error';
    item.error = err.message;
    toast(`Não consegui anexar ${item.name}: ${err.message}`, 'error');
  }
  renderAttachTray();
}

function removeAttachment(localId) {
  const item = pendingAttachments.find(a => a.localId === localId);
  pendingAttachments = pendingAttachments.filter(a => a.localId !== localId);
  if (item && item.id) api(`/api/chat/attachments/${item.id}`, { method: 'DELETE' }).catch(() => {});
  renderAttachTray();
}

function renderAttachTray() {
  attachTray.innerHTML = '';
  attachTray.hidden = pendingAttachments.length === 0;
  for (const item of pendingAttachments) {
    const chip = document.createElement('div');
    chip.className = `attach-chip ${item.kind} ${item.status}`;
    chip.title = item.status === 'error' ? `${item.name}: ${item.error || 'falhou'}` : item.name;
    if (item.kind === 'image' && item.preview) {
      const img = document.createElement('img');
      img.src = item.preview;
      img.alt = item.name;
      chip.appendChild(img);
    } else {
      const ic = document.createElement('span');
      ic.className = 'attach-icon';
      ic.innerHTML = icon(item.kind === 'image' ? 'file' : 'file');
      const ext = document.createElement('span');
      ext.className = 'attach-ext';
      ext.textContent = fileExt(item.name).slice(1, 5).toUpperCase();
      ic.appendChild(ext);
      chip.appendChild(ic);
    }
    const info = document.createElement('div');
    info.className = 'attach-info';
    const name = document.createElement('span');
    name.className = 'attach-name';
    name.textContent = item.name;
    const meta = document.createElement('span');
    meta.className = 'attach-meta';
    meta.textContent = item.status === 'uploading' ? 'enviando…'
      : item.status === 'error' ? 'falhou' : formatBytes(item.size);
    info.append(name, meta);
    chip.appendChild(info);
    const rm = document.createElement('button');
    rm.type = 'button';
    rm.className = 'attach-remove';
    rm.title = 'Remover anexo';
    rm.setAttribute('aria-label', `Remover ${item.name}`);
    rm.innerHTML = icon('x', 'ic ic-sm');
    rm.addEventListener('click', () => removeAttachment(item.localId));
    chip.appendChild(rm);
    attachTray.appendChild(chip);
  }
  updateSendState();
}

function setupAttachmentDrop() {
  const zone = document.querySelector('.chat-input-area') || chatForm;
  const hint = $('dropHint');
  let depth = 0;
  const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes('Files');
  zone.addEventListener('dragenter', (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    depth += 1;
    chatForm.classList.add('dragging');
    hint.hidden = false;
  });
  zone.addEventListener('dragover', (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  });
  zone.addEventListener('dragleave', () => {
    depth = Math.max(0, depth - 1);
    if (!depth) { chatForm.classList.remove('dragging'); hint.hidden = true; }
  });
  zone.addEventListener('drop', (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    depth = 0;
    chatForm.classList.remove('dragging');
    hint.hidden = true;
    addChatFiles(e.dataTransfer.files);
  });
}

function renderAttachments(list) {
  const box = document.createElement('div');
  box.className = 'msg-attachments';
  for (const att of list || []) {
    if (att.kind === 'image') {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'msg-thumb';
      button.title = att.name;
      const img = document.createElement('img');
      img.src = att.url;
      img.alt = att.name;
      img.loading = 'lazy';
      img.addEventListener('error', () => { button.classList.add('missing'); button.textContent = att.name; });
      button.appendChild(img);
      button.addEventListener('click', () => openLightbox(att.url, att.name));
      box.appendChild(button);
    } else {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'msg-file';
      chip.title = `Abrir ${att.name} no programa do Windows`;
      chip.innerHTML = `${icon('file')}<span class="msg-file-name"></span><span class="msg-file-meta"></span>`;
      chip.querySelector('.msg-file-name').textContent = att.name;
      chip.querySelector('.msg-file-meta').textContent = formatBytes(att.size);
      chip.addEventListener('click', async () => {
        try {
          await api(`/api/chat/attachments/${att.id}/open`, { method: 'POST' });
        } catch (err) {
          toast(`Não consegui abrir: ${err.message}`, 'error');
        }
      });
      box.appendChild(chip);
    }
  }
  return box;
}

function openLightbox(url, name) {
  $('lightboxImg').src = url;
  $('lightboxImg').alt = name || '';
  $('lightboxCaption').textContent = name || '';
  $('imageLightbox').hidden = false;
}

function closeLightbox() {
  $('imageLightbox').hidden = true;
  $('lightboxImg').removeAttribute('src');
}

// ----------------- Sidebar -----------------
function toggleSidebar() {
  const layout = $('appLayout');
  layout.classList.toggle('sidebar-collapsed');
  try { localStorage.setItem('sidebarCollapsed', layout.classList.contains('sidebar-collapsed') ? '1' : '0'); } catch (_) { /* storage off */ }
}

function restoreSidebarState() {
  let collapsed = false;
  try { collapsed = localStorage.getItem('sidebarCollapsed') === '1'; } catch (_) { /* storage off */ }
  if (collapsed || window.innerWidth < 820) $('appLayout').classList.add('sidebar-collapsed');
}

function showSidebarTab(name) {
  $('appLayout').classList.remove('sidebar-collapsed');
  const tab = document.querySelector(`.nav-tab[data-tab="${name}"]`);
  if (tab) tab.click();
}

// ----------------- HTTP helpers -----------------
async function api(path, options = {}) {
  const opts = { method: options.method || 'GET', headers: { ...(options.headers || {}) } };
  if (options.body instanceof FormData) {
    opts.body = options.body;
  } else if (options.body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = typeof options.body === 'string' ? options.body : JSON.stringify(options.body);
  }
  if (options.signal) opts.signal = options.signal;

  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      detail = data.detail || data.error || detail;
    } catch (_) { /* not JSON */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res.text();
}

function delay(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

function toast(message, kind = 'ok') {
  const el = document.createElement('div');
  el.className = `toast ${kind === 'error' ? 'error' : ''}`;
  el.innerHTML = `${icon(kind === 'error' ? 'info' : 'check')}<span></span>`;
  el.querySelector('span').textContent = message;
  $('toastStack').appendChild(el);
  setTimeout(() => el.remove(), kind === 'error' ? 5000 : 2200);
}

async function copyText(text, button) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (_) {
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
  }
  if (button) {
    const old = button.innerHTML;
    button.innerHTML = button.classList.contains('code-copy') ? `${icon('check')}Copiado` : icon('check');
    setTimeout(() => { button.innerHTML = old; }, 1400);
  } else {
    toast('Copiado');
  }
}

// ----------------- Preferences & appearance -----------------
// Modo Turbo: ligar pede uma confirmação; desligar é imediato.
function setupTurboSwitch() {
  const box = $('prefTurbo');
  const confirmBox = $('turboConfirm');
  box.addEventListener('change', () => {
    if (box.checked) {
      box.checked = false;  // só liga depois de confirmar
      confirmBox.hidden = false;
      $('btnTurboConfirm').focus();
      return;
    }
    confirmBox.hidden = true;
    savePref('turbo_mode', false, { immediate: true, quiet: true });
    toast('Modo Turbo desligado: ela volta a pedir aprovação.');
  });
  $('btnTurboCancel').addEventListener('click', () => { confirmBox.hidden = true; });
  $('btnTurboConfirm').addEventListener('click', () => {
    confirmBox.hidden = true;
    box.checked = true;
    savePref('turbo_mode', true, { immediate: true, quiet: true });
    toast('Modo Turbo ligado. Excluir e reorganizar pastas ainda pedem aprovação.');
  });
}

function setupDeepThinkingButton() {
  $('btnDeepThinking').addEventListener('click', () => {
    const on = !prefs.deep_thinking;
    savePref('deep_thinking', on, { immediate: true, quiet: true });
    toast(on ? 'Pensamento profundo ligado: ela pensa em voz alta antes de responder.'
             : 'Pensamento profundo desligado.');
  });
}

async function loadPreferences() {
  try {
    prefs = await api('/api/preferences');
  } catch (err) {
    console.error('Failed to load preferences', err);
  }
  applyAppearance();
  fillPreferenceControls();
  updateUserLabel();
  updateLifeControls();
}

let prefSaveTimer = null;
let pendingPrefChanges = {};
let pendingPrefsQuiet = true;

function savePref(name, value, { immediate = false, quiet = false } = {}) {
  prefs[name] = value;
  pendingPrefChanges[name] = value;
  if (!quiet) pendingPrefsQuiet = false;
  applyAppearance();
  if (name === 'user_name') updateUserLabel();
  if (name.startsWith('life_')) updateLifeControls();
  if (name.startsWith('mascot_')) setTimeout(loadMascotStatus, 2600);
  clearTimeout(prefSaveTimer);
  prefSaveTimer = setTimeout(flushPrefs, immediate ? 0 : 600);
}

async function flushPrefs() {
  const changes = pendingPrefChanges;
  const quiet = pendingPrefsQuiet;
  pendingPrefChanges = {};
  pendingPrefsQuiet = true;
  if (!Object.keys(changes).length) return;
  try {
    prefs = await api('/api/preferences', { method: 'POST', body: changes });
    if (!quiet) toast('Preferências salvas');
  } catch (err) {
    toast(`Não salvei: ${err.message}`, 'error');
    await loadPreferences();
  }
}

function resolvedTheme() {
  if (prefs.theme === 'system') {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  }
  return prefs.theme || 'dark';
}

function applyAppearance() {
  const root = document.documentElement;
  root.dataset.theme = resolvedTheme();
  root.dataset.accent = prefs.accent || 'terracota';
  root.dataset.fontSize = prefs.font_size || 'medium';
  root.dataset.chatWidth = prefs.chat_width || 'normal';
  root.dataset.responseFont = prefs.response_font || 'sans';
  messagesList.classList.toggle('hide-reasoning', prefs.show_reasoning === false);
  messagesList.classList.toggle('hide-tools', prefs.show_tool_events === false);
  $('suggestions').classList.toggle('on', prefs.show_suggestions !== false);
  const deep = !!prefs.deep_thinking;
  $('btnDeepThinking').setAttribute('aria-pressed', String(deep));
  $('btnDeepThinking').classList.toggle('on', deep);
  $('turboBadge').hidden = !prefs.turbo_mode;
  chatInput.placeholder = prefs.enter_to_send === false
    ? 'Escreva sua mensagem (Ctrl+Enter envia)'
    : `Pergunte qualquer coisa a ${activeProfileName()}`;
}

if (window.matchMedia) {
  window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
    if (prefs.theme === 'system') applyAppearance();
  });
}

function fillPreferenceControls() {
  document.querySelectorAll('[data-pref]').forEach(el => {
    const value = prefs[el.dataset.pref];
    if (value === undefined) return;
    if (el.type === 'checkbox') el.checked = !!value;
    else el.value = value;
  });
  document.querySelectorAll('[data-pref-group]').forEach(group => {
    const value = prefs[group.dataset.prefGroup];
    group.querySelectorAll('button').forEach(b => b.classList.toggle('active', b.dataset.value === value));
  });
  $('valTemperature').textContent = Number(prefs.temperature ?? 0.7).toFixed(2);
  $('prefTurbo').checked = !!prefs.turbo_mode;
  $('turboConfirm').hidden = true;
  $('aboutCount').textContent = ($('prefUserAbout').value || '').length;
}

function setupSettingsControls() {
  document.querySelectorAll('.settings-tab').forEach(tab => {
    tab.addEventListener('click', () => showSettingsSection(tab.dataset.section));
  });

  document.querySelectorAll('[data-pref]').forEach(el => {
    const name = el.dataset.pref;
    if (el.type === 'checkbox') {
      el.addEventListener('change', () => savePref(name, el.checked, { immediate: true }));
    } else if (el.type === 'range') {
      el.addEventListener('input', () => { $('valTemperature').textContent = Number(el.value).toFixed(2); });
      el.addEventListener('change', () => savePref(name, Number(el.value), { immediate: true }));
    } else if (el.type === 'number') {
      el.addEventListener('change', () => {
        const n = parseInt(el.value, 10);
        const min = Number(el.min), max = Number(el.max);
        if (Number.isNaN(n) || n < min || n > max) {
          toast(`Use um valor entre ${min} e ${max}.`, 'error');
          el.value = prefs[name];
          return;
        }
        savePref(name, n, { immediate: true });
      });
    } else if (el.tagName === 'SELECT') {
      el.addEventListener('change', () => savePref(name, el.value, { immediate: true }));
    } else {
      el.addEventListener('input', () => {
        if (name === 'user_about') $('aboutCount').textContent = el.value.length;
        savePref(name, el.value);
      });
    }
  });

  document.querySelectorAll('[data-pref-group]').forEach(group => {
    group.querySelectorAll('button').forEach(btn => {
      btn.addEventListener('click', () => {
        group.querySelectorAll('button').forEach(b => b.classList.toggle('active', b === btn));
        savePref(group.dataset.prefGroup, btn.dataset.value, { immediate: true });
      });
    });
  });

  setupTurboSwitch();

  $('emojiLevel').querySelectorAll('button').forEach(btn => {
    btn.addEventListener('click', () => setEditorEmoji(Number(btn.dataset.value)));
  });
  $('btnDuplicateProfile').addEventListener('click', duplicateProfile);
  $('btnResetProfile').addEventListener('click', resetEditorProfile);
  $('btnMakeDefaultProfile').addEventListener('click', makeEditorProfileDefault);
  $('btnDeleteProfile').addEventListener('click', deleteEditorProfile);
}

function showSettingsSection(name) {
  document.querySelectorAll('.settings-tab').forEach(t => t.classList.toggle('active', t.dataset.section === name));
  document.querySelectorAll('.settings-section').forEach(s => s.classList.toggle('active', s.dataset.section === name));
}

function updateUserLabel() {
  const name = (prefs.user_name || '').trim();
  $('userNameLabel').textContent = name || 'Você';
  $('userAvatar').textContent = name ? name.charAt(0).toUpperCase() : '?';
  updateGreeting();
}

function updateGreeting() {
  const h = new Date().getHours();
  const part = h < 5 ? 'Boa noite' : h < 12 ? 'Bom dia' : h < 18 ? 'Boa tarde' : 'Boa noite';
  const name = (prefs.user_name || '').trim();
  $('welcomeGreeting').textContent = name ? `${part}, ${name}` : part;
  const profile = activeProfile();
  $('welcomeSub').textContent = profile && profile.id === 'victorique'
    ? 'Traga um mistério. De preferência, um que não seja entediante.'
    : 'Como posso ajudar hoje?';
}

function renderSuggestions() {
  const box = $('suggestions');
  box.innerHTML = '';
  SUGGESTIONS.forEach(s => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'suggestion';
    b.innerHTML = `${icon(s.icon)}<span></span>`;
    b.querySelector('span').textContent = s.label;
    b.addEventListener('click', () => (s.action ? s.action() : setPrompt(s.prompt)));
    box.appendChild(b);
  });
}

// ----------------- Health & Models -----------------
async function checkHealth() {
  const pill = $('statusPill');
  const dot = $('statusDot');
  try {
    const data = await api('/api/health');
    const backend = currentBackend || data.active_backend;
    let ok = data.status === 'healthy';
    let label;
    if (backend === 'claude-code') {
      label = ok ? 'Claude Code pronto' : 'Claude Agent SDK ausente';
    } else if (backend === 'codex') {
      label = ok ? 'Codex pronto' : 'Codex não instalado';
    } else if (backend === 'ollama') {
      ok = !!data.ollama_online && data.default_model_installed !== false;
      label = !data.ollama_online ? 'Ollama desconectado'
        : data.default_model_installed === false ? `Modelo ${data.default_model} ausente`
        : `Ollama · ${data.default_model}`;
    } else {
      label = ok ? 'llama.cpp pronto' : 'llama.cpp carregando ou offline';
    }
    pill.textContent = label;
    pill.className = `status-indicator ${ok ? 'online' : 'offline'}`;
    dot.className = `status-dot ${ok ? 'online' : 'offline'}`;
    dot.parentElement.title = label;

    const ocr = data.ocr || {};
    $('runtimeInfo').innerHTML = [
      `<strong>${escape(data.app_name || 'Victorique')}</strong>`,
      `Modo ativo: ${escape(backendLabel(backend))} — ${escape(label)}`,
      `Ferramentas: ${data.tools_count || 0}${data.tool_calling_enabled ? ' (tool calling ativo)' : ' (tool calling desativado)'}`,
      ocr.available ? `OCR ativo (${escape((ocr.languages || []).join(', ') || 'eng')})` : 'OCR indisponível',
    ].join('<br>');
  } catch (err) {
    console.error('Healthcheck failed', err);
    pill.textContent = 'Servidor indisponível';
    pill.className = 'status-indicator offline';
    dot.className = 'status-dot offline';
  }
}

function backendLabel(value) {
  return { 'claude-code': 'Claude Code', codex: 'Codex', ollama: 'Ollama', 'llama-cpp': 'llama.cpp', 'llama-cpp-server': 'llama.cpp' }[value] || value || '—';
}

async function initVoice() {
  const button = $('vicVoiceGenerate');
  const player = $('vicVoicePlayer');
  button.onclick = async () => {
    button.disabled = true;
    const message = $('vicVoiceMessage');
    message.textContent = 'Gerando a voz no computador…';
    try {
      const response = await fetch('/api/tts/audio', { method: 'POST',
        headers: {'Content-Type':'application/json'}, body: JSON.stringify({
          text: $('vicVoiceText').value.trim(), language: $('vicVoiceLang').value, emotion: $('vicVoiceEmotion').value
        }) });
      if (!response.ok) {
        let detail = 'Verifique o texto e a disponibilidade do motor de voz.';
        try { detail = (await response.json()).detail || detail; } catch (_) { /* not JSON */ }
        throw new Error(detail);
      }
      const previous = player.src;
      player.src = URL.createObjectURL(await response.blob());
      if (previous.startsWith('blob:')) URL.revokeObjectURL(previous);
      message.textContent = 'Áudio pronto para reprodução.';
      await player.play().catch(() => {});
    } catch (err) { message.textContent = err.message; }
    finally { button.disabled = false; }
  };
  try {
    const [tts, stt] = await Promise.all([api('/api/tts/status'), api('/api/stt/status')]);
    ttsAvailable = tts.available === true;
    sttAvailable = stt.available === true;
    micAvailable = !!stt.microphone_available;
    btnVoiceListen.hidden = !(sttAvailable && micAvailable);
    $('voiceStatus').innerHTML =
      `Leitura em voz alta: <strong>${ttsAvailable ? 'disponível' : 'indisponível'}</strong><br>` +
      `Ditado pelo microfone: <strong>${sttAvailable && micAvailable ? 'disponível' : 'indisponível'}</strong>` +
      (sttAvailable && !micAvailable ? ' (microfone não encontrado — instale o PyAudio)' : '');
    document.querySelectorAll('.btn-speak').forEach(b => { b.hidden = !ttsAvailable; });
  } catch (err) {
    console.error('Voice init failed', err);
    btnVoiceListen.hidden = true;
  }
}

async function toggleVoiceListen() {
  if (!sttAvailable) { toast('Ditado indisponível.', 'error'); return; }
  btnVoiceListen.classList.add('listening');
  visual.listening = true;
  noteActivity();
  refreshVisualState();
  btnVoiceListen.title = 'Ouvindo… fale agora';
  try {
    const data = await api('/api/stt/listen', {
      method: 'POST',
      body: { timeout: 5, phrase_time_limit: 15 },
    });
    if (data.status === 'ok' && data.text) {
      chatInput.value = (chatInput.value ? chatInput.value + ' ' : '') + data.text;
      autoGrow();
      updateSendState();
      chatInput.focus();
    } else {
      toast('Nenhuma fala detectada.', 'error');
    }
  } catch (err) {
    toast(`Erro no ditado: ${err.message}`, 'error');
  } finally {
    btnVoiceListen.classList.remove('listening');
    visual.listening = false;
    refreshVisualState();
    btnVoiceListen.title = 'Ditar pelo microfone';
  }
}

async function speakText(text) {
  if (!ttsAvailable) { toast('Leitura em voz alta indisponível.', 'error'); return; }
  try {
    const data = await api('/api/tts/speak', { method: 'POST', body: { text, async_: true } });
    if (data.status !== 'speaking_async') toast('Leitura em voz alta indisponível.', 'error');
    else markSpeaking(text);
  } catch (err) {
    toast(`Erro na leitura: ${err.message}`, 'error');
  }
}

async function loadModels() {
  try {
    const [modelsData, cfg] = await Promise.all([api('/api/models'), api('/api/settings')]);
    const select = $('settingModel');
    select.innerHTML = '';
    const models = (modelsData.models || []).filter(m => !String(m.name).includes('embed'));
    models.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.name;
      const size = m.size ? ` — ${(m.size / (1024 ** 3)).toFixed(1)} GB` : '';
      opt.textContent = m.name + size;
      select.appendChild(opt);
    });
    selectedModel = modelsData.active_default || cfg.default_model;
    if (selectedModel && !models.some(m => m.name === selectedModel)) {
      const opt = document.createElement('option');
      opt.value = selectedModel;
      opt.textContent = selectedModel + ' (não instalado)';
      select.appendChild(opt);
    }
    select.value = selectedModel;
    updateModelTag();
  } catch (err) {
    console.error('Failed to load models', err);
  }
}

async function changeModel(name) {
  try {
    await api('/api/settings', { method: 'POST', body: { default_model: name } });
    selectedModel = name;
    updateModelTag();
    toast('Modelo alterado');
    await checkHealth();
  } catch (err) {
    toast(`Não foi possível salvar o modelo: ${err.message}`, 'error');
  }
}

function updateModelTag() {
  $('modelHint').textContent = selectedModel
    ? `Em uso: ${selectedModel}. Modelos do Ollama rodam no seu computador; nada sai dele.`
    : 'Nenhum modelo do Ollama encontrado.';
}

// ----------------- Mode (local / Claude Code) -----------------
async function loadBackendMode() {
  try {
    const cfg = await api('/api/settings');
    currentBackend = cfg.default_backend;
    updateModeUi();
  } catch (err) {
    console.error('Failed to load mode', err);
  }
}

async function changeBackend(value) {
  try {
    await api('/api/settings', { method: 'POST', body: { default_backend: value } });
    currentBackend = value;
    updateModeUi();
    toast(`Modo: ${backendLabel(value)}`);
    await checkHealth();
    if (value === 'codex') checkCodexInstalled();
  } catch (err) {
    toast(`Não foi possível trocar o modo: ${err.message}`, 'error');
    updateModeUi();
  }
}

// The Codex CLI is the user's to install; say how when it is missing.
async function checkCodexInstalled() {
  try {
    const status = await api('/api/codex/status');
    if (!status.installed) {
      toast('O Codex não está instalado. Rode num terminal: npm install -g @openai/codex e depois codex login.', 'error');
    }
  } catch (_) { /* the chat explains it too */ }
}

function updateModeUi() {
  const isCloud = currentBackend === 'claude-code' || currentBackend === 'codex';
  // llama-cpp-server is the same local engine as llama-cpp in the selector.
  $('modeSelect').value = currentBackend === 'llama-cpp-server' ? 'llama-cpp' : (currentBackend || 'llama-cpp');
  const badge = $('claudeBadge');
  badge.hidden = !isCloud;
  const company = currentBackend === 'codex' ? 'OpenAI' : 'Anthropic';
  badge.textContent = `Dados enviados à ${company}`;
  badge.title = `Neste modo as mensagens são processadas pela ${company}, não no seu computador.`;
}

// ----------------- Profiles -----------------
function activeProfile() {
  return profilesCache.find(p => p.id === currentPersonalityId)
    || profilesCache.find(p => p.is_default)
    || profilesCache[0] || null;
}

function activeProfileName() {
  const p = activeProfile();
  return p ? p.name : 'Victorique';
}

function avatarText(p) {
  if (!p) return 'V';
  return (p.avatar || '').trim() || (p.name || '?').charAt(0).toUpperCase();
}

// The Victorique profile (with no text avatar) shows her photo. The photo URL
// lives in the --avatar-photo CSS variable, so changing it repaints every
// avatar already on screen, old messages included.
function usesAvatarPhoto(p) {
  return !p || (p.id === 'victorique' && !(p.avatar || '').trim());
}

function paintAvatar(el, p) {
  const photo = usesAvatarPhoto(p);
  el.classList.toggle('has-photo', photo);
  el.textContent = photo ? '' : avatarText(p);
}

let avatarPhotoInfo = { source: 'default', url: '/api/avatar/photo' };

function applyAvatarPhoto(info) {
  if (info) avatarPhotoInfo = info;
  const url = avatarPhotoInfo.url;
  document.documentElement.style.setProperty('--avatar-photo', `url("${url}")`);
  let link = document.querySelector('link[rel="icon"]');
  if (!link) {
    link = document.createElement('link');
    link.rel = 'icon';
    document.head.appendChild(link);
  }
  link.removeAttribute('type');
  link.href = url;
  const preview = $('avatarPhotoPreview');
  if (preview) preview.style.backgroundImage = `url("${url}")`;
  const reset = $('btnAvatarPhotoReset');
  if (reset) reset.disabled = avatarPhotoInfo.source !== 'custom';
  const note = $('avatarPhotoSource');
  if (note) note.textContent = avatarPhotoInfo.source === 'custom' ? 'Foto escolhida por você.' : 'Foto padrão.';
}

async function loadAvatarPhoto() {
  try {
    applyAvatarPhoto(await api('/api/avatar/photo/info'));
  } catch (err) {
    console.error('Failed to load avatar photo', err);
    applyAvatarPhoto();
  }
}

async function uploadAvatarPhoto(file) {
  if (!file) return;
  if (file.size > 5 * 1024 * 1024) {
    toast('Imagem maior que 5 MB.', 'error');
    return;
  }
  const form = new FormData();
  form.append('file', file);
  try {
    applyAvatarPhoto(await api('/api/avatar/photo', { method: 'POST', body: form }));
    prefs.avatar_photo = 'custom';
    toast('Foto trocada');
  } catch (err) {
    toast(`Não troquei a foto: ${err.message}`, 'error');
  }
}

async function resetAvatarPhoto() {
  try {
    applyAvatarPhoto(await api('/api/avatar/photo', { method: 'DELETE' }));
    prefs.avatar_photo = 'default';
    toast('Foto padrão restaurada');
  } catch (err) {
    toast(`Não restaurei: ${err.message}`, 'error');
  }
}

async function loadProfiles() {
  try {
    profilesCache = await api('/api/personalities');
    if (!currentPersonalityId || !profilesCache.some(p => p.id === currentPersonalityId)) {
      const def = profilesCache.find(p => p.is_default) || profilesCache[0];
      currentPersonalityId = def ? def.id : null;
    }
    updateProfileUi();
  } catch (err) {
    console.error('Failed to load profiles', err);
  }
}

function updateProfileUi() {
  const p = activeProfile();
  paintAvatar($('profilePillAvatar'), p);
  $('profilePillName').textContent = p ? p.name : '—';
  paintAvatar($('welcomeAvatar'), p);
  paintAvatar($('brandAvatar'), p);
  $('brandName').textContent = p ? p.name : 'Victorique';
  $('composerNote').textContent = `${p ? p.name : 'A assistente'} pode errar. Confira informações importantes.`;
  document.title = p ? p.name : 'Victorique';
  updateGreeting();
  applyAppearance();
}

function toggleProfileMenu() {
  const menu = $('profileMenu');
  if (!menu.hidden) { menu.hidden = true; return; }
  menu.innerHTML = '<div class="popover-title">Perfil da assistente</div>';
  profilesCache.forEach(p => {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'popover-item';
    item.innerHTML = `
      <span class="pill-avatar"></span>
      <span class="popover-item-text"><strong></strong><small></small></span>
      ${p.id === currentPersonalityId ? icon('check', 'ic check') : ''}`;
    paintAvatar(item.querySelector('.pill-avatar'), p);
    item.querySelector('strong').textContent = p.name;
    item.querySelector('small').textContent = p.description || (p.is_default ? 'Perfil padrão' : p.tone || '');
    item.addEventListener('click', () => {
      currentPersonalityId = p.id;
      menu.hidden = true;
      updateProfileUi();
      toast(currentConversationId ? `${p.name} responde a partir da próxima mensagem` : `Perfil: ${p.name}`);
    });
    menu.appendChild(item);
  });
  const sep = document.createElement('div');
  sep.className = 'popover-sep';
  menu.appendChild(sep);
  const manage = document.createElement('button');
  manage.type = 'button';
  manage.className = 'popover-item';
  manage.innerHTML = `${icon('sliders')}<span class="popover-item-text"><strong>Gerenciar perfis</strong></span>`;
  manage.addEventListener('click', () => { menu.hidden = true; openSettingsModal('profiles'); });
  menu.appendChild(manage);
  menu.hidden = false;
}

// Profile editor (Settings → Perfis)
let editorProfileId = null;
let editorEmoji = 2;

function renderProfileList() {
  const list = $('profileList');
  list.innerHTML = '';
  profilesCache.forEach(p => {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = `profile-card ${p.id === editorProfileId ? 'active' : ''}`;
    card.innerHTML = `
      <span class="profile-card-avatar"></span>
      <span class="profile-card-text"><strong></strong><small></small></span>
      ${p.is_default ? '<span class="badge">Padrão</span>' : ''}`;
    paintAvatar(card.querySelector('.profile-card-avatar'), p);
    card.querySelector('strong').textContent = p.name;
    card.querySelector('small').textContent = p.tone || '';
    card.addEventListener('click', () => loadProfileIntoEditor(p));
    list.appendChild(card);
  });
  const add = document.createElement('button');
  add.type = 'button';
  add.className = 'profile-card profile-new';
  add.innerHTML = `${icon('plus')}<span>Novo perfil</span>`;
  add.addEventListener('click', () => loadProfileIntoEditor(null));
  list.appendChild(add);
}

function loadProfileIntoEditor(p) {
  editorProfileId = p ? p.id : null;
  $('profileId').value = editorProfileId || '';
  $('profileAvatar').value = p ? (p.avatar || '') : '';
  $('settingName').value = p ? p.name : '';
  $('profileDescription').value = p ? (p.description || '') : '';
  $('settingInstructions').value = p ? p.system_instructions : '';
  $('settingTone').value = p ? (p.tone || '') : '';
  [['sliderFormality', 'valFormality', p ? p.formality : 3],
   ['sliderObjectivity', 'valObjectivity', p ? p.objectivity : 4],
   ['sliderDetail', 'valDetail', p ? p.detail_level : 3]].forEach(([s, v, val]) => {
    $(s).value = val || 3;
    $(v).textContent = val || 3;
  });
  setEditorEmoji(p ? (p.emoji_level || 2) : 2);
  $('btnDeleteProfile').disabled = !p || !!p.is_default || p.id === 'default';
  $('btnMakeDefaultProfile').disabled = !p || !!p.is_default;
  $('btnDuplicateProfile').disabled = !p;
  $('btnResetProfile').hidden = !p || p.id !== 'victorique';
  renderProfileList();
  if (!p) $('settingName').focus();
}

function setEditorEmoji(level) {
  editorEmoji = level;
  $('emojiLevel').querySelectorAll('button').forEach(b => b.classList.toggle('active', Number(b.dataset.value) === level));
}

function editorPayload() {
  const existing = profilesCache.find(p => p.id === editorProfileId);
  return {
    id: editorProfileId || undefined,
    name: $('settingName').value.trim(),
    avatar: $('profileAvatar').value.trim(),
    description: $('profileDescription').value.trim(),
    system_instructions: $('settingInstructions').value.trim(),
    tone: $('settingTone').value.trim() || 'prestativo',
    formality: parseInt($('sliderFormality').value, 10),
    objectivity: parseInt($('sliderObjectivity').value, 10),
    detail_level: parseInt($('sliderDetail').value, 10),
    emoji_level: editorEmoji,
    is_default: existing ? !!existing.is_default : false,
  };
}

async function saveProfileFromEditor() {
  const payload = editorPayload();
  if (!payload.name || !payload.system_instructions) {
    toast('Nome e instruções não podem ficar vazios.', 'error');
    return;
  }
  try {
    const saved = await api('/api/personalities', { method: 'POST', body: payload });
    await loadProfiles();
    loadProfileIntoEditor(profilesCache.find(p => p.id === saved.id) || saved);
    toast('Perfil salvo');
  } catch (err) {
    toast(`Falha ao salvar perfil: ${err.message}`, 'error');
  }
}

function duplicateProfile() {
  const payload = editorPayload();
  editorProfileId = null;
  $('profileId').value = '';
  $('settingName').value = `${payload.name} (cópia)`;
  $('btnDeleteProfile').disabled = true;
  $('btnMakeDefaultProfile').disabled = true;
  $('btnDuplicateProfile').disabled = true;
  renderProfileList();
  toast('Cópia criada no editor. Salve para manter.');
}

async function resetEditorProfile() {
  if (!editorProfileId) return;
  try {
    const original = await api(`/api/personalities/${encodeURIComponent(editorProfileId)}/factory`);
    const current = profilesCache.find(p => p.id === editorProfileId) || {};
    loadProfileIntoEditor({ ...original, is_default: current.is_default });
    toast('Textos originais carregados. Clique em Salvar perfil para manter.');
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function makeEditorProfileDefault() {
  if (!editorProfileId) { toast('Salve o perfil primeiro.', 'error'); return; }
  try {
    await api(`/api/personalities/${encodeURIComponent(editorProfileId)}/default`, { method: 'POST' });
    if (!currentConversationId) currentPersonalityId = editorProfileId;
    await loadProfiles();
    loadProfileIntoEditor(profilesCache.find(p => p.id === editorProfileId));
    toast('Perfil padrão alterado');
  } catch (err) {
    toast(`Falha: ${err.message}`, 'error');
  }
}

async function deleteEditorProfile() {
  const p = profilesCache.find(x => x.id === editorProfileId);
  if (!p) return;
  if (!confirm(`Excluir o perfil "${p.name}"? Esta ação não pode ser desfeita.`)) return;
  try {
    await api(`/api/personalities/${encodeURIComponent(p.id)}`, { method: 'DELETE' });
    if (currentPersonalityId === p.id) currentPersonalityId = null;
    await loadProfiles();
    loadProfileIntoEditor(activeProfile());
    toast('Perfil excluído');
  } catch (err) {
    toast(err.message, 'error');
  }
}

// ----------------- Conversations -----------------
async function loadConversations() {
  try {
    conversationsCache = await api('/api/conversations');
    renderConversationList();
  } catch (err) {
    console.error('Failed to load conversations', err);
  }
}

function parseDbDate(value) {
  if (!value) return null;
  const iso = String(value).includes('T') ? String(value) : String(value).replace(' ', 'T') + 'Z';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

function dateGroup(d) {
  if (!d) return 'Mais antigas';
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const days = (startOfToday - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 86400000;
  if (days <= 0) return 'Hoje';
  if (days === 1) return 'Ontem';
  if (days < 7) return 'Últimos 7 dias';
  if (days < 30) return 'Últimos 30 dias';
  return 'Mais antigas';
}

function renderConversationList() {
  const q = ($('searchConversations').value || '').toLowerCase().trim();
  // Projects are isolated: the sidebar shows only the selected scope.
  const list = conversationsCache
    .filter(c => (c.project_id || null) === (currentProjectId || null))
    .filter(c => !q || (c.title || '').toLowerCase().includes(q));
  conversationsList.innerHTML = '';
  if (!list.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-hint';
    empty.textContent = q ? 'Nenhuma conversa encontrada.' : 'Suas conversas aparecem aqui.';
    conversationsList.appendChild(empty);
    return;
  }
  let lastGroup = null;
  list.forEach(c => {
    const group = dateGroup(parseDbDate(c.updated_at || c.created_at));
    if (group !== lastGroup) {
      const label = document.createElement('div');
      label.className = 'group-label';
      label.textContent = group;
      conversationsList.appendChild(label);
      lastGroup = group;
    }
    const item = document.createElement('div');
    item.className = `list-item ${c.id === currentConversationId ? 'active' : ''}`;
    item.dataset.id = c.id;
    item.dataset.title = c.title || '';
    item.innerHTML = `
      <span class="list-item-title"></span>
      <span class="item-actions">
        <button class="icon-btn" title="Renomear">${icon('pencil')}</button>
        <button class="icon-btn danger" title="Excluir conversa">${icon('trash')}</button>
      </span>`;
    item.querySelector('.list-item-title').textContent = c.title || 'Sem título';
    item.addEventListener('click', () => switchConversation(c.id));
    const [renameBtn, delBtn] = item.querySelectorAll('button');
    renameBtn.addEventListener('click', (e) => { e.stopPropagation(); startInlineRename(item, c); });
    delBtn.addEventListener('click', (e) => deleteConversationById(c.id, e));
    conversationsList.appendChild(item);
  });
}

function startInlineRename(item, conv) {
  const titleEl = item.querySelector('.list-item-title');
  const input = document.createElement('input');
  input.className = 'rename-input';
  input.value = conv.title || '';
  input.maxLength = 120;
  titleEl.replaceWith(input);
  input.focus();
  input.select();
  let done = false;
  const finish = async (save) => {
    if (done) return;
    done = true;
    const title = input.value.trim();
    if (save && title && title !== conv.title) await renameConversation(conv.id, title);
    else renderConversationList();
  };
  input.addEventListener('click', (e) => e.stopPropagation());
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') finish(true);
    if (e.key === 'Escape') { e.stopPropagation(); finish(false); }
  });
  input.addEventListener('blur', () => finish(true));
}

async function renameConversation(id, title) {
  try {
    await api(`/api/conversations/${id}`, { method: 'PUT', body: { title } });
    if (id === currentConversationId) currentChatTitle.textContent = title;
    await loadConversations();
  } catch (err) {
    toast(`Falha ao renomear: ${err.message}`, 'error');
    renderConversationList();
  }
}

function startTitleEdit() {
  if (!currentConversationId || currentChatTitle.isContentEditable) return;
  const original = currentChatTitle.textContent;
  currentChatTitle.contentEditable = 'true';
  currentChatTitle.focus();
  document.getSelection().selectAllChildren(currentChatTitle);
  const finish = async (save) => {
    currentChatTitle.contentEditable = 'false';
    currentChatTitle.removeEventListener('keydown', onKey);
    currentChatTitle.removeEventListener('blur', onBlur);
    const title = currentChatTitle.textContent.trim().slice(0, 120);
    if (save && title && title !== original) await renameConversation(currentConversationId, title);
    else currentChatTitle.textContent = original;
  };
  const onKey = (e) => {
    if (e.key === 'Enter') { e.preventDefault(); currentChatTitle.blur(); }
    if (e.key === 'Escape') { e.stopPropagation(); currentChatTitle.textContent = original; currentChatTitle.blur(); }
  };
  const onBlur = () => finish(true);
  currentChatTitle.addEventListener('keydown', onKey);
  currentChatTitle.addEventListener('blur', onBlur);
}

function setEmptyState(empty) {
  chatMain.classList.toggle('is-empty', empty);
}

// The Biblioteca covers the chat; going to a conversation leaves it.
function leaveLibrary() {
  if (!window.VictoriqueLibrary || !window.VictoriqueLibrary.isOpen()) return;
  const tab = document.querySelector('.nav-tab[data-tab="conversations"]');
  if (tab) tab.click();
}

function startNewChat() {
  leaveLibrary();
  if (isGenerating) abortGeneration(true);
  currentConversationId = null;
  currentChatTitle.textContent = 'Nova conversa';
  messagesList.innerHTML = '';
  setEmptyState(true);
  const def = profilesCache.find(p => p.is_default);
  if (def) currentPersonalityId = def.id;
  updateProfileUi();
  document.querySelectorAll('.conversations-list .list-item').forEach(i => i.classList.remove('active'));
  updateSendState();
  chatInput.focus();
}

async function switchConversation(convId) {
  leaveLibrary();
  if (isGenerating) {
    abortGeneration(true);
    await delay(450);
  }
  currentConversationId = convId;
  document.querySelectorAll('.conversations-list .list-item').forEach(i => {
    i.classList.toggle('active', i.dataset.id === convId);
  });

  try {
    const data = await api(`/api/conversations/${convId}/messages`);
    const conv = data.conversation;
    currentChatTitle.textContent = conv.title;
    currentProjectId = conv.project_id || null;
    if (conv.personality_id && profilesCache.some(p => p.id === conv.personality_id)) {
      currentPersonalityId = conv.personality_id;
    }
    updateProfileUi();
    updateProjectTag();
    messagesList.innerHTML = '';
    setEmptyState(false);

    data.messages.forEach(m => {
      if (m.role === 'user' || m.role === 'assistant') {
        renderMessage(m.role, m.content, m.sources, {
          reasoning: m.reasoning, reasoningSeconds: m.reasoning_seconds, attachments: m.attachments,
        });
      }
    });
    scrollToBottom();
    await loadConversations();
    await loadDocuments();
    await loadMemories();
  } catch (err) {
    console.error('Failed to switch conversation', err);
    toast(`Falha ao abrir conversa: ${err.message}`, 'error');
  }
}

// ----------------- Messaging & Streaming -----------------
async function sendMessage() {
  const text = chatInput.value.trim();
  if (isGenerating) return;
  if (pendingAttachments.some(a => a.status === 'uploading')) {
    toast('Espere os anexos terminarem de subir.');
    return;
  }
  const sentAttachments = pendingAttachments.filter(a => a.status === 'ready');
  if (!text && !sentAttachments.length) return;

  if (!currentConversationId) {
    try {
      const conv = await api('/api/conversations', {
        method: 'POST',
        body: {
          title: (text || sentAttachments[0].name).slice(0, 60),
          project_id: currentProjectId,
          personality_id: currentPersonalityId,
        }
      });
      currentConversationId = conv.id;
      currentChatTitle.textContent = conv.title;
    } catch (err) {
      toast(`Não foi possível criar a conversa: ${err.message}`, 'error');
      return;
    }
  }

  chatInput.value = '';
  autoGrow();
  setEmptyState(false);
  pendingAttachments = [];
  renderAttachTray();

  renderMessage('user', text, null, {
    attachments: sentAttachments.map(a => ({ id: a.id, name: a.name, kind: a.kind, size: a.size, url: a.url })),
  });
  const assistantMsgEl = renderMessage('assistant', '');
  assistantMsgEl.classList.add('streaming');
  const body = assistantMsgEl.querySelector('.msg-body');
  const bubble = assistantMsgEl.querySelector('.message-bubble');
  bubble.innerHTML = `<span class="thinking">${PIPE_SVG}${escape(activeProfileName())} está pensando…</span>`;

  const toolDetails = document.createElement('details');
  toolDetails.className = 'tool-events';
  toolDetails.hidden = true;
  toolDetails.innerHTML = `<summary>${icon('sliders', 'ic ic-sm')}<span class="tool-summary">Usando ferramentas</span></summary>`;
  const toolBox = document.createElement('div');
  toolBox.className = 'tool-list';
  toolDetails.appendChild(toolBox);
  body.insertBefore(toolDetails, bubble);
  const citationsContainer = document.createElement('div');
  citationsContainer.className = 'citations-box';
  body.insertBefore(citationsContainer, body.querySelector('.msg-actions'));

  isGenerating = true;
  visual.generating = true;
  visual.streaming = false;
  noteActivity();
  refreshVisualState();
  btnSend.hidden = true;
  btnStop.hidden = false;
  activeAbortController = new AbortController();
  let accumulated = '';
  let reasoningBox = null;  // raciocínio interno do modelo
  let thoughtBox = null;    // Pensamento profundo, na voz dela
  let aborted = false;
  const deepThinking = !!prefs.deep_thinking;

  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: activeAbortController.signal,
      body: JSON.stringify({
        conversation_id: currentConversationId,
        message: text,
        attachments: sentAttachments.map(a => a.id),
        model: selectedModel || undefined,
        backend: currentBackend || undefined,
        project_id: currentProjectId,
        personality_id: currentPersonalityId,
        enable_rag: prefs.enable_rag !== false,
        deep_thinking: deepThinking,
      })
    });

    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try { detail = (await response.json()).detail || detail; } catch (_) { /* ignore */ }
      throw new Error(detail);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split(/\r?\n\r?\n/);
      buffer = events.pop();

      for (const block of events) {
        const dataLines = block.split(/\r?\n/)
          .filter(line => line.startsWith('data:'))
          .map(line => line.slice(5).trimStart());
        if (!dataLines.length) continue;

        let data;
        try {
          data = JSON.parse(dataLines.join('\n'));
        } catch (e) {
          console.error('SSE JSON error', e, block);
          continue;
        }

        if (data.type === 'meta') {
          if (data.conversation_id) currentConversationId = data.conversation_id;
          if (data.model) { selectedModel = data.model; updateModelTag(); }
        } else if (data.type === 'sources') {
          renderCitations(citationsContainer, data.data || []);
        } else if (data.type === 'tool_call') {
          if (thoughtBox) thoughtBox.setLive(false);
          const args = JSON.stringify(data.arguments || {});
          appendToolEvent(
            toolBox,
            `▸ ${data.tool} ${args.length > 160 ? args.slice(0, 160) + '…' : args}`,
            'tool-event-running'
          );
        } else if (data.type === 'tool_result') {
          let detail = '';
          const payload = data.result && data.result.result;
          if (payload !== undefined) {
            try {
              detail = JSON.stringify(payload);
            } catch (_) {
              detail = String(payload);
            }
            if (detail.length > 300) detail = detail.slice(0, 300) + '…';
          }
          const ok = data.status === 'success';
          if (ok && window.VictoriqueLibrary) window.VictoriqueLibrary.notifyActivity();
          appendToolEvent(
            toolBox,
            `${ok ? '✓' : '!'} ${data.tool} (${data.status})${detail ? ' — ' + detail : ''}`,
            ok ? 'tool-event-ok' : 'tool-event-error'
          );
        } else if (data.type === 'authorization_required') {
          appendToolEvent(
            toolBox,
            `Autorização necessária: ${data.tool_name || data.tool || 'ação'} — ${data.resource || ''}`,
            'tool-event-auth'
          );
          checkPendingAuthorizations(true);
        } else if (data.type === 'reasoning') {
          // Never part of the answer. data.voice = her own thought (Pensamento
          // profundo), shown like DeepSeek; otherwise the model's internal one.
          if (data.voice) {
            if (!thoughtBox) {
              thoughtBox = createThoughtBox(true, { live: true });
              body.insertBefore(thoughtBox.el, toolDetails);
              if (bubble.querySelector('.thinking')) bubble.innerHTML = '';
            }
            thoughtBox.append(data.content || '');
          } else {
            if (!reasoningBox) {
              reasoningBox = createThoughtBox(false);
              body.insertBefore(reasoningBox.el, toolDetails);
            }
            reasoningBox.append(data.content || '');
          }
          scrollToBottom(true);
        } else if (data.type === 'notice') {
          appendToolEvent(toolBox, `${data.message}`, 'tool-event-notice');
        } else if (data.type === 'avatar') {
          sendMascotSignal({ expression: data.expression || null, gesture: data.gesture || null });
        } else if (data.type === 'token') {
          if (thoughtBox) thoughtBox.setLive(false);
          if (!visual.streaming) { visual.streaming = true; refreshVisualState(); }
          accumulated += data.content || '';
          bubble.innerHTML = md(accumulated);
          scrollToBottom(true);
        } else if (data.type === 'error') {
          const errBox = document.createElement('div');
          errBox.className = 'stream-error';
          errBox.textContent = `Erro do modelo: ${data.message}`;
          markVisualError();
          body.insertBefore(errBox, citationsContainer);
        } else if (data.type === 'done') {
          if (thoughtBox) thoughtBox.finish(data.reasoning_seconds);
          refreshOrganizerIfOpen();
          if (window.VictoriqueLibrary) window.VictoriqueLibrary.notifyActivity();
          if (data.conversation_id) currentConversationId = data.conversation_id;
          accumulated = data.content || accumulated;
          bubble.innerHTML = md(accumulated);
        }
      }
    }
  } catch (err) {
    if (err.name === 'AbortError') {
      aborted = true;
      if (!accumulated) bubble.innerHTML = '';
      const note = document.createElement('div');
      note.className = 'cancelled-note';
      note.textContent = 'Resposta interrompida.';
      body.insertBefore(note, citationsContainer);
    } else {
      bubble.innerHTML = `<p class="text-danger">Erro de comunicação: ${escape(err.message)}</p>`;
      markVisualError();
    }
  } finally {
    isGenerating = false;
    visual.generating = false;
    visual.streaming = false;
    if (thoughtBox) thoughtBox.setLive(false);
    if (accumulated && prefs.tts_speak_responses && ttsAvailable) markSpeaking(accumulated);
    refreshVisualState();
    if (accumulated && !aborted) tellMascotReply(accumulated);
    activeAbortController = null;
    assistantMsgEl.classList.remove('streaming');
    if (bubble.querySelector('.thinking')) bubble.innerHTML = '';
    if (!accumulated && !aborted && !body.querySelector('.stream-error') && !bubble.textContent.trim()) {
      const errBox = document.createElement('div');
      errBox.className = 'stream-error';
      errBox.textContent = 'O modelo não respondeu. Confira se o motor do modo escolhido está rodando (status no canto inferior esquerdo).';
      body.insertBefore(errBox, citationsContainer);
    }
    enhanceCodeBlocks(bubble);
    bindMessageActions(assistantMsgEl, () => accumulated);
    btnSend.hidden = false;
    btnStop.hidden = true;
    updateSendState();
    scrollToBottom();
    await loadConversations();

    if (aborted && currentConversationId) {
      await delay(600);
      await switchConversation(currentConversationId);
    }
    checkPendingAuthorizations();
  }
}

function abortGeneration(silent = false) {
  if (activeAbortController) {
    activeAbortController.abort();
    if (!silent) btnStop.title = 'Cancelando…';
  }
}

function renderMessage(role, content, sources = null, { reasoning = '', reasoningSeconds = null, attachments = null } = {}) {
  const msg = document.createElement('div');
  msg.className = `message ${role}`;
  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  const actions = document.createElement('div');
  actions.className = 'msg-actions';

  if (role === 'user') {
    if (attachments && attachments.length) msg.appendChild(renderAttachments(attachments));
    bubble.textContent = content;
    if (content) msg.appendChild(bubble);
    msg.appendChild(actions);
  } else {
    const avatar = document.createElement('div');
    avatar.className = 'msg-avatar';
    paintAvatar(avatar, activeProfile());
    const body = document.createElement('div');
    body.className = 'msg-body';
    bubble.innerHTML = md(content || '');
    if (reasoning) body.appendChild(createThoughtBox(true, { text: reasoning, seconds: reasoningSeconds }).el);
    body.appendChild(bubble);
    if (sources && sources.length > 0) {
      const box = document.createElement('div');
      box.className = 'citations-box';
      renderCitations(box, sources);
      body.appendChild(box);
    }
    body.appendChild(actions);
    msg.appendChild(avatar);
    msg.appendChild(body);
    enhanceCodeBlocks(bubble);
  }

  messagesList.appendChild(msg);
  if (content) bindMessageActions(msg, () => content);
  scrollToBottom();
  return msg;
}

function bindMessageActions(msg, getText) {
  const actions = msg.querySelector('.msg-actions');
  if (!actions || !getText()) return;
  actions.innerHTML = '';
  const add = (name, title, handler, extraClass = '') => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = `icon-btn ${extraClass}`.trim();
    b.title = title;
    b.setAttribute('aria-label', title);
    b.innerHTML = icon(name);
    b.addEventListener('click', () => handler(b));
    actions.appendChild(b);
    return b;
  };
  add('copy', 'Copiar', (b) => copyText(getText(), b));
  if (msg.classList.contains('user')) {
    add('pencil', 'Editar e reenviar', () => setPrompt(getText()));
  } else {
    const speak = add('volume', 'Ler em voz alta', () => speakText(getText()), 'btn-speak');
    speak.hidden = !ttsAvailable;
  }
}

function enhanceCodeBlocks(bubble) {
  bubble.querySelectorAll('pre').forEach(pre => {
    if (pre.querySelector('.code-copy')) return;
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'code-copy';
    b.innerHTML = `${icon('copy')}Copiar`;
    b.addEventListener('click', () => copyText(pre.querySelector('code') ? pre.querySelector('code').textContent : pre.textContent, b));
    pre.appendChild(b);
  });
}

function appendToolEvent(container, text, className) {
  if (!container) return;
  const line = document.createElement('div');
  line.className = `tool-event ${className || ''}`.trim();
  line.textContent = text;
  container.appendChild(line);
  const details = container.closest('details');
  if (details) {
    details.hidden = false;
    const calls = container.querySelectorAll('.tool-event-running').length;
    const summary = details.querySelector('.tool-summary');
    if (summary) {
      summary.textContent = calls
        ? `Usou ${calls} ${calls === 1 ? 'ferramenta' : 'ferramentas'}`
        : 'Avisos';
    }
    if (className === 'tool-event-auth' || className === 'tool-event-error') details.open = true;
  }
  scrollToBottom(true);
}

function renderCitations(container, sources) {
  container.innerHTML = '';
  (sources || []).forEach(s => {
    const pill = document.createElement('span');
    pill.className = 'citation-pill';
    const page = s.page ? `pág. ${s.page}` : 'página não informada';
    pill.innerHTML = icon('book');
    pill.appendChild(document.createTextNode(`${s.document || 'Documento'} (${page})`));
    if (s.score != null) pill.title = `Relevância: ${s.score}`;
    container.appendChild(pill);
  });
}

// soft: only follow the stream when the user is already near the bottom.
function scrollToBottom(soft = false) {
  const container = $('messagesContainer');
  if (soft && container.scrollHeight - container.scrollTop - container.clientHeight > 160) return;
  container.scrollTop = container.scrollHeight;
}

// ----------------- Security Authorizations -----------------
// force: show the bar even mid-stream. Claude Code waits for the answer inside
// the turn, while the local engine ends its turn before asking.
async function checkPendingAuthorizations(force = false) {
  if (isGenerating && !force) return;
  try {
    const pending = await api('/api/security/pending');
    if (pending.length > 0) {
      const act = pending[0];
      authTitle.textContent = `Autorizar: ${act.description || String(act.action_type || 'ação protegida')}`;
      authDesc.textContent = `Alvo: ${act.resource || '—'} · expira ${act.expires_at_iso ? new Date(act.expires_at_iso).toLocaleTimeString('pt-BR') : '—'}`;
      authPayload.textContent = JSON.stringify(act.payload || {}, null, 2).slice(0, 3000);
      renderAuthPlan(act.payload || {});
      authBar.hidden = false;

      btnApproveAction.onclick = () => resolveAuth(act.id, true, act.kind);
      btnRejectAction.onclick = () => resolveAuth(act.id, false, act.kind);
    } else {
      authBar.hidden = true;
    }
  } catch (err) {
    console.error('Pending auth check failed', err);
  }
}

// Moves shown as origem → destino, so the user approves the plan, not a JSON blob.
function planSteps(payload) {
  if (Array.isArray(payload.moves)) {
    return payload.moves.map(m => [m.origem || m.src || '?', m.destino || m.dst || '?']);
  }
  if (Array.isArray(payload.paths)) return payload.paths.map(p => [p, 'Reserva (_Quarentena)']);
  if (payload.path && payload.new_name) return [[payload.path, payload.new_name]];
  return [];
}

function shortPath(path) {
  const parts = String(path).split(/[\\/]+/).filter(Boolean);
  return parts.length > 3 ? `…\\${parts.slice(-3).join('\\')}` : String(path);
}

function renderAuthPlan(payload) {
  const list = $('authPlan');
  list.innerHTML = '';
  const steps = planSteps(payload);
  list.hidden = steps.length === 0;
  const MAX_STEPS = 40;
  steps.slice(0, MAX_STEPS).forEach(([from, to]) => {
    const li = document.createElement('li');
    const a = document.createElement('span');
    a.className = 'plan-from';
    a.textContent = shortPath(from);
    a.title = from;
    const b = document.createElement('span');
    b.className = 'plan-to';
    b.textContent = shortPath(to);
    b.title = to;
    li.append(a, document.createTextNode(' → '), b);
    list.appendChild(li);
  });
  if (steps.length > MAX_STEPS) {
    const li = document.createElement('li');
    li.className = 'plan-more';
    li.textContent = `e mais ${steps.length - MAX_STEPS} item(ns); veja os detalhes.`;
    list.appendChild(li);
  }
}

// ----------------- Organizer (moves history, undo) -----------------
const OPERATION_LABELS = { move: 'Movidos', rename: 'Renomeado', reserve: 'Na Reserva' };

async function loadOperations() {
  const list = $('operationsList');
  try {
    const batches = await api('/api/operations');
    list.innerHTML = '';
    if (!batches.length) {
      const empty = document.createElement('p');
      empty.className = 'empty-hint';
      empty.textContent = 'Nenhum arquivo foi movido ainda. Peça à assistente para organizar uma pasta: ela mostra o plano e você aprova antes.';
      list.appendChild(empty);
      return;
    }
    batches.forEach(b => list.appendChild(operationItem(b)));
  } catch (err) {
    list.innerHTML = '';
    toast(`Falha ao carregar o histórico: ${err.message}`, 'error');
  }
}

function operationItem(batch) {
  const item = document.createElement('details');
  item.className = `operation-item ${batch.status === 'undone' ? 'undone' : ''}`;
  const when = new Date(batch.created_at).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
  const state = batch.status === 'undone' ? 'desfeito' : `${batch.ops.length} item(ns)`;
  item.innerHTML = `
    <summary>
      <span class="list-item-title"><span class="op-title"></span><span class="list-sub"></span></span>
    </summary>
    <ol class="op-steps"></ol>`;
  item.querySelector('.op-title').textContent = batch.description;
  item.querySelector('.list-sub').textContent =
    `${OPERATION_LABELS[batch.kind] || batch.kind} · ${state} · ${when}`;
  const steps = item.querySelector('.op-steps');
  batch.ops.forEach(op => {
    const li = document.createElement('li');
    li.textContent = `${shortPath(op.src)} → ${shortPath(op.dst)}`;
    li.title = `${op.src}\n→ ${op.dst}`;
    steps.appendChild(li);
  });
  if (batch.status !== 'undone') {
    const btn = document.createElement('button');
    btn.className = 'chip-btn op-undo';
    btn.innerHTML = `${icon('undo')}Desfazer`;
    // Two clicks: the first arms the button, the second puts everything back.
    btn.addEventListener('click', async () => {
      if (!btn.classList.contains('armed')) {
        btn.classList.add('armed');
        btn.innerHTML = `${icon('undo')}Devolver ${batch.ops.length} item(ns)?`;
        setTimeout(() => {
          if (btn.isConnected && btn.classList.contains('armed')) {
            btn.classList.remove('armed');
            btn.innerHTML = `${icon('undo')}Desfazer`;
          }
        }, 5000);
        return;
      }
      btn.disabled = true;
      try {
        const res = await api(`/api/operations/${batch.id}/undo`, { method: 'POST' });
        toast(`Desfeito: ${res.restored} item(ns) voltaram ao lugar.`);
      } catch (err) {
        toast(err.message, 'error');
      }
      loadOperations();
    });
    item.appendChild(btn);
  }
  return item;
}

async function resolveAuth(actionId, approved, kind) {
  try {
    const data = await api('/api/security/authorize', {
      method: 'POST',
      body: { action_id: actionId, approved }
    });
    authBar.hidden = true;
    if (approved) setTimeout(refreshOrganizerIfOpen, 1500);
    if (kind === 'claude_code') {
      // Claude Code runs (or skips) the tool itself; the open stream shows it.
    } else if (data.status === 'executed') {
      renderToolResult(data.result);
    } else {
      renderMessage('assistant', `Ação **${approved ? 'não executada' : 'recusada'}**: ${data.status}`);
    }
  } catch (err) {
    authBar.hidden = true;
    toast(`Falha ao resolver autorização: ${err.message}`, 'error');
  }
  checkPendingAuthorizations(kind === 'claude_code');
}

function refreshOrganizerIfOpen() {
  if ($('paneOrganizer').classList.contains('active')) loadOperations();
}

function renderToolResult(result) {
  setEmptyState(false);
  const msg = renderMessage('assistant', '**Resultado da ferramenta:**');
  const pre = document.createElement('pre');
  pre.className = 'tool-result';
  pre.textContent = JSON.stringify(result, null, 2);
  msg.querySelector('.msg-body').appendChild(pre);
}

// ----------------- Documents (RAG) -----------------
async function loadDocuments() {
  try {
    const all = await api('/api/documents');
    const docs = all.filter(d => (d.project_id || null) === (currentProjectId || null));
    renderDocumentList($('documentsList'), docs);
    renderDocumentList($('libraryModalList'), docs);
  } catch (err) {
    console.error('Failed to load documents', err);
  }
}

function renderDocumentList(container, docs) {
  if (!container) return;
  container.innerHTML = '';
  if (!docs.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-hint';
    empty.textContent = 'Nenhum documento ainda. Importe um PDF, TXT ou MD para consultar com citação de página.';
    container.appendChild(empty);
    return;
  }
  docs.forEach(d => {
    const item = document.createElement('div');
    item.className = 'list-item';
    item.innerHTML = `
      ${icon('book')}
      <span class="list-item-title"><span class="doc-title"></span><span class="list-sub"></span></span>
      <span class="item-actions"><button class="icon-btn danger" title="Remover documento">${icon('trash')}</button></span>`;
    item.querySelector('.doc-title').textContent = d.title;
    item.querySelector('.list-sub').textContent = `${d.total_pages} pág. · ${d.total_chunks} trechos`;
    item.querySelector('button').addEventListener('click', (e) => deleteDocument(d.id, e));
    container.appendChild(item);
  });
}

async function handleFileUpload(e) {
  const file = e.target.files[0];
  e.target.value = '';
  if (!file) return;

  const ext = fileExt(file.name);
  const allowed = ['.pdf', '.txt', '.md', '.docx', '.epub', '.xlsx', '.xlsm', '.xls', '.pptx', '.csv', '.tsv'];
  if (!allowed.includes(ext)) {
    toast('Formato não suportado. Use PDF, Word, Excel, PowerPoint, EPUB, CSV, TXT ou MD.', 'error');
    return;
  }
  if (file.size > 50 * 1024 * 1024) {
    toast('Arquivo maior que 50 MB.', 'error');
    return;
  }

  const formData = new FormData();
  formData.append('file', file);
  formData.append('collection', 'Geral');
  if (currentProjectId) formData.append('project_id', currentProjectId);

  toast(`Indexando ${file.name}…`);
  try {
    const data = await api('/api/documents/upload', { method: 'POST', body: formData });
    toast(`${data.title} indexado (${data.total_pages} páginas, ${data.total_chunks} trechos)`);
    await loadDocuments();
  } catch (err) {
    toast(`Falha ao indexar: ${err.message}`, 'error');
  }
}

async function deleteDocument(docId, event) {
  if (event) event.stopPropagation();
  if (!confirm('Excluir este documento da biblioteca? A cópia indexada e o arquivo armazenado serão removidos.')) return;
  try {
    await api(`/api/documents/${docId}`, { method: 'DELETE' });
    await loadDocuments();
    toast('Documento removido');
  } catch (err) {
    toast(`Falha ao excluir: ${err.message}`, 'error');
  }
}

function openLibraryModal() {
  loadDocuments();
  openModal('libraryModal');
}

// ----------------- Memories -----------------
const MEMORY_LABELS = { preference: 'Preferência', fact: 'Fato', decision: 'Decisão', project: 'Caso', instruction: 'Instrução' };

async function loadMemories() {
  try {
    const all = await api('/api/memories');
    const memories = all.filter(m => {
      if (!currentProjectId) return !m.project_id;
      return !m.project_id || m.project_id === currentProjectId;
    });
    const list = $('memoriesList');
    list.innerHTML = '';
    if (!memories.length) {
      const empty = document.createElement('p');
      empty.className = 'empty-hint';
      empty.textContent = 'Nenhuma memória. Adicione fatos e preferências que a assistente deve lembrar sempre.';
      list.appendChild(empty);
      return;
    }
    const projectName = (id) => {
      const p = projectsCache.find(x => x.id === id);
      return p ? p.name : 'caso';
    };

    memories.forEach(m => {
      const item = document.createElement('div');
      item.className = `list-item memory-item ${m.is_active ? '' : 'inactive'}`;
      const scope = m.project_id ? projectName(m.project_id) : 'Global';
      item.innerHTML = `
        <span class="list-item-title"><span class="mem-text"></span><span class="list-sub"></span></span>
        <span class="item-actions">
          <button class="icon-btn" title="${m.is_active ? 'Desativar' : 'Ativar'}">${icon(m.is_active ? 'pause' : 'play')}</button>
          <button class="icon-btn" title="Editar">${icon('pencil')}</button>
          <button class="icon-btn danger" title="Excluir">${icon('trash')}</button>
        </span>`;
      item.querySelector('.mem-text').textContent = m.content;
      item.querySelector('.list-sub').textContent =
        `${MEMORY_LABELS[m.category] || m.category} · ${scope}${m.is_active ? '' : ' · inativa'}`;
      const [toggleBtn, editBtn, delBtn] = item.querySelectorAll('button');
      toggleBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        try {
          await api(`/api/memories/${m.id}`, {
            method: 'PUT',
            body: { content: m.content, category: m.category, is_active: !m.is_active }
          });
          await loadMemories();
        } catch (err) { toast(`Falha: ${err.message}`, 'error'); }
      });
      editBtn.addEventListener('click', (e) => { e.stopPropagation(); openMemoryModal(m); });
      delBtn.addEventListener('click', (e) => { e.stopPropagation(); deleteMemory(m.id); });
      list.appendChild(item);
    });
  } catch (err) {
    console.error('Failed to load memories', err);
  }
}

async function deleteMemory(id, event) {
  if (event) event.stopPropagation();
  if (!confirm('Excluir esta memória permanentemente?')) return;
  try {
    await api(`/api/memories/${id}`, { method: 'DELETE' });
    await loadMemories();
    toast('Memória excluída');
  } catch (err) {
    toast(`Falha ao excluir: ${err.message}`, 'error');
  }
}

function openMemoryModal(mem = null) {
  $('memoryId').value = mem ? mem.id : '';
  $('memoryModalTitle').textContent = mem ? 'Editar memória' : 'Nova memória';
  $('memoryCategory').value = mem ? mem.category : 'preference';
  $('memoryContent').value = mem ? mem.content : '';
  updateMemoryProjectOptions(mem ? mem.project_id : currentProjectId);
  openModal('memoryModal');
  $('memoryContent').focus();
}

async function saveMemory() {
  const id = $('memoryId').value;
  const payload = {
    category: $('memoryCategory').value,
    content: $('memoryContent').value,
    project_id: $('memoryProject').value || null,
  };
  if (!payload.content.trim()) { toast('Escreva o conteúdo da memória.', 'error'); return; }

  try {
    if (id) {
      await api(`/api/memories/${id}`, {
        method: 'PUT',
        body: { content: payload.content, category: payload.category }
      });
    } else {
      await api('/api/memories', { method: 'POST', body: payload });
    }
    closeModal('memoryModal');
    await loadMemories();
    toast('Memória salva');
  } catch (err) {
    toast(`Falha ao salvar memória: ${err.message}`, 'error');
  }
}

// ----------------- Projects -----------------
async function loadProjects() {
  try {
    projectsCache = await api('/api/projects');
    const open = projectsCache.filter(p => !p.archived);
    const archived = projectsCache.filter(p => p.archived);
    const list = $('projectsList');
    list.innerHTML = '';
    if (!open.length) {
      const empty = document.createElement('p');
      empty.className = 'empty-hint';
      empty.textContent = 'Nenhum caso aberto. Crie um para separar conversas, memórias e documentos de um assunto.';
      list.appendChild(empty);
    }
    open.forEach(p => list.appendChild(projectItem(p)));

    const archivedList = $('archivedList');
    archivedList.innerHTML = '';
    archived.forEach(p => archivedList.appendChild(projectItem(p)));
    $('archivedCases').hidden = archived.length === 0;
    $('archivedSummary').textContent = `Casos arquivados (${archived.length})`;
    updateMemoryProjectOptions();
  } catch (err) {
    console.error('Failed to load projects', err);
  }
}

function projectItem(p) {
  const item = document.createElement('div');
  item.className = `list-item ${p.id === currentProjectId ? 'active' : ''} ${p.archived ? 'archived' : ''}`;
  item.dataset.projectId = p.id;
  item.innerHTML = `
    ${icon(p.archived ? 'archive' : 'folder')}
    <span class="list-item-title"></span>
    <span class="item-actions">
      <button class="icon-btn" title="Editar caso">${icon('pencil')}</button>
      <button class="icon-btn" title="${p.archived ? 'Reabrir caso' : 'Arquivar caso'}">${icon(p.archived ? 'unarchive' : 'archive')}</button>
      <button class="icon-btn danger" title="Excluir caso">${icon('trash')}</button>
    </span>`;
  item.querySelector('.list-item-title').textContent = p.name;
  item.title = p.id === currentProjectId ? 'Clique para sair do caso' : 'Clique para abrir o caso';
  item.addEventListener('click', () => selectProject(p));
  const [editBtn, archiveBtn, delBtn] = item.querySelectorAll('button');
  editBtn.addEventListener('click', (e) => { e.stopPropagation(); openProjectModal(p); });
  archiveBtn.addEventListener('click', (e) => { e.stopPropagation(); archiveProject(p, !p.archived); });
  delBtn.addEventListener('click', (e) => { e.stopPropagation(); deleteProject(p); });
  return item;
}

async function archiveProject(project, archived) {
  try {
    await api(`/api/projects/${project.id}/archive`, { method: 'POST', body: { archived } });
    if (archived && currentProjectId === project.id) {
      currentProjectId = null;
      updateProjectTag();
      startNewChat();
      await Promise.all([loadConversations(), loadDocuments(), loadMemories()]);
    }
    await loadProjects();
    toast(archived ? `Caso "${project.name}" arquivado` : `Caso "${project.name}" reaberto`);
  } catch (err) {
    toast(`Falha: ${err.message}`, 'error');
  }
}

async function selectProject(project) {
  if (currentProjectId === project.id) {
    currentProjectId = null;
  } else {
    currentProjectId = project.id;
  }
  updateProjectTag();
  startNewChat();
  await Promise.all([loadProjects(), loadConversations(), loadDocuments(), loadMemories()]);
}

function updateProjectTag() {
  const tag = $('activeProjectTag');
  if (!currentProjectId) {
    tag.hidden = true;
    tag.textContent = '';
    return;
  }
  const p = projectsCache.find(x => x.id === currentProjectId);
  tag.textContent = p ? p.name : 'Caso';
  tag.hidden = false;
  document.querySelectorAll('#projectsList .list-item').forEach((item) => {
    item.classList.toggle('active', item.dataset.projectId === currentProjectId);
  });
}

function openProjectModal(project = null) {
  $('projectId').value = project ? project.id : '';
  $('projectModalTitle').textContent = project ? 'Editar caso' : 'Novo caso';
  $('projectName').value = project ? project.name : '';
  $('projectDescription').value = project ? (project.description || '') : '';
  $('projectInstructions').value = project ? (project.instructions || '') : '';
  openModal('projectModal');
  $('projectName').focus();
}

async function saveProject() {
  const id = $('projectId').value;
  const payload = {
    name: $('projectName').value.trim(),
    description: $('projectDescription').value,
    instructions: $('projectInstructions').value,
  };
  if (!payload.name) { toast('Informe o nome do caso.', 'error'); return; }

  try {
    if (id) {
      await api(`/api/projects/${id}`, { method: 'PUT', body: payload });
    } else {
      const saved = await api('/api/projects', { method: 'POST', body: payload });
      currentProjectId = saved.id;
    }
    closeModal('projectModal');
    await loadProjects();
    updateProjectTag();
    if (!id) { startNewChat(); await Promise.all([loadConversations(), loadDocuments(), loadMemories()]); }
    toast('Caso salvo');
  } catch (err) {
    toast(`Falha ao salvar o caso: ${err.message}`, 'error');
  }
}

async function deleteProject(project) {
  const warning = 'Excluir o caso "' + project.name + '"?\n\nIsso remove também memórias e documentos vinculados. Conversas ficam sem caso. Esta ação não pode ser desfeita (faça um backup antes). Para só guardar o caso, use Arquivar.';
  if (!confirm(warning)) return;
  try {
    await api(`/api/projects/${project.id}`, { method: 'DELETE' });
    if (currentProjectId === project.id) { currentProjectId = null; updateProjectTag(); startNewChat(); }
    await Promise.all([loadProjects(), loadMemories(), loadDocuments(), loadConversations()]);
    toast('Caso excluído');
  } catch (err) {
    toast(`Falha ao excluir o caso: ${err.message}`, 'error');
  }
}

function updateMemoryProjectOptions(selected = null) {
  const select = $('memoryProject');
  select.innerHTML = '<option value="">Global (todos os casos)</option>';
  projectsCache.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p.id;
    opt.textContent = p.name;
    select.appendChild(opt);
  });
  select.value = selected || currentProjectId || '';
}

// ----------------- Settings -----------------
async function openSettingsModal(section = null) {
  openModal('settingsModal');
  if (section) showSettingsSection(section);
  fillPreferenceControls();
  await loadProfiles();
  loadProfileIntoEditor(profilesCache.find(p => p.id === (editorProfileId || currentPersonalityId)) || activeProfile());
  loadModels();
  loadBackups();
  checkHealth();
  loadLifeStatus();
}

// ----------------- Backup -----------------
async function loadBackups() {
  const list = $('backupList');
  try {
    const backups = await api('/api/backups');
    list.innerHTML = '';
    if (!backups.length) {
      list.innerHTML = '<p class="empty-hint">Nenhum backup ainda.</p>';
      return;
    }
    backups.forEach(b => {
      const row = document.createElement('div');
      row.className = 'backup-row';
      const size = (b.size_bytes / 1024).toFixed(0);
      row.innerHTML = `
        <span>${escape(b.created_at)} · ${size} KB</span>
        <span class="backup-row-actions">
          <a class="btn btn-sm btn-ghost" href="/api/backups/${encodeURIComponent(b.name)}" download>Baixar</a>
          <button class="btn btn-sm btn-secondary">Restaurar</button>
        </span>
      `;
      row.querySelector('button').addEventListener('click', () => restoreBackup(b.name));
      list.appendChild(row);
    });
  } catch (err) {
    list.innerHTML = `<p class="hint text-danger">Falha ao listar backups: ${escape(err.message)}</p>`;
  }
}

async function createBackupNow() {
  const status = $('backupStatus');
  status.textContent = 'Criando…';
  try {
    const data = await api('/api/backup', { method: 'POST', body: { label: 'manual' } });
    status.textContent = `Backup criado: ${data.name}`;
    await loadBackups();
  } catch (err) {
    status.textContent = `Falha: ${err.message}`;
  }
}

async function restoreBackup(name) {
  const typed = prompt(
    `Restaurar o backup "${name}"?\n\nIsso SUBSTITUI o banco atual. Um backup de segurança será criado antes.\nDigite RESTAURAR para confirmar:`
  );
  if (typed !== 'RESTAURAR') return;
  try {
    const result = await api('/api/backup/restore', { method: 'POST', body: { name, confirm: true } });
    toast(`Backup restaurado. Segurança criada antes: ${result.pre_restore_backup}`);
    closeModal('settingsModal');
    startNewChat();
    await Promise.all([loadConversations(), loadProjects(), loadDocuments(), loadMemories(), loadProfiles(), loadPreferences()]);
  } catch (err) {
    toast(`Falha ao restaurar: ${err.message}`, 'error');
  }
}

// ----------------- Utilities & Modals -----------------
function openModal(id) { $(id).hidden = false; }
function closeModal(id) {
  $(id).hidden = true;
  if (id === 'settingsModal') flushPrefs();
}
function setPrompt(text) {
  chatInput.value = text;
  autoGrow();
  updateSendState();
  chatInput.focus();
  chatInput.setSelectionRange(text.length, text.length);
}

async function exportCurrentChat() {
  if (!currentConversationId) { toast('Nenhuma conversa selecionada.', 'error'); return; }
  try {
    const data = await api(`/api/conversations/${currentConversationId}/export?format=md`);
    const blob = new Blob([data.content], { type: 'text/markdown' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `conversa-${currentConversationId}.md`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  } catch (err) {
    toast(`Falha ao exportar: ${err.message}`, 'error');
  }
}

async function deleteCurrentChat() {
  if (!currentConversationId) { toast('Nenhuma conversa selecionada.', 'error'); return; }
  if (!confirm('Excluir esta conversa permanentemente?')) return;
  if (isGenerating) abortGeneration(true);
  try {
    await api(`/api/conversations/${currentConversationId}`, { method: 'DELETE' });
    startNewChat();
    await loadConversations();
    toast('Conversa excluída');
  } catch (err) {
    toast(`Falha ao excluir: ${err.message}`, 'error');
  }
}

async function deleteConversationById(id, event) {
  if (event) event.stopPropagation();
  if (!confirm('Excluir esta conversa?')) return;
  try {
    await api(`/api/conversations/${id}`, { method: 'DELETE' });
    if (currentConversationId === id) startNewChat();
    await loadConversations();
    toast('Conversa excluída');
  } catch (err) {
    toast(`Falha ao excluir: ${err.message}`, 'error');
  }
}

// Expose for debugging from the webview devtools.
window.assistantApp = {
  startNewChat, sendMessage, abortGeneration, openLibraryModal,
  openProjectModal, openMemoryModal, checkPendingAuthorizations, openSettingsModal
};


// ----------------- Her state: sidebar strip + desktop mascot -----------------
// The miniature Victorique lives on the desktop (app/mascot, run by run.py).
// This page computes her operational state, shows it in the sidebar and
// forwards it, plus the model's [expression]/[gesture] picks, to the mascot.
// Priority: ouvindo > pensando > falando > erro > dormindo.
const STATE_LABELS = {
  acordada: 'Acordada', dormindo: 'Cochilando entre os livros', ouvindo: 'Ouvindo',
  pensando: 'Pensando', falando: 'Falando', erro: 'Algo deu errado',
};
const ERROR_HOLD_MS = 60000;
const visual = {
  state: null, generating: false, streaming: false, listening: false,
  speakingUntil: 0, errorAt: 0, lastActivity: Date.now(),
};
const mascot = { running: false, active: false };

function computeVisualState() {
  const now = Date.now();
  if (visual.listening) return 'ouvindo';
  if (visual.generating && !visual.streaming) return 'pensando';
  if (visual.streaming || visual.speakingUntil > now) return 'falando';
  if (visual.errorAt && now - visual.errorAt < ERROR_HOLD_MS) return 'erro';
  const idleMs = (prefs.idle_minutes || 5) * 60000;
  if (now - visual.lastActivity > idleMs) return 'dormindo';
  return 'acordada';
}

function refreshVisualState() {
  const state = computeVisualState();
  if (state === visual.state) return;
  visual.state = state;
  $('vicStatus').dataset.state = state;
  $('vicState').textContent = STATE_LABELS[state];
  sendMascotSignal({ state });
}

function sendMascotSignal(body) {
  if (!mascot.running) return;
  api('/api/mascot/signal', { method: 'POST', body }).catch(() => {});
}

// A finished reply while the chat is not in front: she shows its start.
function tellMascotReply(text) {
  if (!mascot.active || prefs.mascot_replies === false) return;
  if (document.visibilityState === 'visible' && document.hasFocus()) return;
  api('/api/mascot/reply', { method: 'POST', body: { text } }).catch(() => {});
}

function noteActivity() {
  visual.lastActivity = Date.now();
  if (visual.errorAt && !isGenerating) visual.errorAt = 0;
  if (visual.state === 'dormindo' || visual.state === 'erro') refreshVisualState();
}

function markVisualError() {
  visual.errorAt = Date.now();
  refreshVisualState();
}

// The server speaks in the background; estimate how long (about 14 chars/s).
function markSpeaking(text) {
  const seconds = Math.min(90, Math.max(2, String(text).length / 14));
  visual.speakingUntil = Date.now() + seconds * 1000;
  refreshVisualState();
  setTimeout(refreshVisualState, seconds * 1000 + 50);
}

async function loadMascotStatus() {
  try {
    applyMascotStatus(await api('/api/mascot/status'));
  } catch (err) {
    applyMascotStatus({ running: false, active: false });
  }
}

function applyMascotStatus(status) {
  const wasRunning = mascot.running;
  mascot.running = !!status.running;
  mascot.active = !!status.active;
  $('btnMascotCall').hidden = !(mascot.running && !mascot.active);
  if (mascot.running && !wasRunning && visual.state) sendMascotSignal({ state: visual.state });
  const card = $('mascotStatus');
  if (!card) return;
  if (!mascot.running) {
    card.textContent = 'Ela só aparece na área de trabalho quando o assistente é aberto como aplicativo (run.bat), no Windows. No navegador, os balões dela aparecem aqui na página.';
  } else if (mascot.active) {
    card.textContent = status.visible
      ? `Ela está na área de trabalho agora (${STATE_LABELS[status.state] || 'acordada'}).`
      : 'Ativa, mas escondida enquanto há algo em tela cheia.';
  } else {
    card.textContent = 'Escondida. Ligue a primeira opção abaixo (ou o ✦ na barra lateral) para trazê-la de volta.';
  }
}

function initVisualState() {
  ['pointerdown', 'keydown', 'wheel'].forEach(evt =>
    document.addEventListener(evt, noteActivity, { passive: true }));
  setInterval(refreshVisualState, 15000);
  visual.state = null;
  refreshVisualState();
  loadMascotStatus();
  $('btnMascotCall').addEventListener('click', () => {
    savePref('mascot_enabled', true, { immediate: true });
    fillPreferenceControls();
  });
  $('btnMascotHome').addEventListener('click', async () => {
    try {
      const r = await api('/api/mascot/command', { method: 'POST', body: { action: 'home' } });
      toast(r.delivered ? 'Ela volta para perto do relógio.' : 'Ela não está na área de trabalho agora.');
    } catch (err) {
      toast(`Erro: ${err.message}`, 'error');
    }
  });
  // Called by the desktop mascot (run.py) when "Aceitar o Caso" is clicked there.
  window.victoriqueDesktop = {
    acceptCase: event => acceptLifeCase(event),
    // "Abrir na janela grande" in the small chat by her side.
    openConversation: id => switchConversation(String(id)),
    // «Assistir» in her balloon, or «Ir para a Biblioteca» in her menu.
    openLibrary: () => showSidebarTab('hall'),
  };
}

// ----------------- Vida própria -----------------
// The server decides whether and what she says (app/life); the UI only reports
// its own state, shows the balloon and carries out the user's answer.
const LIFE_TICK_MS = 20000;
const LIFE_FAST_TICK_MS = 4000;
const LIFE_SILENCE_MINUTES = 120;
const LIFE_TAGS = {
  tedio: 'entediada', tarde: 'hora tardia', bagunca: 'sobre uma pasta',
  organizado: 'organização concluída', retorno: 'de volta',
};
const life = { timer: null, busy: false, lastTyping: 0, event: null, hideTimer: null, status: null };

function lifeUiState() {
  const draft = document.hasFocus() && document.activeElement === chatInput && chatInput.value.trim().length > 0;
  return {
    app_idle_seconds: Math.max(0, (Date.now() - visual.lastActivity) / 1000),
    typing: draft || Date.now() - life.lastTyping < 15000,
    generating: isGenerating,
    visible: document.visibilityState === 'visible',
    settings_open: !$('settingsModal').hidden,
    backend: currentBackend || null,
    personality_id: currentPersonalityId || null,
  };
}

function scheduleLifeTick(ms) {
  clearTimeout(life.timer);
  life.timer = setTimeout(lifeTick, ms);
}

async function lifeTick() {
  if (life.busy) return;
  life.busy = true;
  let next = LIFE_TICK_MS;
  try {
    const data = await api('/api/life/tick', { method: 'POST', body: lifeUiState() });
    if (typeof data.mascot === 'boolean' && data.mascot !== mascot.active) loadMascotStatus();
    renderLifeStatus(data.status);
    if (data.event) showLifeBubble(data.event);
    if (data.status && data.status.reason === 'preparando') next = LIFE_FAST_TICK_MS;
  } catch (err) {
    // Server restarting or offline: just try again later.
  } finally {
    life.busy = false;
    scheduleLifeTick(next);
  }
}

function lifeTime(epochSeconds) {
  return new Date(epochSeconds * 1000).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

function renderLifeStatus(status) {
  if (!status) return;
  life.status = status;
  const note = $('lifeQuietNote');
  if (status.silenced_until) {
    note.textContent = `· em silêncio até ${lifeTime(status.silenced_until)}`;
    note.hidden = false;
  } else {
    note.hidden = true;
  }
  const card = $('lifeStatus');
  if (!card) return;
  card.innerHTML = '';
  const line = document.createElement('div');
  line.append('Agora: ', Object.assign(document.createElement('strong'), { textContent: status.label }));
  const counts = document.createElement('div');
  counts.textContent = `Falas na última hora: ${status.spoken_last_hour} de ${status.max_per_hour}.`;
  card.append(line, counts);
  if (typeof status.boredom_in === 'number' && status.boredom_in > 0) {
    const boredom = document.createElement('div');
    boredom.textContent = `O tédio chega em cerca de ${Math.ceil(status.boredom_in / 60)} min sem você falar com ela.`;
    card.append(boredom);
  }
  if (status.silenced_until) {
    const row = document.createElement('div');
    row.className = 'inline-actions';
    row.style.marginTop = '8px';
    const resume = Object.assign(document.createElement('button'), {
      className: 'btn btn-secondary btn-sm', type: 'button', textContent: 'Encerrar o silêncio',
    });
    resume.addEventListener('click', resumeLife);
    row.append(`Silêncio até ${lifeTime(status.silenced_until)}.`, resume);
    card.append(row);
  }
  const hint = $('lifeLinesHint');
  if (hint && status.lines_file) {
    hint.innerHTML = '';
    const path = document.createElement('code');
    path.textContent = status.lines_file;
    hint.append('Banco de falas, editável num editor de texto: ', path, '. As mudanças valem na próxima fala.');
  }
}

async function loadLifeStatus() {
  try {
    renderLifeStatus(await api('/api/life/status'));
  } catch (err) {
    $('lifeStatus').textContent = 'Não consegui consultar o estado.';
  }
}

function updateLifeControls() {
  const dnd = !!prefs.life_dnd;
  const button = $('btnLifeDnd');
  button.setAttribute('aria-pressed', String(dnd));
  button.title = dnd ? 'Não perturbar ligado: clique para ela voltar a puxar assunto'
                     : 'Não perturbar: ela não puxa assunto';
  const box = document.querySelector('[data-pref="life_dnd"]');
  if (box) box.checked = dnd;
}

function lifeTextHtml(text) {
  // Plain text; only *ação* becomes italic.
  return escape(text).replace(/\*([^*\n]{1,160})\*/g, '<em>$1</em>');
}

function speakLife(event) {
  markSpeaking(event.text);
  if (prefs.life_voice && ttsAvailable) {
    const spoken = event.text.replace(/\*[^*]*\*/g, ' ').replace(/\s+/g, ' ').trim();
    if (spoken) api('/api/tts/speak', { method: 'POST', body: { text: spoken, async_: true } }).catch(() => {});
  }
}

// With Victorique on the desktop the line goes to her balloon; otherwise
// (browser, mascot hidden) it shows here in the page.
async function showLifeBubble(event) {
  life.event = event;
  if (mascot.active) {
    try {
      const body = { category: event.category, text: event.text, case: event.case || null, test: !!event.test };
      const r = await api('/api/mascot/say', { method: 'POST', body });
      if (r.shown) { speakLife(event); return; }
    } catch (err) {
      // Fall through to the page balloon.
    }
  }
  showPageLifeBubble(event);
}

function showPageLifeBubble(event) {
  const bubble = $('lifeBubble');
  bubble.dataset.category = event.category;
  paintAvatar($('lifeBubbleMark'), activeProfile());
  $('lifeBubbleName').textContent = activeProfileName();
  $('lifeBubbleTag').textContent = (event.test ? 'teste · ' : '') + (LIFE_TAGS[event.category] || '');
  $('lifeBubbleText').innerHTML = lifeTextHtml(event.text);
  const hasCase = event.category === 'tedio' && !!event.case;
  $('lifeBubbleCase').hidden = !hasCase;
  $('lifeBubbleCaseTitle').textContent = hasCase ? event.case.titulo : '';
  $('btnLifeAccept').hidden = !hasCase;
  $('btnLifeLater').hidden = !hasCase;
  bubble.hidden = false;
  speakLife(event);
  clearTimeout(life.hideTimer);
  const stay = hasCase ? 5 * 60000 : Math.min(90000, 30000 + event.text.length * 120);
  life.hideTimer = setTimeout(hideLifeBubble, stay);
}

function hideLifeBubble() {
  clearTimeout(life.hideTimer);
  $('lifeBubble').hidden = true;
  life.event = null;
}

async function silenceLife() {
  hideLifeBubble();
  try {
    const data = await api('/api/life/silence', { method: 'POST', body: { minutes: LIFE_SILENCE_MINUTES } });
    toast(`Silêncio até ${lifeTime(data.silenced_until)}.`);
  } catch (err) {
    toast(`Não consegui silenciar: ${err.message}`, 'error');
  }
  scheduleLifeTick(0);
}

async function resumeLife() {
  try {
    renderLifeStatus(await api('/api/life/resume', { method: 'POST' }));
    toast('Ela pode voltar a falar.');
  } catch (err) {
    toast(`Erro: ${err.message}`, 'error');
  }
}

async function acceptLifeCase(fromDesktop) {
  const event = (fromDesktop && fromDesktop.case) ? fromDesktop : life.event;
  if (!event || !event.case) return;
  hideLifeBubble();
  try {
    const project = await api('/api/projects', {
      method: 'POST',
      body: {
        name: event.case.titulo,
        description: 'Mistério proposto pela Victorique num momento de tédio.',
        instructions: `Pergunta do Caso: ${event.case.pergunta}\n\nComo ela propôs: ${event.text}`,
      },
    });
    await loadProjects();
    if (currentProjectId === project.id) currentProjectId = null;
    await selectProject(project);
    chatInput.value = `Aceito o desafio: ${event.case.pergunta}`;
    autoGrow();
    updateSendState();
    chatInput.focus();
    toast(`Caso aberto: ${project.name}`);
  } catch (err) {
    toast(`Não consegui abrir o Caso: ${err.message}`, 'error');
  }
}

async function testLife() {
  const button = $('btnLifeTest');
  button.disabled = true;
  button.textContent = 'Pensando…';
  try {
    const event = await api('/api/life/test', {
      method: 'POST', body: { ...lifeUiState(), category: $('lifeTestCategory').value },
    });
    closeModal('settingsModal');
    showLifeBubble(event);
  } catch (err) {
    toast(`O teste falhou: ${err.message}`, 'error');
  } finally {
    button.disabled = false;
    button.textContent = 'Testar';
  }
}

function initLife() {
  chatInput.addEventListener('input', () => { life.lastTyping = Date.now(); });
  $('btnLifeClose').addEventListener('click', hideLifeBubble);
  $('btnLifeLater').addEventListener('click', hideLifeBubble);
  $('btnLifeSilence').addEventListener('click', silenceLife);
  $('btnLifeAccept').addEventListener('click', acceptLifeCase);
  $('btnLifeTest').addEventListener('click', testLife);
  $('btnLifeDnd').addEventListener('click', () => {
    const on = !prefs.life_dnd;
    savePref('life_dnd', on, { immediate: true });
    if (on) hideLifeBubble();
    scheduleLifeTick(500);
  });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') scheduleLifeTick(1000);
  });
  updateLifeControls();
  scheduleLifeTick(3000);
}
