# Modo Claude Code e persona Victorique — design

Data: 2026-11-23 · Status: aguardando aprovação

## Intenção

A Victorique é a assistente pessoal do usuário e mexe nos arquivos dele. Ela
precisa funcionar de dois modos:

1. **Modo Claude Code**: cada mensagem é entregue ao Claude Code instalado na
   máquina, que faz o trabalho com as próprias ferramentas (ler, editar, buscar,
   rodar comandos).
2. **Modo local**: llama.cpp ou Ollama, com o laço de ferramentas do próprio app
   (já existe e foi corrigido).

Nos dois modos ela fala como a **Victorique de Blois, de *Gosick***.

## Objetivos

- Um terceiro backend, `claude-code`, escolhido na interface e salvo nas
  configurações, ao lado de `llama-cpp` e `ollama`.
- Cada conversa da Victorique fica ligada a uma sessão do Claude Code, retomada
  pelo id, para que o Claude lembre o que já fez naquela conversa.
- Toda ação do Claude que precise de permissão aparece na **barra de autorização
  atual** do app e espera a decisão do usuário. A decisão fica no log de
  auditoria.
- O Claude consegue consultar as memórias e os documentos da Victorique.
- Texto em streaming, raciocínio separado da resposta (evento `reasoning`) e o
  botão "Parar" interrompe de verdade.
- A persona Victorique vira um perfil de personalidade, padrão em bancos novos.
- A interface deixa claro quando o modo Claude está ativo (os dados saem da
  máquina e vão para a Anthropic).

## Fora do escopo

- Refatorar os backends locais (llama.cpp/Ollama) para uma interface comum.
- Lixeira, filtro de URL, configuração portátil do llama.cpp e detecção
  automática de caminhos.
- Voz com o timbre da personagem; empacotamento e distribuição do app.
- O Claude criar ou editar memórias (memórias continuam só por ação do usuário,
  como diz o README).

## Anti-objetivos (seria falha mesmo funcionando)

- O Claude escrever, editar, apagar ou rodar comandos sem aprovação do usuário.
- Configurações pessoais do Claude Code (`~/.claude/settings.json`, regras de
  permissão "allow") liberarem ações por fora da barra de autorização.
- A personagem piorar o trabalho: recusar tarefa "por tédio", esconder erro,
  inventar resultado.
- O texto da persona copiar falas ou trechos da obra original.
- A interface sugerir "100% local/offline" enquanto o modo Claude está ativo.

## Restrições

- Windows 11, Python 3.12 no `.venv`. O app é FastAPI + SSE + pywebview +
  SQLite.
- `claude-agent-sdk` 0.2.187 (wheel de 170 MB que já traz o Claude Code). O
  login é o do Claude Code (assinatura ou `ANTHROPIC_API_KEY`). Uso pessoal; se
  o app for distribuído, precisa de chave de API.
- Ainda não verificado: se o login atual do usuário funciona com o CLI do
  pacote. O primeiro passo da implementação é um teste rápido disso.
- Rodar o Claude Code de verdade consome a cota/assinatura do usuário.

## Abordagens consideradas

| | Como | Troca | Decisão |
|---|---|---|---|
| **A** | Claude Agent SDK (`ClaudeSDKClient`), sessão por conversa, callback de permissão ligado à barra de autorização, ferramentas MCP da Victorique | Mais código de integração; dependência de 170 MB | **Escolhida pelo usuário** |
| B | `claude -p --output-format stream-json` por mensagem | Simples, mas sem aprovação interativa: permissões fixas antes do turno | Descartada |
| C | API da Anthropic direto | Exige chave; perde as ferramentas do Claude Code | Descartada |

## Design

### 1. Backend `claude-code` (`app/claude_code/`)

**Turno.** Para cada mensagem, abre um `ClaudeSDKClient` com
`resume=<session_id da conversa>` (ou sem `resume` na primeira mensagem), envia
o texto, consome as mensagens até o `ResultMessage` e fecha. O `session_id`
devolvido é salvo na conversa (nova coluna `conversations.claude_session_id`,
pela migração aditiva que já existe em `database.py`).

**Fila de eventos.** O consumo do SDK roda numa tarefa em segundo plano que
coloca eventos numa `asyncio.Queue`; o gerador SSE lê dessa fila. Isso permite
emitir `authorization_required` enquanto o SDK está parado no callback de
permissão.

**Mapeamento para os eventos SSE que a interface já entende:**

| Do SDK | Para o app |
|---|---|
| `StreamEvent` com delta de texto (`include_partial_messages=True`) | `token` |
| `StreamEvent` com delta de pensamento | `reasoning` |
| `ToolUseBlock` em `AssistantMessage` | `tool_call` |
| `ToolResultBlock` em `UserMessage` | `tool_result` |
| `ResultMessage` | `done` (+ `session_id` salvo; erro vira `error`) |

O texto completo dos `TextBlock` serve só para conferência: os deltas são a
fonte do texto, para não duplicar.

