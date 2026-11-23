# Modo Claude Code e persona Victorique — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar o backend `claude-code` (Claude Agent SDK) com aprovações pela barra de autorização do app, e a persona Victorique como perfil padrão.

**Architecture:** Um pacote `app/claude_code/` roda um turno por mensagem com `ClaudeSDKClient` (retomando a sessão salva na conversa), traduz as mensagens do SDK para os eventos SSE que a interface já entende e liga o callback `can_use_tool` ao `SecurityManager` por meio de futures. O `assistant_engine` só desvia para ele quando o backend é `claude-code`; os backends locais não mudam.

**Tech Stack:** Python 3.12, FastAPI/SSE, SQLite, `claude-agent-sdk==0.2.187`, pytest + pytest-asyncio, JS puro na interface.

**Spec:** `docs/superpowers/specs/2026-11-23-claude-code-mode-victorique-design.md`

## Global Constraints

- `claude-agent-sdk==0.2.187` fixado no `requirements.txt`.
- Opções do SDK sempre com `setting_sources=[]` e `include_partial_messages=True`; `permission_mode="default"` (ou `"acceptEdits"` com `settings.turbo_mode`).
- `system_prompt={"type": "preset", "preset": "claude_code", "append": <texto>}`; nunca substituir o prompt do Claude Code.
- Pedido de autorização sem resposta em `settings.authorization_ttl_seconds` (120 s) → negado.
- Escrita/edição em caminho protegido (`path_guard.is_protected`) → negada sem perguntar.
- Servidor MCP `victorique` somente leitura; ferramentas `mcp__victorique__buscar_memorias` e `mcp__victorique__buscar_documentos` em `allowed_tools`.
- Texto visível ao usuário em português. Persona escrita do zero, sem falas da obra.
- Testes nunca chamam o Claude Code real; usam um cliente falso injetado por fábrica.
- Testes do projeto: `.venv\Scripts\python.exe -m pytest -q` (todos verdes ao fim de cada tarefa).

## Review Focus

1. Usuário nunca responde à autorização (fechou a janela) → nega após o TTL; o turno termina com mensagem, sem travar. (Tarefa 3)
2. Usuário clica "Parar" com uma autorização pendente → pedido negado, cliente interrompido, resposta parcial salva com o marcador de cancelamento. (Tarefa 5)
3. SDK ausente ou Claude Code sem login → evento `error` claro em português; a conversa continua usável. (Tarefa 5)
4. Sessão salva não pode ser retomada (pasta mudou/sessão apagada) → sessão nova + evento `notice`. (Tarefa 5)
5. Regras pessoais do Claude Code ("allow") não podem liberar nada → `setting_sources=[]` verificado nas opções. (Tarefa 5)

---

### Task 0: Instalar o SDK e testar o login real

**Files:**
- Modify: `requirements.txt`
- Create: `scripts/claude_login_check.py`

- [ ] **Step 1:** Adicionar `claude-agent-sdk==0.2.187` ao `requirements.txt` e instalar no `.venv`.
- [ ] **Step 2:** `scripts/claude_login_check.py`: `query(prompt="Responda apenas: OK", options=ClaudeAgentOptions(setting_sources=[], max_turns=1, allowed_tools=[]))`, imprime o texto, `session_id`, `is_error` e `total_cost_usd` do `ResultMessage`.
- [ ] **Step 3:** Rodar `.venv\Scripts\python.exe scripts\claude_login_check.py`. Esperado: `OK`. Se falhar por login, registrar a mensagem exata — ela define o texto de ajuda da Tarefa 5 — e avisar o usuário (precisa logar antes do teste real da Tarefa 7).
- [ ] **Step 4:** Commit `chore: add claude-agent-sdk and login check script`.

### Task 1: Persona Victorique

**Files:**
- Modify: `app/memory/database.py`, `app/core/personality.py`, `app/config.py`, `app/ui/index.html`, `run.py`
- Test: `tests/test_victorique_persona.py`

