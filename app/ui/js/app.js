// Application State
let currentConversationId = null;
let currentProjectId = null;
let currentPersonalityId = null;
let selectedModel = null;
let activeAbortController = null;
let isGenerating = false;
let projectsCache = [];
let authPollTimer = null;
let voiceEnabled = false;
let sttAvailable = false;
let ttsAvailable = false;

const $ = (id) => document.getElementById(id);
const escape = (t) => (window.escapeHtml ? window.escapeHtml(t) : String(t || ''));
const md = (t) => (window.renderMarkdown ? window.renderMarkdown(t) : escape(t));

// DOM Elements
const chatInput = $('chatInput');
const chatForm = $('chatForm');
const btnSend = $('btnSend');
const btnStop = $('btnStop');
const btnVoiceListen = $('btnVoiceListen');
const btnVoiceSpeak = $('btnVoiceSpeak');
const voiceStatus = $('voiceStatus');
const messagesList = $('messagesList');
const welcomeScreen = $('welcomeScreen');
const conversationsList = $('conversationsList');
const currentChatTitle = $('currentChatTitle');
const authBar = $('authBar');
const authTitle = $('authTitle');
const authDesc = $('authDesc');
const authPayload = $('authPayload');
const btnApproveAction = $('btnApproveAction');
const btnRejectAction = $('btnRejectAction');
const fileInput = $('fileInput');

// ----------------- Initialization -----------------
document.addEventListener('DOMContentLoaded', async () => {
  setupEventListeners();
  setupSliders();
  await checkHealth();
  await loadModels();
  await loadBackendMode();
  await loadProjects();
  await loadConversations();
  await loadDocuments();
  await loadMemories();
  await loadPersonalitySettings();
  startNewChat();
  checkPendingAuthorizations();
  await initVoice();
  authPollTimer = setInterval(checkPendingAuthorizations, 5000);
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
    });
  });

  $('modeSelect').addEventListener('change', (e) => changeBackend(e.target.value));

  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    sendMessage();
  });

  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  chatInput.addEventListener('input', () => {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 180) + 'px';
  });

  $('btnNewChat').addEventListener('click', startNewChat);
  $('btnStop').addEventListener('click', () => abortGeneration());

  $('btnOpenSettings').addEventListener('click', openSettingsModal);
  $('btnSavePersonality').addEventListener('click', savePersonalitySettings);
  $('btnCreateBackup').addEventListener('click', createBackupNow);

  $('btnCreateProject').addEventListener('click', () => openProjectModal());
  $('btnCreateMemory').addEventListener('click', () => openMemoryModal());
  $('btnSaveProject').addEventListener('click', saveProject);
  $('btnSaveMemory').addEventListener('click', saveMemory);

  $('btnAttachDoc').addEventListener('click', () => fileInput.click());
  $('btnUploadDoc').addEventListener('click', () => fileInput.click());
  $('btnModalUploadDoc').addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', handleFileUpload);

  $('searchConversations').addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase();
    document.querySelectorAll('.conversations-list .list-item').forEach(item => {
      const title = (item.dataset.title || '').toLowerCase();
      item.style.display = title.includes(q) ? 'flex' : 'none';
    });
  });

  $('btnExportChat').addEventListener('click', exportCurrentChat);
  $('btnDeleteChat').addEventListener('click', deleteCurrentChat);

  $('settingModel').addEventListener('change', (e) => changeModel(e.target.value));

  document.querySelectorAll('[data-close]').forEach(btn => {
    btn.addEventListener('click', () => closeModal(btn.dataset.close));
  });
  document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) closeModal(backdrop.id);
    });
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal-backdrop').forEach(m => {
        if (m.style.display !== 'none') closeModal(m.id);
      });
    }
  });

  // Controles de voz
  if (btnVoiceListen) {
    btnVoiceListen.addEventListener('click', toggleVoiceListen);
  }
  if (btnVoiceSpeak) {
    btnVoiceSpeak.addEventListener('click', toggleVoiceSpeak);
  }

  document.querySelectorAll('.quick-card').forEach(card => {
    card.addEventListener('click', () => {
      const kind = card.dataset.quick;
      if (kind === 'library') { openLibraryModal(); return; }
      if (kind === 'calc') {
        setPrompt('Faça um cálculo matemático: qual é a raiz quadrada de 144 multiplicada por 15?');
      } else {
        setPrompt('Resuma as ferramentas locais disponíveis e o que cada uma pode fazer, incluindo quais exigem autorização.');
      }
    });
  });
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

