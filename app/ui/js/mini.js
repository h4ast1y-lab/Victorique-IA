/*
 * Conversa rápida: a janelinha que abre com um clique na Victorique da área
 * de trabalho. Usa o mesmo /api/chat em streaming da janela grande (mesmo
 * modo e perfil padrão), mostra o Pensamento profundo e fórmulas, e guarda a
 * própria conversa na preferência "mini_conversation_id".
 */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const MINI_TITLE = 'Conversa rápida';
  const HISTORY_SHOWN = 40;

  let prefs = {};
  let profile = null;
  let conversationId = '';
  let busy = false;
  let abortController = null;
  let loaded = false;
  let saving = Promise.resolve();  // preference saves, in order

  async function api(path, options = {}) {
    const opts = { method: options.method || 'GET', headers: {} };
    if (options.body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(options.body);
    }
    const res = await fetch(path, opts);
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try { detail = (await res.json()).detail || detail; } catch (_) { /* not JSON */ }
      const err = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
      err.status = res.status;
      throw err;
    }
    return res.json();
  }

  function md(text) {
    return window.renderMarkdown ? window.renderMarkdown(text) : window.escapeHtml(text);
  }

  function signal(state) {
    api('/api/mascot/signal', { method: 'POST', body: { state } }).catch(() => {});
  }

  function savePrefs(changes) {
    Object.assign(prefs, changes);
    saving = saving.then(() => api('/api/preferences', { method: 'POST', body: changes }).catch(() => {}));
    return saving;
  }

  // ----------------- Aparência (as mesmas preferências da janela grande) -----------------
  function applyAppearance() {
    const root = document.documentElement;
    let theme = prefs.theme || 'dark';
    if (theme === 'system') {
      theme = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
    }
    root.dataset.theme = theme;
    root.dataset.accent = prefs.accent || 'terracota';
    root.dataset.fontSize = prefs.font_size || 'medium';
    root.dataset.responseFont = prefs.response_font || 'sans';
    const deep = !!prefs.deep_thinking;
    $('btnMiniThink').setAttribute('aria-pressed', String(deep));
    $('btnMiniThink').classList.toggle('on', deep);
    $('miniInput').placeholder = `Fale com ${profile ? profile.name : 'a Victorique'}`;
  }

  // ----------------- Mensagens -----------------
  function setEmpty(empty) {
    $('miniEmpty').hidden = !empty;
    $('btnMiniExpand').disabled = !conversationId;
  }

  function scrollDown() {
    const thread = $('miniThread');
    thread.scrollTop = thread.scrollHeight;
  }

  function addMessage(role, content, { reasoning = '', reasoningSeconds = null } = {}) {
    const msg = document.createElement('div');
    msg.className = `message ${role}`;
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    if (role === 'user') {
      bubble.textContent = content;
      msg.appendChild(bubble);
    } else {
      const body = document.createElement('div');
      body.className = 'msg-body';
      if (reasoning) body.appendChild(createThoughtBox(true, { text: reasoning, seconds: reasoningSeconds }).el);
      bubble.innerHTML = md(content || '');
      body.appendChild(bubble);
      msg.appendChild(body);
    }
    $('miniMessages').appendChild(msg);
    setEmpty(false);
    scrollDown();
    return msg;
  }

  async function loadConversation() {
    $('miniMessages').innerHTML = '';
    conversationId = prefs.mini_conversation_id || '';
    if (conversationId) {
      try {
        const data = await api(`/api/conversations/${encodeURIComponent(conversationId)}/messages`);
        data.messages
          .filter(m => m.role === 'user' || m.role === 'assistant')
          .slice(-HISTORY_SHOWN)
          .forEach(m => addMessage(m.role, m.content, { reasoning: m.reasoning, reasoningSeconds: m.reasoning_seconds }));
      } catch (err) {
        if (err.status === 404) {  // apagada na janela grande: começa outra
          conversationId = '';
          savePrefs({ mini_conversation_id: '' });
        }
      }
    }
    setEmpty(!$('miniMessages').children.length);
  }

  async function ensureConversation() {
    if (conversationId) return conversationId;
    const body = { title: MINI_TITLE };
    if (profile) body.personality_id = profile.id;
    const conv = await api('/api/conversations', { method: 'POST', body });
    conversationId = conv.id;
    await savePrefs({ mini_conversation_id: conversationId });
    return conversationId;
  }

  // ----------------- Envio em streaming -----------------
  async function send() {
    const input = $('miniInput');
    const text = input.value.trim();
    if (!text || busy) return;
    $('miniAuth').hidden = true;
    try {
      await ensureConversation();
    } catch (err) {
      addMessage('assistant', `_Não consegui abrir a conversa: ${err.message}_`);
      return;
    }
    input.value = '';
    autoGrow();
    addMessage('user', text);
    const msg = addMessage('assistant', '');
    msg.classList.add('streaming');
    const body = msg.querySelector('.msg-body');
    const bubble = msg.querySelector('.message-bubble');
    bubble.innerHTML = `<span class="thinking">${PIPE_SVG}${window.escapeHtml(profile ? profile.name : 'Victorique')} está pensando…</span>`;

    setBusy(true);
    signal('pensando');
    let answer = '';
    let thoughtBox = null;
    let reasoningBox = null;
    let failed = false;
    abortController = new AbortController();
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: abortController.signal,
        body: JSON.stringify({
          conversation_id: conversationId,
          message: text,
          personality_id: profile ? profile.id : undefined,
          enable_rag: prefs.enable_rag !== false,
          deep_thinking: !!prefs.deep_thinking,
        }),
      });
      if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try { detail = (await response.json()).detail || detail; } catch (_) { /* ignore */ }
        throw new Error(detail);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let talking = false;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop();
        for (const block of blocks) {
          const lines = block.split(/\r?\n/).filter(l => l.startsWith('data:')).map(l => l.slice(5).trimStart());
          if (!lines.length) continue;
          let data;
          try { data = JSON.parse(lines.join('\n')); } catch (_) { continue; }

          if (data.type === 'reasoning') {
            if (data.voice) {
              if (!thoughtBox) {
                thoughtBox = createThoughtBox(true, { live: true });
                body.insertBefore(thoughtBox.el, bubble);
                if (bubble.querySelector('.thinking')) bubble.innerHTML = '';
              }
              thoughtBox.append(data.content || '');
            } else if (prefs.show_reasoning !== false) {
              if (!reasoningBox) {
                reasoningBox = createThoughtBox(false);
                body.insertBefore(reasoningBox.el, bubble);
              }
              reasoningBox.append(data.content || '');
            }
            scrollDown();
          } else if (data.type === 'tool_call') {
            if (thoughtBox) thoughtBox.setLive(false);
            $('miniStatus').textContent = `Usando ${data.tool || 'uma ferramenta'}…`;
          } else if (data.type === 'authorization_required') {
            $('miniAuth').hidden = false;
          } else if (data.type === 'avatar') {
            api('/api/mascot/signal', {
              method: 'POST', body: { expression: data.expression || null, gesture: data.gesture || null },
            }).catch(() => {});
          } else if (data.type === 'token') {
            if (thoughtBox) thoughtBox.setLive(false);
            if (!talking) { talking = true; signal('falando'); }
            answer += data.content || '';
            bubble.innerHTML = md(answer);
            scrollDown();
          } else if (data.type === 'error') {
            failed = true;
            const err = document.createElement('div');
            err.className = 'stream-error';
            err.textContent = `Erro do modelo: ${data.message}`;
            body.appendChild(err);
          } else if (data.type === 'done') {
            if (thoughtBox) thoughtBox.finish(data.reasoning_seconds);
            answer = data.content || answer;
            bubble.innerHTML = md(answer);
          }
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        const note = document.createElement('div');
        note.className = 'cancelled-note';
        note.textContent = 'Resposta interrompida.';
        body.appendChild(note);
      } else {
        failed = true;
        bubble.innerHTML = `<p class="text-danger">Erro de comunicação: ${window.escapeHtml(err.message)}</p>`;
      }
    } finally {
      if (thoughtBox) thoughtBox.setLive(false);
      if (bubble.querySelector('.thinking')) bubble.innerHTML = '';
      if (!answer && !failed && !body.querySelector('.cancelled-note')) {
        const err = document.createElement('div');
        err.className = 'stream-error';
        err.textContent = 'O modelo não respondeu. Confira na janela grande se o modo escolhido está funcionando.';
        body.appendChild(err);
      }
      msg.classList.remove('streaming');
      abortController = null;
      $('miniStatus').textContent = MINI_TITLE;
      setBusy(false);
      signal(failed ? 'erro' : 'acordada');
      scrollDown();
    }
  }

  function setBusy(on) {
    busy = on;
    $('btnMiniSend').hidden = on;
    $('btnMiniStop').hidden = !on;
  }

  function autoGrow() {
    const input = $('miniInput');
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 140) + 'px';
  }

  // ----------------- Botões -----------------
  function openInMainWindow() {
    if (!conversationId) return;
    api('/api/mascot/open-conversation', { method: 'POST', body: { conversation_id: conversationId } }).catch(() => {});
  }

  function bind() {
    $('miniForm').addEventListener('submit', (e) => { e.preventDefault(); send(); });
    $('miniInput').addEventListener('input', autoGrow);
    $('miniInput').addEventListener('keydown', (e) => {
      if (e.key !== 'Enter' || e.isComposing) return;
      const enterSends = prefs.enter_to_send !== false;
      if ((enterSends && !e.shiftKey) || (!enterSends && e.ctrlKey)) {
        e.preventDefault();
        send();
      }
    });
    $('btnMiniStop').addEventListener('click', () => abortController && abortController.abort());
    $('btnMiniThink').addEventListener('click', () => {
      savePrefs({ deep_thinking: !prefs.deep_thinking });
      applyAppearance();
    });
    $('btnMiniNew').addEventListener('click', () => {
      if (busy) return;
      conversationId = '';
      savePrefs({ mini_conversation_id: '' });
      $('miniMessages').innerHTML = '';
      $('miniAuth').hidden = true;
      setEmpty(true);
      $('miniInput').focus();
    });
    $('btnMiniExpand').addEventListener('click', openInMainWindow);
    $('btnMiniAuth').addEventListener('click', openInMainWindow);
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !busy) {
        api('/api/mascot/command', { method: 'POST', body: { action: 'close-mini' } }).catch(() => {});
      }
    });
    // Coming back to the window: pick up changes made in the main one.
    window.addEventListener('focus', () => { if (!busy) refresh(); });
  }

  async function refresh() {
    await saving;  // never read back a preference that is still being saved
    try {
      prefs = await api('/api/preferences');
    } catch (_) { /* keeps the last ones */ }
    try {
      const profiles = await api('/api/personalities');
      profile = profiles.find(p => p.is_default) || profiles[0] || null;
      if (profile) $('miniName').textContent = profile.name;
    } catch (_) { /* default name stays */ }
    applyAppearance();
    // Reload only when the stored conversation changed (e.g. deleted in the main window).
    if (!loaded || (prefs.mini_conversation_id || '') !== conversationId) {
      loaded = true;
      await loadConversation();
    }
  }

  bind();
  refresh().then(() => $('miniInput').focus());
})();