**Interfaces:**
- Produces: perfil `id='victorique'`; `personality_manager.build_system_prompt(personality: Optional[dict] = None, mode: str = "local") -> str` com `mode in {"local", "claude-code"}`.

- [ ] **Step 1: Testes que falham**
  - `test_victorique_profile_is_seeded`: `personality_manager.get_personality("victorique")["name"] == "Victorique"`.
  - `test_victorique_is_default_on_fresh_db`: com `ASSISTANT_DATA_DIR` novo em subprocesso, o perfil com `is_default=1` é `victorique`.
  - `test_user_profile_default_is_preserved`: banco com perfil do usuário como padrão + `init_db()` de novo → padrão continua o do usuário.
  - `test_prompt_states_real_mode`: `build_system_prompt(p, mode="claude-code")` contém `"Claude Code"` e não contém `"localmente"`; `mode="local"` contém `"localmente"`.
  - `test_persona_keeps_work_quality_rules`: o texto do perfil contém as regras "nunca recusa tarefa por tédio" e "não inventa resultados" (substrings `"tédio"` e `"inventa"`).
- [ ] **Step 2:** Rodar; esperado FAIL.
- [ ] **Step 3:** Em `init_db`, inserir `victorique` se não existir; **só nessa inserção**, torná-lo padrão quando não houver perfis além de `default`. Instruções em português, originais: gênia entediada, orgulhosa, língua afiada, finge desinteresse mas resolve e se importa; tom de personagem nunca reduz qualidade; direta em erros, ações destrutivas e assuntos sérios; não inventa resultados; nunca recusa tarefa por tédio. `formality=3, objectivity=4, detail_level=3, tone="sarcástica e brilhante"`.
- [ ] **Step 4:** `build_system_prompt(..., mode)`: linha `MODO DE OPERAÇÃO:` — local: "Você roda localmente no computador do usuário."; claude-code: "Você opera pelo Claude Code; as mensagens são processadas pela Anthropic." `settings.app_name = "Victorique"`; título/brand do `index.html` e `title` da janela no `run.py` = "Victorique".
- [ ] **Step 5:** Rodar a suíte; esperado PASS. Commit `feat: add Victorique persona as default profile`.

### Task 2: Configurações de modo e sessão por conversa

**Files:**
- Modify: `app/config.py`, `app/memory/database.py`, `app/memory/conversation_store.py`, `app/main.py`
- Test: `tests/test_backend_settings.py`

**Interfaces:**
- Produces:
  - `settings.claude_code_workspace: str` (env `ASSISTANT_CLAUDE_WORKSPACE`, padrão `~/Documents`), `settings.claude_code_model: str` (env `ASSISTANT_CLAUDE_MODEL`, padrão `""`).
  - `VALID_BACKENDS = {"llama-cpp", "llama-cpp-server", "ollama", "claude-code"}` em `app/config.py`.
  - `main._current_backend() -> str` (tabela `settings`, chave `default_backend`, fallback `settings.default_backend`).
  - Coluna `conversations.claude_session_id` (em `COLUMN_MIGRATIONS`); `conversation_store.get_claude_session(conversation_id) -> Optional[str]`, `conversation_store.set_claude_session(conversation_id, session_id: Optional[str]) -> None`.
  - `GET /api/claude-code/status` → `{"sdk_installed": bool, "cli_path": str|None, "workspace": str, "model": str, "last_error": str|None}`.

- [ ] **Step 1: Testes que falham**
  - `test_backend_choice_is_persisted`: `POST /api/settings {"default_backend": "claude-code"}` → 200; `GET /api/settings` → `default_backend == "claude-code"` e `available_backends` contém os 4.
  - `test_invalid_backend_rejected`: `{"default_backend": "gpt"}` → 400.
  - `test_chat_uses_persisted_backend`: com backend salvo `claude-code` e engine monkeypatched, `/api/chat` sem `backend` chama o engine com `backend="claude-code"`.
  - `test_claude_session_roundtrip`: `set_claude_session(cid, "s1")` → `get_claude_session(cid) == "s1"`; `None` limpa.
  - `test_claude_status_endpoint`: retorna as 5 chaves.