// ----------------- HTTP helpers -----------------
async function api(path, options = {}) {
  const opts = { method: options.method || 'GET', headers: { ...(options.headers || {}) } };
  if (options.body instanceof FormData) {
    opts.body = options.body;
  } else if (options.body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(options.body);
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

// ----------------- Health & Models -----------------
async function checkHealth() {
  try {
    const data = await api('/api/health');
    const pill = $('statusPill');
    if (data.ollama_online) {
      const suffix = data.default_model_installed === false ? ' — modelo ausente!' : '';
      pill.textContent = `● Ollama Conectado (${data.default_model})${suffix}`;
      pill.className = data.default_model_installed === false ? 'status-indicator text-danger' : 'status-indicator online';
    } else {
      pill.textContent = '○ Ollama Desconectado';
      pill.className = 'status-indicator text-danger';
    }

    const runtime = $('runtimeInfo');
    if (runtime) {
      const ocr = data.ocr || {};
      const ocrText = ocr.available
        ? `OCR ativo (${(ocr.languages || []).join(', ') || 'eng'})`
        : 'OCR indisponível';
      runtime.textContent =
        `Ferramentas: ${data.tools_count || 0}` +
        `${data.tool_calling_enabled ? ' · tool calling ativo' : ' · tool calling desativado'}` +
        ` · ${ocrText}`;
    }
  } catch (err) {
    console.error('Healthcheck failed', err);
    $('statusPill').textContent = '○ Backend indisponível';
    $('statusPill').className = 'status-indicator text-danger';
  }
}

async function initVoice() {
  try {
    const [tts, stt] = await Promise.all([
      api('/api/tts/status'),
      api('/api/stt/status'),
    ]);
    ttsAvailable = tts.available === true;
    sttAvailable = stt.available === true;
    voiceEnabled = ttsAvailable || sttAvailable;

    const ttsBtn = $('btnVoiceSpeak');
    const sttBtn = $('btnVoiceListen');
    const vs = $('voiceStatus');

    if (ttsBtn) {
      ttsBtn.disabled = !ttsAvailable;
      ttsBtn.title = ttsAvailable ? 'Falar última resposta' : 'TTS indisponível';
    }
    if (sttBtn) {
      sttBtn.disabled = !sttAvailable || !stt.microphone_available;
      sttBtn.title = sttAvailable && stt.microphone_available
        ? 'Ouvir microfone'
        : 'STT/microfone indisponível';
    }
    if (vs) {
      vs.textContent = `Voz: TTS ${ttsAvailable ? '●' : '○'} | STT ${sttAvailable ? '●' : '○'}`;
      vs.className = voiceEnabled ? 'voice-status on' : 'voice-status off';
    }
  } catch (err) {
    console.error('Voice init failed', err);
  }
}

function updateVoiceStatus(text, kind = 'info') {
  const vs = $('voiceStatus');
  if (vs) {
    vs.textContent = text;
    vs.className = `voice-status ${kind}`;
  }
}

async function toggleVoiceListen() {
  if (!sttAvailable) {
    updateVoiceStatus('STT não disponível.', 'error');
    return;
  }
  try {
    updateVoiceStatus('Ouvindo... fale agora.', 'listening');
    const data = await api('/api/stt/listen', {
      method: 'POST',
      body: JSON.stringify({ timeout: 5, phrase_time_limit: 15 }),
    });
    if (data.status === 'ok' && data.text) {
      updateVoiceStatus('Reconhecido: ' + data.text.slice(0, 60) + '…', 'ok');
      chatInput.value = data.text;
      chatInput.style.height = 'auto';
      chatInput.style.height = Math.min(chatInput.scrollHeight, 180) + 'px';
      chatInput.focus();
    } else {
      updateVoiceStatus('Nenhuma fala detectada.', 'warn');
    }
  } catch (err) {
    console.error('STT error', err);
    updateVoiceStatus('Erro no STT.', 'error');
  } finally {
    if (voiceEnabled) updateVoiceStatus('Voz: ativa', 'info');
  }
}

async function toggleVoiceSpeak() {
  if (!ttsAvailable) {
    updateVoiceStatus('TTS não disponível.', 'error');
    return;
  }
  // Fala a última mensagem do assistente na conversa atual.
  const lastBubble = messagesList.querySelector('.message-bubble.bot:last-child');
  if (!lastBubble) {
    updateVoiceStatus('Nenhuma resposta para falar.', 'warn');
    return;
  }
  const text = lastBubble.textContent || '';
  try {
    updateVoiceStatus('Falando…', 'speaking');
    const data = await api('/api/tts/speak', {
      method: 'POST',
      body: JSON.stringify({ text, async_: true }),
    });
    if (data.status === 'speaking_async') {
      updateVoiceStatus('Falando resposta.', 'ok');
    } else {
      updateVoiceStatus('TTS indisponível.', 'error');
    }
  } catch (err) {
    console.error('TTS error', err);
    updateVoiceStatus('Erro no TTS.', 'error');
  } finally {
    if (voiceEnabled) updateVoiceStatus('Voz: ativa', 'info');
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
    await checkHealth();
  } catch (err) {
    alert(`Não foi possível salvar o modelo: ${err.message}`);
  }
}

// ----------------- Mode (local / Claude Code) -----------------
let currentBackend = null;

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
    await checkHealth();
  } catch (err) {
    alert(`Não foi possível trocar o modo: ${err.message}`);
    updateModeUi();
  }
}

