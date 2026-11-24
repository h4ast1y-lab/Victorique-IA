# Seis funções — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pensamento Profundo, Biblioteca, botão do Turbo, LaTeX, mini-chat pelo mascote e modo Codex no app Victorique.

**Architecture:** FastAPI + página única (`app/ui`) + mascote Win32 (`app/mascot`). Cada função entra como módulo pequeno no backend (`app/core/deep_thinking.py`, `app/library/`, `app/codex/`) e como seção nova em `app.js`/`style.css`; a Biblioteca e o mini-chat ganham JS próprios (`library.js`, `mini.js`).

**Tech Stack:** Python 3.12, FastAPI, pytest, pywebview 6.2.1, claude-agent-sdk 0.2.187, KaTeX 0.16.x (vendorizado), Canvas 2D.

**Spec:** `docs/superpowers/specs/2026-11-24-seis-funcoes-design.md`

## Global Constraints

- Interface 100% local: CSP `script-src 'self'`, `font-src 'self'`; nada de CDN.
- Textos de interface em pt-BR.
- Testes isolados pelo `tests/conftest.py`; suíte de base: 297 passam, 3 pulados.
- Rodar com `"C:/Users/h4ast/Downloads/Victorique Bot/.venv/Scripts/python.exe" -m pytest -q -p no:cacheprovider`.
- Migrações de banco só aditivas (`COLUMN_MIGRATIONS`).
- Turbo continua desligado por padrão; exclusões e organizador sempre pedem autorização.
- Codex sempre com `--sandbox read-only`.

## Review Focus