- [ ] **Step 2:** Rodar; FAIL.
- [ ] **Step 3:** Implementar. O auto-start do llama-server no `main.py` passa a usar `_current_backend()` (não sobe o llama.cpp quando o modo salvo é `claude-code`). `last_error` vem de `claude_code.backend.last_error` (Tarefa 5; até lá, `None`).
- [ ] **Step 4:** Suíte verde. Commit `feat: persist backend choice and claude session per conversation`.

### Task 3: Ponte de permissões

**Files:**
- Modify: `app/security/permissions.py`, `app/main.py` (`/api/security/authorize`)
- Create: `app/claude_code/__init__.py`, `app/claude_code/permissions.py`
- Test: `tests/test_claude_permissions.py`

**Interfaces:**
- Produces:
  - `security_manager.create_waiting_request(action_type: str, resource: str, description: str, payload: dict, context: dict|None = None) -> tuple[str, asyncio.Future]` — pedido com `kind="claude_code"`; o future recebe `True`/`False`. `resolve_action_detailed` e `_purge_expired` completam o future (aprovado → True; recusado/expirado → False).
  - `/api/security/authorize`: ação com `kind == "claude_code"` aprovada → `{"status": "approved"}` sem chamar `tool_registry`.
  - `class PermissionBridge` em `app/claude_code/permissions.py`: `__init__(self, emit: Callable[[dict], None], conversation_id: str)`; `async can_use_tool(self, tool_name: str, input_data: dict, context) -> PermissionResultAllow | PermissionResultDeny`; `cancel_pending(self) -> None` (nega tudo que estiver pendente).
  - `describe_target(tool_name: str, input_data: dict) -> str`: `file_path`/`notebook_path` → caminho; `command` → comando; `url`; `query`; `path`/`pattern`; senão JSON truncado em 200.

- [ ] **Step 1: Testes que falham**
  - `test_approval_allows`: chamar `can_use_tool("Write", {"file_path": <tmp>/a.txt, "content": "x"}, None)` numa task; o `emit` recebe `{"type": "authorization_required", "action_id": ..., "tool_name": "Write", "resource": <caminho>}`; `resolve_action_detailed(id, True)` → resultado `PermissionResultAllow`.
  - `test_rejection_denies`: idem com `False` → `PermissionResultDeny` com `message` não vazia.
  - `test_timeout_denies` (Review Focus 1): `settings.authorization_ttl_seconds` monkeypatched para 1 e `max(30, ...)` contornado via parâmetro `ttl` do bridge (`PermissionBridge(..., ttl=0.2)`) → Deny, e o pedido some de `list_pending_actions()`.
  - `test_protected_path_denied_without_asking`: `Edit` em `BASE_DIR/app/main.py` → Deny e `emit` não chamado.
  - `test_cancel_pending_denies`: `cancel_pending()` com pedido aberto → Deny.
  - `test_authorize_endpoint_does_not_run_registry_for_claude`: `POST /api/security/authorize` aprovando um pedido `claude_code` → `{"status": "approved"}`.
  - `test_decisions_are_audited`: após aprovar, `audit_logs` tem linha `action_type="Write"`, `authorized=1`.
- [ ] **Step 2:** Rodar; FAIL.
- [ ] **Step 3:** Implementar (`PermissionBridge.__init__` aceita `ttl: float | None = None`; padrão `settings.authorization_ttl_seconds`). Espera com `asyncio.wait_for`; no timeout, `resolve_action_detailed(id, False)`.
- [ ] **Step 4:** Suíte verde. Commit `feat: bridge Claude Code permissions to the authorization bar`.

### Task 4: Ferramentas da Victorique (MCP)

**Files:**
- Create: `app/claude_code/victorique_tools.py`
- Test: `tests/test_victorique_tools.py`