function updateModeUi() {
  const isClaude = currentBackend === 'claude-code';
  // llama-cpp-server is the same local engine as llama-cpp in the selector.
  $('modeSelect').value = currentBackend === 'llama-cpp-server' ? 'llama-cpp' : (currentBackend || 'llama-cpp');
  $('claudeBadge').hidden = !isClaude;
  $('activeModelTag').hidden = isClaude;
}

function updateModelTag() {
  const tag = $('activeModelTag');
  if (!selectedModel) { tag.textContent = '—'; return; }
  tag.textContent = selectedModel;
  $('modelHint').textContent = selectedModel.includes('coder')
    ? 'Modelo de código. Na GTX 1660 Super (6 GB) parte das camadas roda em CPU; respostas longas podem demorar.'
    : 'Modelos locais via Ollama. Nenhum dado sai do computador.';
}

// ----------------- Conversations -----------------
async function loadConversations() {
  try {
    const all = await api('/api/conversations');
    // Projects are isolated: the sidebar shows only the selected scope.
    const list = all.filter(c => (c.project_id || null) === (currentProjectId || null));
    conversationsList.innerHTML = '';
    list.forEach(c => {
      const item = document.createElement('div');
      item.className = `list-item ${c.id === currentConversationId ? 'active' : ''}`;
      item.dataset.id = c.id;
      item.dataset.title = c.title || '';
      item.innerHTML = `
        <span class="list-item-title">${escape(c.title || 'Sem título')}</span>
        <button class="btn-ghost btn-xs text-danger" title="Excluir conversa">✕</button>
      `;
      item.addEventListener('click', () => switchConversation(c.id));
      item.querySelector('button').addEventListener('click', (e) => deleteConversationById(c.id, e));
      conversationsList.appendChild(item);
    });
  } catch (err) {
    console.error('Failed to load conversations', err);
  }
}

function startNewChat() {
  if (isGenerating) abortGeneration(true);
  currentConversationId = null;
  currentChatTitle.textContent = 'Nova Conversa';
  messagesList.innerHTML = '';
  welcomeScreen.style.display = 'block';
  document.querySelectorAll('.conversations-list .list-item').forEach(i => i.classList.remove('active'));
  chatInput.focus();
}

async function switchConversation(convId) {
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
    currentPersonalityId = conv.personality_id || currentPersonalityId;
    updateProjectTag();
    messagesList.innerHTML = '';
    welcomeScreen.style.display = 'none';

    data.messages.forEach(m => {
      renderMessage(m.role, m.content, m.sources);
    });
    await loadConversations();
    await loadDocuments();
    await loadMemories();
  } catch (err) {
    console.error('Failed to switch conversation', err);
    alert(`Falha ao abrir conversa: ${err.message}`);
  }
}