**Opções do SDK:**
- `system_prompt={"type": "preset", "preset": "claude_code", "append": <persona + contexto>}`;
- `cwd` = pasta de trabalho (configurável; padrão `~/Documents`);
- `add_dirs` = diretórios autorizados, menos as pastas protegidas do app;
- `setting_sources=[]`: ignora as configurações pessoais do Claude Code (anti-objetivo 2);
- `permission_mode="default"` (ou `"acceptEdits"` se o modo turbo estiver ligado);
- `can_use_tool` = ponte de permissões (abaixo);
- `mcp_servers={"victorique": ...}`;
- `include_partial_messages=True`.

**Parar.** Se o cliente SSE desconectar, chama `client.interrupt()`, drena o
turno, salva a resposta parcial com o marcador de cancelamento que já existe e
fecha o cliente.

**Histórico.** A mensagem do usuário e a resposta final são salvas como hoje. As
ferramentas usadas vão para `tool_trace_json`: nome, entrada resumida e status.

### 2. Ponte de permissões

O callback `can_use_tool(tool_name, input, context)`:
- **Nega na hora**, sem perguntar, escrita/edição em caminho protegido
  (`path_guard.is_protected`: código do app, banco, backups).
- **Pede autorização** para o resto. Cria um pedido no `SecurityManager` com
  ferramenta, alvo (caminho, comando ou URL) e entrada; emite
  `authorization_required` e espera um `asyncio.Future`.
- `POST /api/security/authorize` reconhece pedidos do Claude Code e resolve o
  future (aprovado → `PermissionResultAllow`; recusado → `PermissionResultDeny`
  com mensagem), em vez de executar uma ferramenta do registro.
- **Expiração** (TTL atual de 120 s) ou desconexão → nega.
- Aprovação, recusa e expiração vão para `audit_logs`, como hoje.

Leituras dentro de `cwd`/`add_dirs` o próprio Claude Code libera sem perguntar.
Leituras fora disso, escrita, edição, terminal e internet caem no callback.
Comandos de exclusão no terminal (`rm`, `del`, `Remove-Item`…) também caem,
porque o terminal sempre pede no modo padrão.

### 3. Ferramentas da Victorique para o Claude (MCP no mesmo processo)

Servidor `victorique` criado com `create_sdk_mcp_server`, somente leitura e
liberado em `allowed_tools`:
- `buscar_memorias(consulta)`: memórias ativas (globais e do projeto da conversa);
- `buscar_documentos(consulta)`: busca RAG nos documentos importados, com título
  e página. Se o Ollama (embeddings) estiver offline, devolve um aviso em vez de
  erro.

### 4. Seleção de modo

- `default_backend` aceita `claude-code`. A escolha é salva na tabela `settings`
  (como o `default_model`) via `POST /api/settings`.
- `GET /api/claude-code/status` informa se o SDK está instalado, o caminho do
  CLI e o último erro conhecido (ex.: login ausente).
- **Interface:** um seletor de modo (Local / Claude Code) e, no modo Claude, um
  selo visível "Claude Code — dados enviados à Anthropic".
- `assistant_engine.chat_stream` desvia para o backend Claude quando
  `backend == "claude-code"`; os backends locais ficam como estão.

### 5. Persona Victorique

- Novo perfil `victorique`, criado pelo `init_db` se não existir. É o padrão em
  bancos novos e em bancos que só têm o perfil de fábrica; perfis criados pelo
  usuário não são alterados.
- Texto original em português. Gênia entediada, orgulhosa e de língua afiada,
  que finge desinteresse, mas resolve tudo e se importa. O personagem aparece
  no tom, nunca na qualidade:
  - nunca recusa ou enrola tarefa por tédio;
  - em erros, ações destrutivas e assuntos sérios, fica direta;
  - não inventa resultados.
- O prompt deixa de dizer "você roda localmente" e passa a informar o modo real
  (local ou Claude Code).
- Nome do app e título da janela passam a ser "Victorique".

## Testes

- Cliente falso do SDK (sem rede) para o mapeamento de eventos, a gravação e
  retomada do `session_id`, a interrupção e os erros.
- Ponte de permissões: aprovar, recusar, expirar, negar caminho protegido e
  `setting_sources=[]` presente nas opções.
- Configurações: persistência do `claude-code`; endpoint de status.
- Persona: perfil criado, padrão em banco novo, perfil do usuário preservado.
- Um teste real, manual, com o Claude Code de verdade (consome cota): conversa
  curta, uma leitura e uma escrita aprovada pela barra.

## Decisões deixadas para quem implementa (marcadas como escolhas minhas)

- Um cliente por turno com `resume`, em vez de manter clientes vivos entre
  mensagens: mais simples e robusto; o custo é ~1–3 s de partida por mensagem.
  Dá para otimizar depois.
- Modelo: o padrão do Claude Code, com um campo opcional nas configurações
  (`claude_code_model`) para escolher outro.
- Sessão que não pode ser retomada (o Claude Code guarda sessões por pasta de
  trabalho; trocar a pasta ou apagar a sessão quebra o `resume`): começa uma
  sessão nova e avisa com um evento `notice`.
- A personalidade usada no modo Claude é a da conversa (ou a padrão), igual ao
  modo local.
- Formato exato do selo e do seletor na interface, seguindo o estilo atual.
- Texto de ajuda para quando faltar login, definido depois do teste de login.