**Interfaces:**
- Produces: `async buscar_memorias(args: dict, project_id: Optional[str]) -> dict`, `async buscar_documentos(args: dict, project_id: Optional[str]) -> dict` (formato MCP `{"content": [{"type": "text", "text": ...}]}`); `create_victorique_server(project_id: Optional[str]) -> McpSdkServerConfig` (nome `"victorique"`); `VICTORIQUE_TOOL_NAMES = ["mcp__victorique__buscar_memorias", "mcp__victorique__buscar_documentos"]`.

- [ ] **Step 1: Testes que falham**
  - `test_buscar_memorias_returns_active_memories`: cria memória global "Prefiro relatórios em PDF" → texto do resultado contém a frase.
  - `test_buscar_memorias_respects_project`: memória do projeto B não aparece com `project_id=A`.
  - `test_buscar_documentos_offline_returns_notice`: `vector_store.search` monkeypatched para levantar `httpx.ConnectError` → resultado contém "indisponível" e não levanta.
  - `test_buscar_documentos_cites_title_and_page`: `search` falso devolve 1 trecho → texto contém título e "página 3".
  - `test_server_exposes_two_tools`: `create_victorique_server(None)` tem `name == "victorique"`.
- [ ] **Step 2:** Rodar; FAIL.
- [ ] **Step 3:** Implementar com `@tool` + `create_sdk_mcp_server`; os handlers decorados fecham sobre `project_id` e chamam as funções testáveis acima. Usar `memory_store.get_context_for_prompt(project_id=..., user_query=consulta)` e `vector_store.search(query=..., project_id=..., top_k=4)`.
- [ ] **Step 4:** Suíte verde. Commit `feat: expose Victorique memories and documents to Claude Code`.

### Task 5: Backend do turno Claude Code

**Files:**
- Create: `app/core/sse.py`, `app/claude_code/options.py`, `app/claude_code/backend.py`
- Modify: `app/core/assistant.py` (`_event` passa a vir de `app/core/sse.py`)
- Test: `tests/test_claude_backend.py`

**Interfaces:**
- Consumes: `PermissionBridge` (T3), `create_victorique_server`/`VICTORIQUE_TOOL_NAMES` (T4), `get/set_claude_session` (T2), `build_system_prompt(..., mode="claude-code")` (T1).
- Produces:
  - `sse_event(payload: dict) -> str` em `app/core/sse.py`.
  - `build_options(*, append_prompt: str, resume: Optional[str], bridge: PermissionBridge, project_id: Optional[str]) -> ClaudeAgentOptions` em `options.py` (cwd = `settings.claude_code_workspace`; `add_dirs` = `path_guard.authorized_dirs` sem os caminhos protegidos; `model` só se `settings.claude_code_model`).
  - `class ClaudeCodeBackend` em `backend.py`: `__init__(self, client_factory: Callable[[ClaudeAgentOptions], Any] = ClaudeSDKClient)`; `async run_turn(self, conversation_id: str, user_message: str, project_id: Optional[str], personality_id: Optional[str]) -> AsyncGenerator[str, None]` (strings SSE); atributo `last_error: Optional[str]`. Instância `claude_code_backend`.