// ----------------- Messaging & Streaming -----------------
async function sendMessage() {
  const text = chatInput.value.trim();
  if (!text || isGenerating) return;

  if (!currentConversationId) {
    try {
      const conv = await api('/api/conversations', {
        method: 'POST',
        body: {
          title: text.slice(0, 60),
          project_id: currentProjectId,
          personality_id: currentPersonalityId,
        }
      });
      currentConversationId = conv.id;
      currentChatTitle.textContent = conv.title;
    } catch (err) {
      alert(`Não foi possível criar a conversa: ${err.message}`);
      return;
    }
  }

  chatInput.value = '';
  chatInput.style.height = 'auto';
  welcomeScreen.style.display = 'none';

  renderMessage('user', text);
  const assistantMsgEl = renderMessage('assistant', '');
  const bubble = assistantMsgEl.querySelector('.message-bubble');
  const toolBox = document.createElement('div');
  toolBox.className = 'tool-events';
  assistantMsgEl.appendChild(toolBox);
  const citationsContainer = document.createElement('div');
  citationsContainer.className = 'citations-box';
  assistantMsgEl.appendChild(citationsContainer);

  isGenerating = true;
  btnSend.style.display = 'none';
  btnStop.style.display = 'inline-flex';
  activeAbortController = new AbortController();
  let accumulated = '';
  let reasoningBody = null;
  let aborted = false;

  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: activeAbortController.signal,
      body: JSON.stringify({
        conversation_id: currentConversationId,
        message: text,
        model: selectedModel || undefined,
        backend: currentBackend || undefined,
        project_id: currentProjectId,
        personality_id: currentPersonalityId,
        enable_rag: true,
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
          const args = JSON.stringify(data.arguments || {});
          appendToolEvent(
            toolBox,
            `🔧 Executando ${data.tool} ${args.length > 160 ? args.slice(0, 160) + '…' : args}`,
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
          appendToolEvent(
            toolBox,
            `${ok ? '✅' : '⚠️'} ${data.tool} (${data.status})${detail ? ' — ' + detail : ''}`,
            ok ? 'tool-event-ok' : 'tool-event-error'
          );
        } else if (data.type === 'authorization_required') {
          appendToolEvent(
            toolBox,
            `🔐 Autorização necessária: ${data.tool_name || data.tool || 'ação'} — ${data.resource || ''}`,
            'tool-event-auth'
          );
          checkPendingAuthorizations();
        } else if (data.type === 'reasoning') {
          // Model's internal reasoning: shown collapsed, never part of the answer.
          if (!reasoningBody) {
            const details = document.createElement('details');
            details.className = 'reasoning-box';
            const summary = document.createElement('summary');
            summary.textContent = 'Raciocínio';
            reasoningBody = document.createElement('div');
            reasoningBody.className = 'reasoning-body';
            details.appendChild(summary);
            details.appendChild(reasoningBody);
            assistantMsgEl.insertBefore(details, bubble);
          }
          reasoningBody.textContent += data.content || '';
          scrollToBottom();
        } else if (data.type === 'notice') {
          appendToolEvent(toolBox, `ℹ️ ${data.message}`, 'tool-event-notice');
        } else if (data.type === 'token') {
          accumulated += data.content || '';
          bubble.innerHTML = md(accumulated);
          scrollToBottom();
        } else if (data.type === 'error') {
          const errBox = document.createElement('div');
          errBox.className = 'stream-error';
          errBox.textContent = `Erro do modelo: ${data.message}`;
          assistantMsgEl.appendChild(errBox);
        } else if (data.type === 'done') {
          if (data.conversation_id) currentConversationId = data.conversation_id;
          accumulated = data.content || accumulated;
          bubble.innerHTML = md(accumulated);
        }
      }
    }
  } catch (err) {
    if (err.name === 'AbortError') {
      aborted = true;
      const note = document.createElement('div');
      note.className = 'cancelled-note';
      note.textContent = 'Geração cancelada.';
      assistantMsgEl.appendChild(note);
    } else {
      bubble.innerHTML = `<p class="text-danger">[Erro de comunicação: ${escape(err.message)}]</p>`;
    }
  } finally {
    isGenerating = false;
    activeAbortController = null;
    btnSend.style.display = 'inline-flex';
    btnStop.style.display = 'none';
    btnStop.textContent = 'Parar';
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
    if (!silent) btnStop.textContent = 'Cancelando...';
  }
}