- Resposta com Pensamento Profundo em que o modelo não abre `<pensamento>`: tudo vira resposta, nada se perde (teste no Task 1).
- Tag `</pensamento>` partida entre dois pedaços do stream (teste no Task 1).
- Valores em dinheiro (`R$ 10 e R$ 20`) não viram fórmula (teste JS manual no Task 2 + regra documentada).
- Vincular `C:\`, a pasta do usuário, `C:\Windows` ou a pasta do app como seção: recusado (teste no Task 4).
- Codex não instalado ou sem login: erro claro no chat com o comando de instalação, sem travar (teste no Task 6).

---

### Task 1: Pensamento Profundo (backend)

**Files:**
- Create: `app/core/deep_thinking.py`
- Modify: `app/main.py` (ChatRequest), `app/core/assistant.py`, `app/claude_code/backend.py`, `app/memory/database.py`, `app/memory/conversation_store.py`, `app/core/preferences.py`
- Test: `tests/test_deep_thinking.py`

**Interfaces:**
- Produces: `DEEP_THINKING_INSTRUCTIONS: str`; `class ThoughtSplitter` com `feed(text) -> list[tuple[str, str]]` e `finish() -> list[tuple[str, str]]`, onde cada tupla é `("thought" | "answer", texto)`; `strip_thoughts(text) -> str`.
- `conversation_store.add_message(..., reasoning: str | None = None, reasoning_seconds: float | None = None)`; `get_messages` devolve `reasoning` e `reasoning_seconds`.
- SSE: `{"type": "reasoning", "content": str, "voice": true}`; `done` ganha `reasoning_seconds`.
- Preferência `deep_thinking: bool = False`.

- [ ] Testes: `test_splitter_separates_thought_and_answer`, `test_splitter_handles_tag_split_across_chunks` (`"<pensa"`, `"mento>abc</pen"`, `"samento>resp"`), `test_splitter_without_tag_is_all_answer`, `test_splitter_keeps_leading_avatar_controls_in_answer`, `test_unclosed_thought_is_flushed_as_thought_on_finish`, `test_strip_thoughts_removes_block`, `test_reasoning_saved_and_returned_by_store`, `test_local_turn_with_deep_thinking_emits_voice_reasoning` (cliente Ollama falso emitindo `<pensamento>hm</pensamento>Resposta`).
- [ ] Rodar: falham.
- [ ] Implementar splitter (máquina de estados: `start` → espera `<pensamento>` após espaços/controles; `thought` → até `</pensamento>`; `answer`). Guardar no máximo `len(tag)-1` caracteres pendentes.
- [ ] Ligar no `assistant_engine.chat_stream(..., deep_thinking=False)`: instrução no `system_prompt`, splitter antes do `AvatarControlParser`; reasoning nativo descartado quando `deep_thinking`. Mesmo no `_Turn` do Claude Code (`run_turn(..., deep_thinking=False)`). Salvar `reasoning`.
- [ ] Testes passam; suíte inteira passa. Commit.

### Task 2: Turbo + LaTeX + Pensamento Profundo na interface

**Files:**
- Create: `app/ui/vendor/katex/` (katex.min.js, katex.min.css, fonts/*.woff2, LICENSE)
- Modify: `app/core/preferences.py` (`turbo_mode` em `SCHEMA` e `_LIVE`), `app/core/personality.py` (linha de LaTeX), `app/ui/js/markdown.js`, `app/ui/index.html`, `app/ui/js/app.js`, `app/ui/css/style.css`
- Test: `tests/test_preferences.py`, `tests/test_stream_and_ui.py`

**Interfaces:**
- `preferences.SCHEMA["turbo_mode"] = ("bool", settings.turbo_mode, None)`; `apply_to_settings` espelha em `settings.turbo_mode`.
- `window.renderMarkdown(text)` passa a devolver HTML com KaTeX quando `window.katex` existe.

- [ ] Testes: `test_turbo_preference_updates_live_setting` (POST `/api/preferences {"turbo_mode": true}` → `settings.turbo_mode is True`; volta a False), `test_index_loads_katex_locally` (index.html referencia `/ui/vendor/katex/katex.min.js` e nenhum `http`), `test_system_prompt_asks_for_latex`.
- [ ] Baixar KaTeX com `npm pack katex@0.16.11` numa pasta temporária, copiar só js/css/woff2/LICENSE.
- [ ] `markdown.js`: extrair math antes de escapar (`$$…$$`, `\[…\]`, `\(…\)`, `$…$` com a regra do dinheiro), placeholders `\u0000M{n}\u0000`, render com `katex.renderToString(src, {displayMode, throwOnError:false, trust:false, strict:'ignore'})`.
- [ ] UI: interruptor Turbo com confirmação; botão "Pensamento profundo" na composer; caixa de pensamento estilo DeepSeek (Pensando… / Pensou por N s), também no carregamento do histórico.
- [ ] Testes passam; verificação no navegador (preview 8777). Commit.

### Task 3: Mini-chat pelo mascote

**Files:**
- Create: `app/ui/mini.html`, `app/ui/js/mini.js`
- Modify: `app/mascot/desktop.py`, `app/mascot/launcher.py`, `app/ui/css/style.css`, `app/ui/js/app.js` (`victoriqueDesktop.openConversation`)
- Test: `tests/test_mascot.py`

**Interfaces:**
- Bridge do mascote ganha `toggle_mini_chat(x: int, y: int) -> None` e `open_conversation(conversation_id: str) -> None`.
- `DesktopMascot`: clique simples agenda `_pending_click = (deadline, x, y)`; duplo clique cancela; no tick, ao vencer o prazo, chama `toggle_mini_chat` com a posição dela. `CLICK_WAIT = 0.3` s (ou `GetDoubleClickTime`).
- Endpoint `POST /api/mascot/open-conversation {"conversation_id"}` → `mascot_bus.open_conversation` (o mini chama para abrir na janela grande).

- [ ] Testes: `test_single_click_opens_mini_chat_after_wait`, `test_double_click_opens_main_chat_not_mini`.
- [ ] Implementar; mini.html usa `markdown.js`, KaTeX e o mesmo SSE; guarda `conversation_id` em preferência `mini_conversation_id` (str, 64).
- [ ] Testes passam. Commit.

### Task 4: Biblioteca (backend)

**Files:**
- Create: `app/library/__init__.py`, `app/library/sections.py`, `app/library/activity.py`
- Modify: `app/main.py` (rotas `/api/library/*`, `/api/mascot/atlas`, `/api/mascot/atlas.json`), `app/tools/organizer.py`, `app/tools/registry.py`, `app/claude_code/backend.py`
- Test: `tests/test_library.py`

**Interfaces:**
- `sections.list_sections() -> list[dict]` (`id, name, path, kind: "default"|"linked", exists`); `sections.link(path: str, name: str | None) -> dict`; `sections.unlink(section_id: str) -> None`; `sections.books(section_id: str, limit=120) -> dict` (`files: [{name, path, ext, size, modified}]`, `total`); `sections.section_for(path: str) -> str | None`; `sections.apply_authorization() -> None`.
- `activity.record(kind: str, src: str | None, dst: str | None = None, actor="victorique") -> None` (kinds: `read`, `list`, `move`, `rename`, `reserve`, `undo`, `write`); `activity.since(seq: int) -> {"events": [...], "last": int}`.
- Rotas: `GET /api/library/sections`, `POST /api/library/sections {path, name}`, `DELETE /api/library/sections/{id}`, `GET /api/library/sections/{id}/books`, `GET /api/library/activity?since=N`, `POST /api/library/pick-folder`.

- [ ] Testes: `test_default_sections_only_existing_folders`, `test_link_refuses_drive_root_home_system_and_app_dirs`, `test_link_adds_authorized_dir_and_unlink_removes_it`, `test_books_lists_files_newest_first_without_reading_content`, `test_organizer_move_records_activity_with_sections`, `test_read_file_tool_records_read_activity`, `test_activity_since_returns_only_new_events`.
- [ ] Implementar (seções em `DATA_DIR/library.json`; atividade em memória, últimas 200).
- [ ] Testes passam. Commit.

### Task 5: Biblioteca (interface)

**Files:**
- Create: `app/ui/js/library.js`
- Modify: `app/ui/index.html` (aba Documentos renomeada; aba Biblioteca; vista `#libraryView`), `app/ui/js/app.js`, `app/ui/css/style.css`

**Interfaces:**
- `window.VictoriqueLibrary = { open(), close(), notifyActivity() }`.
- Salão em canvas: estantes por seção, livros por arquivo, Victorique com o atlas; fila de atividades vira tarefas (ir até estante → ler / carregar até outra estante / até o carrinho da Reserva); ocioso: passear, ler, chá, pensar, cochilar.

- [ ] Verificação no navegador: abre a aba, mostra seções, adiciona seção com caminho, clicar num livro mostra o cartão, mover arquivo pelo organizador faz ela carregar o livro.
- [ ] Commit.

### Task 6: Modo Codex

**Files:**
- Create: `app/codex/__init__.py`, `app/codex/backend.py`
- Modify: `app/config.py` (`VALID_BACKENDS` + `codex`), `app/core/assistant.py`, `app/main.py` (`/api/codex/status`, health), `app/memory/database.py` (`conversations.codex_thread_id`), `app/memory/conversation_store.py`, `app/ui/index.html`, `app/ui/js/app.js`
- Test: `tests/test_codex_backend.py`

**Interfaces:**
- `find_codex() -> str | None`; `build_command(exe, workspace, thread_id) -> list[str]`; `class CodexBackend` com `run_turn(conversation_id, user_message, project_id, personality_id, deep_thinking=False)` (async gen de SSE) e `process_factory` injetável.
- Tradução de eventos: `agent_message` → `token`; `reasoning` → `reasoning`; `command_execution` → `tool_call`/`tool_result`; `file_change` → `tool_result` (+ atividade); `turn.failed`/`error` → `error`.

- [ ] Testes: `test_build_command_is_read_only_and_resumes`, `test_turn_translates_jsonl_events` (processo falso), `test_missing_codex_gives_install_help`, `test_resume_failure_starts_new_thread_with_notice`.
- [ ] Implementar. Testes passam; suíte inteira passa. Commit.

### Task 7: Fechamento

- [ ] Suíte inteira; preview no navegador de todas as telas; README (seções novas); memória do projeto atualizada.