- [ ] **Step 1: Testes que falham** (cliente falso: `connect`, `query`, `receive_response` que devolve uma lista roteirizada de mensagens do SDK, `interrupt`, `disconnect`; registra as `options` recebidas)
  - `test_text_and_reasoning_deltas_map_to_events`: `StreamEvent` com `content_block_delta`/`text_delta` "Olá" e `thinking_delta` "hmm" → eventos `token` "Olá" e `reasoning` "hmm"; `done.content == "Olá"`; o mesmo texto vindo também em `AssistantMessage/TextBlock` não duplica.
  - `test_tool_use_and_result_events_and_trace`: `ToolUseBlock(id="t1", name="Read", input={"file_path": "x"})` + `ToolResultBlock(tool_use_id="t1", content="abc", is_error=False)` → eventos `tool_call` (tool "Read") e `tool_result` (status "success"); mensagem salva com `tool_trace[0]["tool"] == "Read"`.
  - `test_session_id_saved_and_resumed`: 1º turno → `ResultMessage(session_id="s1")` salva `s1`; 2º turno → `options.resume == "s1"`.
  - `test_resume_failure_starts_new_session` (Review Focus 4): fábrica levanta na 1ª tentativa com `resume` → 2ª tentativa sem `resume`, evento `notice`, sessão nova salva.
  - `test_missing_login_or_sdk_gives_clear_error` (Review Focus 3): `ResultMessage(is_error=True, result="Invalid API key · Please run /login")` → evento `error` em português contendo "login"; `last_error` preenchido; `done` emitido.
  - `test_cancel_interrupts_and_saves_partial` (Review Focus 2): fechar o gerador após o 1º `token` → `interrupt()` chamado, `bridge.cancel_pending()` chamado, mensagem salva termina com `CANCELLED_MARKER`.
  - `test_options_are_locked_down` (Review Focus 5): `options.setting_sources == []`, `include_partial_messages is True`, `permission_mode == "default"`, `system_prompt["preset"] == "claude_code"`, `"Victorique"` em `system_prompt["append"]`, `VICTORIQUE_TOOL_NAMES` ⊂ `allowed_tools`, `can_use_tool` definido.
  - `test_turbo_uses_accept_edits`: com `settings.turbo_mode=True` → `permission_mode == "acceptEdits"`.
- [ ] **Step 2:** Rodar; FAIL.
- [ ] **Step 3:** Implementar. O consumo do SDK roda numa `asyncio.Task` que põe eventos numa `asyncio.Queue`; o `emit` do bridge também escreve nela; um sentinel encerra. Texto de ajuda de login: o da Tarefa 0. TTS fala a resposta final com a mesma condição do engine local.
- [ ] **Step 4:** Suíte verde. Commit `feat: Claude Code backend with streamed events and sessions`.

### Task 6: Roteamento e interface

**Files:**
- Modify: `app/core/assistant.py`, `app/ui/index.html`, `app/ui/js/app.js`, `app/ui/css/style.css`
- Test: `tests/test_claude_routing_ui.py`

**Interfaces:**
- Consumes: `claude_code_backend.run_turn` (T5), `/api/settings` com `default_backend` (T2).

- [ ] **Step 1: Testes que falham**
  - `test_engine_routes_claude_code`: `claude_code_backend.run_turn` monkeypatched → `assistant_engine.chat_stream(..., backend="claude-code")` repassa os eventos; a mensagem do usuário é salva uma vez só.
  - `test_ui_has_mode_selector_and_badge`: `index.html` contém `id="modeSelect"` com opção `value="claude-code"` e `id="claudeBadge"`; `app.js` contém `default_backend`.
- [ ] **Step 2:** Rodar; FAIL.
- [ ] **Step 3:** Engine: logo após salvar a mensagem do usuário, se `backend == "claude-code"`, repassar `run_turn` e retornar. Interface: seletor no topo (Local llama.cpp / Local Ollama / Claude Code) que faz `POST /api/settings`; selo `claudeBadge` "Claude Code — dados enviados à Anthropic", visível só nesse modo; `sendMessage` envia `backend` do seletor.
- [ ] **Step 4:** Suíte verde. Commit `feat: mode selector and Claude Code routing`.

### Task 7: Teste real e README

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** Subir o app (`run.py --server`), modo Claude Code, e pela API: (a) "Oi, quem é você?" → resposta no tom da Victorique; (b) pedir para listar uma pasta dos Documentos → leitura sem pedir autorização; (c) pedir para criar `victorique_teste.txt` → pedido na barra; aprovar → arquivo criado; (d) pedir de novo e recusar → nada criado. Apagar o arquivo de teste ao fim.
- [ ] **Step 2:** README: seção "Modo Claude Code" (login, privacidade, permissões, `ASSISTANT_CLAUDE_WORKSPACE`, `ASSISTANT_CLAUDE_MODEL`), persona Victorique, novos endpoints e o teste real registrado.
- [ ] **Step 3:** Commit `docs: Claude Code mode and Victorique persona`.