function renderMessage(role, content, sources = null) {
  const msg = document.createElement('div');
  msg.className = `message ${role}`;
  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.innerHTML = role === 'user' ? escape(content) : md(content || '');
  msg.appendChild(bubble);

  if (sources && sources.length > 0) {
    const box = document.createElement('div');
    box.className = 'citations-box';
    renderCitations(box, sources);
    msg.appendChild(box);
  }

  messagesList.appendChild(msg);
  scrollToBottom();
  return msg;
}

function appendToolEvent(container, text, className) {
  if (!container) return;
  const line = document.createElement('div');
  line.className = `tool-event ${className || ''}`.trim();
  line.textContent = text;
  container.appendChild(line);
  scrollToBottom();
}

function renderCitations(container, sources) {
  container.innerHTML = '';
  (sources || []).forEach(s => {
    const pill = document.createElement('span');
    pill.className = 'citation-pill';
    const page = s.page ? `pág. ${s.page}` : 'página não informada';
    pill.textContent = `📖 ${s.document || 'Documento'} (${page})`;
    if (s.score != null) pill.title = `Relevância: ${s.score}`;
    container.appendChild(pill);
  });
}

function scrollToBottom() {
  const container = $('messagesContainer');
  container.scrollTop = container.scrollHeight;
}

// ----------------- Security Authorizations -----------------
async function checkPendingAuthorizations() {
  if (isGenerating) return;
  try {
    const pending = await api('/api/security/pending');
    if (pending.length > 0) {
      const act = pending[0];
      authTitle.textContent = `Solicitação: ${String(act.action_type || '').toUpperCase()}`;
      authDesc.textContent = `${act.description || 'Ação protegida'} | Alvo: ${act.resource || '—'} | Expira: ${act.expires_at_iso || '—'}`;
      authPayload.textContent = JSON.stringify(act.payload || {}, null, 2).slice(0, 3000);
      authBar.style.display = 'flex';

      btnApproveAction.onclick = () => resolveAuth(act.id, true);
      btnRejectAction.onclick = () => resolveAuth(act.id, false);
    } else {
      authBar.style.display = 'none';
    }
  } catch (err) {
    console.error('Pending auth check failed', err);
  }
}

async function resolveAuth(actionId, approved) {
  try {
    const data = await api('/api/security/authorize', {
      method: 'POST',
      body: { action_id: actionId, approved }
    });
    authBar.style.display = 'none';
    if (data.status === 'executed') {
      renderToolResult(data.result);
    } else {
      renderMessage('assistant', `Ação **${approved ? 'não executada' : 'recusada'}**: ${data.status}`);
    }
  } catch (err) {
    authBar.style.display = 'none';
    renderMessage('assistant', `Falha ao resolver autorização: ${err.message}`);
  }
  checkPendingAuthorizations();
}

function renderToolResult(result) {
  const msg = renderMessage('assistant', '**Resultado da ferramenta:**');
  const pre = document.createElement('pre');
  pre.className = 'tool-result';
  pre.textContent = JSON.stringify(result, null, 2);
  msg.appendChild(pre);
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
    empty.className = 'hint';
    empty.textContent = 'Nenhum documento indexado.';
    container.appendChild(empty);
    return;
  }
  docs.forEach(d => {
    const item = document.createElement('div');
    item.className = 'list-item';
    item.innerHTML = `
      <span class="list-item-title">📄 ${escape(d.title)} (${d.total_pages} pág., ${d.total_chunks} trechos)</span>
      <button class="btn-ghost btn-xs text-danger" title="Remover documento">✕</button>
    `;
    item.querySelector('button').addEventListener('click', (e) => deleteDocument(d.id, e));
    container.appendChild(item);
  });
}

async function handleFileUpload(e) {
  const file = e.target.files[0];
  e.target.value = '';
  if (!file) return;

  const ext = (file.name.match(/\.[^.]+$/) || [''])[0].toLowerCase();
  if (!['.pdf', '.txt', '.md'].includes(ext)) {
    alert('Formato não suportado. Use PDF, TXT ou MD.');
    return;
  }
  if (file.size > 25 * 1024 * 1024) {
    alert('Arquivo maior que 25 MB.');
    return;
  }

  const formData = new FormData();
  formData.append('file', file);
  formData.append('collection', 'Geral');
  if (currentProjectId) formData.append('project_id', currentProjectId);

  renderMessage('assistant', `⏳ Indexando documento local **${file.name}**...`);

  try {
    const data = await api('/api/documents/upload', { method: 'POST', body: formData });
    renderMessage('assistant', `✅ Documento **${data.title}** indexado (${data.total_pages} páginas, ${data.total_chunks} trechos).`);
    await loadDocuments();
  } catch (err) {
    renderMessage('assistant', `❌ Falha ao indexar: ${err.message}`);
  }
}

async function deleteDocument(docId, event) {
  if (event) event.stopPropagation();
  if (!confirm('Excluir este documento da biblioteca? A cópia indexada e o arquivo armazenado serão removidos.')) return;
  try {
    await api(`/api/documents/${docId}`, { method: 'DELETE' });
    await loadDocuments();
  } catch (err) {
    alert(`Falha ao excluir: ${err.message}`);
  }
}

function openLibraryModal() {
  loadDocuments();
  openModal('libraryModal');
}

// ----------------- Memories -----------------
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
      empty.className = 'hint';
      empty.textContent = 'Nenhuma memória. Nada é salvo automaticamente.';
      list.appendChild(empty);
      return;
    }
    const projectName = (id) => {
      const p = projectsCache.find(x => x.id === id);
      return p ? p.name : 'projeto';
    };

    memories.forEach(m => {
      const item = document.createElement('div');
      item.className = `list-item memory-item ${m.is_active ? '' : 'inactive'}`;
      const scope = m.project_id ? `📁 ${escape(projectName(m.project_id))}` : '🌐 Global';
      item.innerHTML = `
        <div class="memory-body">
          <span class="list-item-title">📌 [${escape(m.category)}] ${escape(m.content)}</span>
          <small class="hint">${scope} · ${m.is_active ? 'ativa' : 'inativa'}</small>
        </div>
        <div class="item-actions">
          <button class="btn-ghost btn-xs" title="${m.is_active ? 'Desativar' : 'Ativar'}">${m.is_active ? '⏸' : '▶'}</button>
          <button class="btn-ghost btn-xs" title="Editar">✎</button>
          <button class="btn-ghost btn-xs text-danger" title="Excluir">✕</button>
        </div>
      `;
      const [toggleBtn, editBtn, delBtn] = item.querySelectorAll('button');
      toggleBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        try {
          await api(`/api/memories/${m.id}`, {
            method: 'PUT',
            body: { content: m.content, category: m.category, is_active: !m.is_active }
          });
          await loadMemories();
        } catch (err) { alert(`Falha: ${err.message}`); }
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
  } catch (err) {
    alert(`Falha ao excluir: ${err.message}`);
  }
}

function openMemoryModal(mem = null) {
  $('memoryId').value = mem ? mem.id : '';
  $('memoryModalTitle').textContent = mem ? 'Editar Memória' : 'Nova Memória';
  $('memoryCategory').value = mem ? mem.category : 'preference';
  $('memoryContent').value = mem ? mem.content : '';
  updateMemoryProjectOptions(mem ? mem.project_id : currentProjectId);
  openModal('memoryModal');
}

async function saveMemory() {
  const id = $('memoryId').value;
  const payload = {
    category: $('memoryCategory').value,
    content: $('memoryContent').value,
    project_id: $('memoryProject').value || null,
  };
  if (!payload.content.trim()) { alert('Escreva o conteúdo da memória.'); return; }

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
  } catch (err) {
    alert(`Falha ao salvar memória: ${err.message}`);
  }
}

// ----------------- Projects -----------------
async function loadProjects() {
  try {
    projectsCache = await api('/api/projects');
    const list = $('projectsList');
    list.innerHTML = '';
    if (!projectsCache.length) {
      const empty = document.createElement('p');
      empty.className = 'hint';
      empty.textContent = 'Nenhum projeto. Crie um para isolar conversas, memórias e documentos.';
      list.appendChild(empty);
    }
    projectsCache.forEach(p => {
      const item = document.createElement('div');
      item.className = `list-item ${p.id === currentProjectId ? 'active' : ''}`;
      item.dataset.projectId = p.id;
      item.innerHTML = `
        <span class="list-item-title">📁 ${escape(p.name)}</span>
        <div class="item-actions">
          <button class="btn-ghost btn-xs" title="Editar projeto">✎</button>
          <button class="btn-ghost btn-xs text-danger" title="Excluir projeto">✕</button>
        </div>
      `;
      item.addEventListener('click', () => selectProject(p));
      const [editBtn, delBtn] = item.querySelectorAll('button');
      editBtn.addEventListener('click', (e) => { e.stopPropagation(); openProjectModal(p); });
      delBtn.addEventListener('click', (e) => { e.stopPropagation(); deleteProject(p); });
      list.appendChild(item);
    });
    updateMemoryProjectOptions();
  } catch (err) {
    console.error('Failed to load projects', err);
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
  await Promise.all([loadConversations(), loadDocuments(), loadMemories()]);
}

function updateProjectTag() {
  const tag = $('activeProjectTag');
  if (!currentProjectId) {
    tag.style.display = 'none';
    tag.textContent = 'Sem Projeto';
    return;
  }
  const p = projectsCache.find(x => x.id === currentProjectId);
  tag.textContent = `Projeto: ${p ? p.name : currentProjectId}`;
  tag.style.display = 'inline-block';
  document.querySelectorAll('#projectsList .list-item').forEach((item) => {
    item.classList.toggle('active', item.dataset.projectId === currentProjectId);
  });
}

function openProjectModal(project = null) {
  $('projectId').value = project ? project.id : '';
  $('projectModalTitle').textContent = project ? 'Editar Projeto' : 'Novo Projeto';
  $('projectName').value = project ? project.name : '';
  $('projectDescription').value = project ? (project.description || '') : '';
  $('projectInstructions').value = project ? (project.instructions || '') : '';
  openModal('projectModal');
}

async function saveProject() {
  const id = $('projectId').value;
  const payload = {
    name: $('projectName').value.trim(),
    description: $('projectDescription').value,
    instructions: $('projectInstructions').value,
  };
  if (!payload.name) { alert('Informe o nome do projeto.'); return; }

  try {
    let saved;
    if (id) {
      await api(`/api/projects/${id}`, { method: 'PUT', body: payload });
      saved = { id, ...payload };
    } else {
      saved = await api('/api/projects', { method: 'POST', body: payload });
      currentProjectId = saved.id;
    }
    closeModal('projectModal');
    await loadProjects();
    updateProjectTag();
    if (!id) startNewChat();
  } catch (err) {
    alert(`Falha ao salvar projeto: ${err.message}`);
  }
}

async function deleteProject(project) {
  const warning = 'Excluir o projeto "' + project.name + '"?\n\nIsso remove também memórias e documentos vinculados. Conversas ficam sem projeto. Esta ação não pode ser desfeita (faça um backup antes).';
  if (!confirm(warning)) return;
  try {
    await api(`/api/projects/${project.id}`, { method: 'DELETE' });
    if (currentProjectId === project.id) { currentProjectId = null; updateProjectTag(); startNewChat(); }
    await Promise.all([loadProjects(), loadMemories(), loadDocuments(), loadConversations()]);
  } catch (err) {
    alert(`Falha ao excluir projeto: ${err.message}`);
  }
}

function updateMemoryProjectOptions(selected = null) {
  const select = $('memoryProject');
  select.innerHTML = '<option value="">Global (todos os projetos)</option>';
  projectsCache.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p.id;
    opt.textContent = p.name;
    select.appendChild(opt);
  });
  select.value = selected || currentProjectId || '';
}

// ----------------- Personality & Settings -----------------
async function loadPersonalitySettings() {
  try {
    const list = await api('/api/personalities');
    const def = list.find(p => p.is_default) || list[0];
    if (def) {
      currentPersonalityId = def.id;
      $('settingName').value = def.name;
      $('settingInstructions').value = def.system_instructions;
      $('settingTone').value = def.tone || 'prestativo';
      $('sliderFormality').value = def.formality || 3;
      $('valFormality').textContent = def.formality || 3;
      $('sliderObjectivity').value = def.objectivity || 4;
      $('valObjectivity').textContent = def.objectivity || 4;
      $('sliderDetail').value = def.detail_level || 3;
      $('valDetail').textContent = def.detail_level || 3;
      $('activePersonalityTag').textContent = def.name;
    }
  } catch (err) {
    console.error('Failed to load personality', err);
  }
}

function openSettingsModal() {
  loadPersonalitySettings();
  loadModels();
  loadBackups();
  openModal('settingsModal');
}

async function savePersonalitySettings() {
  const payload = {
    id: currentPersonalityId,
    name: $('settingName').value.trim(),
    system_instructions: $('settingInstructions').value.trim(),
    tone: $('settingTone').value,
    formality: parseInt($('sliderFormality').value, 10),
    objectivity: parseInt($('sliderObjectivity').value, 10),
    detail_level: parseInt($('sliderDetail').value, 10),
    is_default: true
  };
  if (!payload.name || !payload.system_instructions) {
    alert('Nome e instruções não podem ficar vazios.');
    return;
  }

  try {
    const saved = await api('/api/personalities', { method: 'POST', body: payload });
    currentPersonalityId = saved.id;
    closeModal('settingsModal');
    $('activePersonalityTag').textContent = saved.name;
    alert('Personalidade atualizada com sucesso!');
  } catch (err) {
    alert(`Falha ao salvar personalidade: ${err.message}`);
  }
}

// ----------------- Backup -----------------
async function loadBackups() {
  const list = $('backupList');
  try {
    const backups = await api('/api/backups');
    list.innerHTML = '';
    if (!backups.length) {
      list.innerHTML = '<p class="hint">Nenhum backup ainda.</p>';
      return;
    }
    backups.forEach(b => {
      const row = document.createElement('div');
      row.className = 'backup-row';
      const size = (b.size_bytes / 1024).toFixed(0);
      row.innerHTML = `
        <span>${escape(b.created_at)} · ${size} KB</span>
        <span class="backup-row-actions">
          <a class="btn btn-xs btn-ghost" href="/api/backups/${encodeURIComponent(b.name)}" download>Baixar</a>
          <button class="btn btn-xs btn-secondary">Restaurar</button>
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
  status.textContent = 'Criando...';
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
    alert(`Backup restaurado. Segurança criada antes: ${result.pre_restore_backup}`);
    closeModal('settingsModal');
    startNewChat();
    await Promise.all([loadConversations(), loadProjects(), loadDocuments(), loadMemories(), loadPersonalitySettings()]);
  } catch (err) {
    alert(`Falha ao restaurar: ${err.message}`);
  }
}

// ----------------- Utilities & Modals -----------------
function openModal(id) { $(id).style.display = 'flex'; }
function closeModal(id) { $(id).style.display = 'none'; }
function setPrompt(text) { chatInput.value = text; chatInput.focus(); }

async function exportCurrentChat() {
  if (!currentConversationId) { alert('Nenhuma conversa selecionada.'); return; }
  try {
    const data = await api(`/api/conversations/${currentConversationId}/export?format=md`);
    const blob = new Blob([data.content], { type: 'text/markdown' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `conversa-${currentConversationId}.md`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  } catch (err) {
    alert(`Falha ao exportar: ${err.message}`);
  }
}

async function deleteCurrentChat() {
  if (!currentConversationId) { alert('Nenhuma conversa selecionada.'); return; }
  if (!confirm('Deseja excluir esta conversa permanentemente?')) return;
  if (isGenerating) abortGeneration(true);
  try {
    await api(`/api/conversations/${currentConversationId}`, { method: 'DELETE' });
    startNewChat();
    await loadConversations();
  } catch (err) {
    alert(`Falha ao excluir: ${err.message}`);
  }
}

async function deleteConversationById(id, event) {
  if (event) event.stopPropagation();
  if (!confirm('Excluir esta conversa?')) return;
  try {
    await api(`/api/conversations/${id}`, { method: 'DELETE' });
    if (currentConversationId === id) startNewChat();
    await loadConversations();
  } catch (err) {
    alert(`Falha ao excluir: ${err.message}`);
  }
}

// Expose for debugging from the webview devtools.
window.assistantApp = {
  startNewChat, sendMessage, abortGeneration, openLibraryModal,
  openProjectModal, openMemoryModal, checkPendingAuthorizations
};
