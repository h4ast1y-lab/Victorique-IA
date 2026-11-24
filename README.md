# Victorique — assistente pessoal (Windows)

Aplicativo desktop Windows com a persona **Victorique** (inspirada na personagem de
*Gosick*: sarcástica, brilhante e direta). Funciona em dois modos, trocados no seletor
do topo da conversa:

- **Local** (llama.cpp ou Ollama): tudo roda no seu computador, offline.
- **Claude Code**: cada mensagem é processada pelo Claude Code da Anthropic, com as
  ferramentas dele (ler e editar arquivos, rodar comandos) sob a barra de autorização
  do app. Veja a [seção 12](#12-modo-claude-code).

Base: chat via Ollama e llama.cpp, personalidade configurável,
histórico, memórias explícitas, projetos independentes, RAG de documentos locais com
referências, ferramentas limitadas com autorização no backend, voz (TTS/STT) local e
interface própria. Funciona offline depois da instalação.

> Situação verificada em 21/11/2026 nesta máquina: Windows 11, Python 3.15.1,
> Ollama 0.40.16, GTX 1660 Super 6 GB, 16 GB RAM.
> - Backend padrão: `llama-cpp-server` (`llama-server.exe` em `C:\Users\Usuário\llama.cpp\`)
>   com modelo `Qwen_Qwen3.5-9B-IQ4_XS.gguf` (5,5 GB IQ4_XS, já baixado localmente).
> - Alternativa: Ollama com `qwen2.5-coder:7b` e `qwen2.5:3b`.
> - Embeddings: `nomic-embed-text` (via Ollama).
> - OCR local via Tesseract 5.4.0 (idioma `eng`; `por` não foi baixado).
> - Voz: TTS via pyttsx3/SAPI5 (disponível); STT via SpeechRecognition (arquivos de áudio;
>   microfone requer PyAudio).

---

## 1. Como iniciar

Formas suportadas:

```bat
run.bat
```

ou

```bat
.venv\Scripts\python.exe run.py
```

Variações úteis:

```bat
.venv\Scripts\python.exe run.py --browser   :: abre no navegador padrão
.venv\Scripts\python.exe run.py --server    :: só o servidor (sem janela), para testes
.venv\Scripts\python.exe run.py --no-ollama :: não tenta iniciar o Ollama
```

A janela nativa usa **pywebview/WebView2**. Se a janela falhar, o `run.py` cai para o
navegador padrão. O backend escuta apenas em `127.0.0.1:8765` (ou `ASSISTANT_PORT`).

### Pré-requisitos já presentes

- `.venv` com Python 3.15.1;
- Ollama ativo em `127.0.0.1:11434` (backend alternativo);
- modelos `qwen2.5-coder:7b` e `nomic-embed-text` (via Ollama);
- **llama.cpp** já instalado em `C:\Users\Usuário\llama.cpp\` com
  `llama-server.exe` e o modelo `models/Qwen_Qwen3.5-9B-IQ4_XS.gguf`
  (5,5 GB, já baixado localmente — **não há download automático de modelo**);
- **Tesseract-OCR** em `C:\Program Files\Tesseract-OCR` (opcional: sem ele o app continua
  funcionando, mas PDFs digitalizados sem camada de texto são recusados com aviso claro);
- **pyttsx3** e **SpeechRecognition** instalados no `.venv` (voz TTS/STT);
- PyAudio **não** está disponível para Python 3.15: o STT de microfone é limitado;
  use `/api/stt/transcribe` com arquivos de áudio.

Se precisar recriar o ambiente em outra máquina:

```bat
py -3.15 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
ollama pull qwen2.5-coder:7b
ollama pull nomic-embed-text
winget install --id UB-Mannheim.TesseractOCR   :: opcional, para OCR
:: Baixar manualmente o modelo GGUF para llama.cpp (não é baixado automaticamente)
```

Nada é baixado automaticamente pelo aplicativo. O `run.py` apenas inicia o processo
local do Ollama quando ele já está instalado. O `llama-server.exe` é iniciado
automaticamente pelo backend quando `ASSISTANT_DEFAULT_BACKEND=llama-cpp`.

---

## 2. Modelo e desempenho medidos

| Modelo | Contexto | Processamento | Velocidade medida | Observação |
|---|---:|---|---:|---|
| `qwen2.5-coder:7b` (padrão) | 4096 | 84% GPU / 16% CPU | ~16–19 tok/s | 5,2 GB; parte em CPU por causa dos 6 GB de VRAM |
| `qwen2.5:3b` | 4096 | 100% GPU | ~87 tok/s | alternativa mais rápida |

Medições reais nesta máquina:

- chat curto com `qwen2.5-coder:7b`: primeiro token entre **3,3 s e 8,6 s** (carregamento a frio),
  resposta de 41 caracteres em ~4 s;
- 1.107 tokens gerados em **79 s** (frio) a ~16 tok/s;
- RAG com 2 fontes: ~7,8 s no total;
- o relato de **167 s** não se reproduziu com o modelo padrão. Ele é compatível com
  respostas muito longas, carregamento a frio ou uso de modelo maior. Para limitar
  respostas descontroladas, `ASSISTANT_MAX_OUTPUT_TOKENS` (padrão 1024) é enviado como
  `num_predict`.

Para trocar de modelo: **Configurações → Modelo de Linguagem** (a escolha é persistida no
banco) ou `ASSISTANT_MODEL`. O modelo `qwen2.5:7b` **não está instalado** nesta máquina;
não foi baixado automaticamente.

Tool calling real medido nesta máquina: `qwen2.5-coder:7b` devolve a chamada como **JSON em
texto** (`{"name": ..., "arguments": ...}`), que o backend interpreta e valida;
`qwen2.5:3b` usa o campo nativo `tool_calls`. Se um modelo não suportar ferramentas, o app
avisa e continua a conversa sem execução automática.

---

## 3. Privacidade e funcionamento offline

- Interface sem CDN: CSS, JS, ícone e renderizador Markdown são locais.
- Nenhuma fonte, imagem ou script externo é carregado.
- Ollama e embeddings são acessados somente em `127.0.0.1`.
- A única função que acessa a internet é `search_web`, e ela **só executa após
  autorização explícita** do usuário, com o pedido mostrando a consulta e o alvo.
- O backend aplica `Content-Security-Policy` com `connect-src 'self'` e `script-src 'self'`,
  bloqueando exfiltração por scripts injetados.
- Nenhum dado pessoal é salvo automaticamente. Memórias só existem quando o usuário
  cria/edita; conversas são salvas localmente por necessidade do histórico.
- A interface não envia telemetria.
- **Exceção: modo Claude Code.** Nele, as mensagens, o contexto e os arquivos que o
  Claude ler são enviados à Anthropic. O selo laranja "Claude Code — dados enviados à
  Anthropic" fica visível no topo enquanto esse modo estiver ativo. Os modos locais
  continuam 100% offline.
- **OCR local**: PDFs sem camada de texto são renderizados com `pypdfium2` e lidos pelo
  Tesseract na própria máquina; nenhuma página é enviada para fora.
- **Voz (TTS/STT)**: síntese de fala via pyttsx3/SAPI5 (offline, Windows) e reconhecimento
  de fala via SpeechRecognition (offline, Sphinx). Nenhum áudio é enviado para nuvem.
  O microfone requer PyAudio (não disponível para Python 3.15; use arquivos de áudio via
  `/api/stt/transcribe`). A fala automática das respostas pode ser desativada com
  `ASSISTANT_TTS_SPEAK=0`.
- **llama.cpp (backend padrão)**: o servidor `llama-server.exe` local roda o modelo
  `Qwen_Qwen3.5-9B-IQ4_XS.gguf` (5,5 GB IQ4_XS) via subprocesso, expo­nendo uma API
  compatível com OpenAI em `127.0.0.1:8899`. Não há download automático de modelo —
  o GGUF já está presente em `C:\Users\Usuário\llama.cpp\models\`. O Ollama continua
  disponível como backend alternativo (`backend=ollama` ou `ASSISTANT_DEFAULT_BACKEND=ollama`).
- **Tool calling**: o modelo pode pedir ferramentas; só as ferramentas livres rodam
  automaticamente. Escrita, exclusão, criação de pastas e internet param num pedido
  de autorização no backend. Cada resposta é limitada (6 rodadas / 4 chamadas por padrão).
  No llama-server, as ferramentas usam o formato nativo (`--jinja`); o JSON em texto
  continua aceito como alternativa.
- **Modo turbo e acesso a todas as pastas são opcionais e vêm desligados.**
  `ASSISTANT_TURBO_MODE=1` faz escrita e internet rodarem sem aprovação (exclusões
  **sempre** pedem aprovação). `ASSISTANT_ALLOW_ALL_DIRS=1` libera leitura em qualquer
  pasta; sem ele, só os diretórios autorizados são acessíveis. Um não liga o outro.
- **Raciocínio do modelo**: o `reasoning_content` do Qwen 3.5 chega como evento
  `reasoning`, aparece recolhido na interface e não é salvo, falado nem reenviado ao modelo.
- **Isolamento por projeto**: conversas, memórias e documentos são filtrados pelo projeto
  ativo. Um chat sem projeto usa apenas documentos globais — nunca recupera conteúdo de
  outro projeto (verificado por teste automatizado e no E2E).

---

## 4. Onde ficam os dados

Tudo por padrão em `data/`:

| Caminho | Conteúdo |
|---|---|
| `data/assistant.db` | histórico, memórias, projetos, personalidades, índice RAG, auditoria |
| `data/documents/` | cópias dos documentos importados |
| `data/backups/` | snapshots do banco |
| `data/falas.md` | banco de falas espontâneas da Victorique (editável; criado na primeira vez) |
| `data/vida_propria.json` | estado da vida própria: últimas falas, limites, silêncio |

Variáveis de ambiente para instalação portátil/testes:

- `ASSISTANT_DATA_DIR` — diretório de dados;
- `ASSISTANT_DB_PATH` — caminho do banco;
- `ASSISTANT_PORT` — porta;
- `ASSISTANT_MODEL` — modelo padrão;
- `ASSISTANT_EMBEDDING_MODEL` — modelo de embeddings;
- `ASSISTANT_NUM_CTX` — contexto do Ollama;
- `ASSISTANT_MAX_OUTPUT_TOKENS` — limite de tokens por resposta;
- `ASSISTANT_AUTHORIZED_DIRS` — diretórios autorizados, separados por `;`;
- `ASSISTANT_TOOL_CALLING` — `0` desativa tool calling;
- `ASSISTANT_TURBO_MODE` — `1` dispensa aprovação para escrita e internet (padrão `0`);
- `ASSISTANT_ALLOW_ALL_DIRS` — `1` libera acesso a qualquer pasta (padrão `0`);
- `ASSISTANT_MAX_TOOL_ROUNDS` / `ASSISTANT_MAX_TOOL_CALLS` — limites do laço de ferramentas;
- `ASSISTANT_OCR` — `0` desativa o OCR;
- `ASSISTANT_OCR_LANG` — idiomas do Tesseract (ex.: `por+eng`; só funciona se os dados
  de idioma estiverem instalados);
- `ASSISTANT_OCR_DPI` / `ASSISTANT_OCR_MIN_CHARS` — renderização e limiar de texto;
- `TESSERACT_CMD` — caminho alternativo para `tesseract.exe`.
- `ASSISTANT_TTS` — `0` desativa a síntese de fala;
- `ASSISTANT_STT` — `0` desativa o reconhecimento de fala;
- `ASSISTANT_TTS_SPEAK` — `0` desativa a fala automática das respostas;
- `ASSISTANT_DEFAULT_BACKEND` — `ollama` ou `llama-cpp` (padrão: `llama-cpp`);
- `ASSISTANT_LLAMA_CPP_AUTO_START` — `0` desativa o auto-start do `llama-server`;
- `LLAMA_CPP_DIR` — diretório da instalação llama.cpp (padrão: `C:\Users\Usuário\llama.cpp`);
- `LLAMA_CPP_SERVER_EXE` — caminho alternativo para `llama-server.exe`;
- `LLAMA_CPP_MODEL_PATH` — caminho do modelo GGUF (padrão: `models/Qwen_Qwen3.5-9B-IQ4_XS.gguf`);
- `LLAMA_CPP_HOST` / `LLAMA_CPP_PORT` — endereço do servidor llama-server;
- `LLAMA_CPP_N_CTX` / `LLAMA_CPP_N_GPU_LAYERS` — contexto e camadas GPU do llama.cpp.

O `llama-server` sobe em segundo plano (a API responde enquanto o modelo carrega;
`/api/llama-cpp-server/status` mostra `starting`), é encerrado junto com o app e grava
a saída em `data/llama-server.log`.

**Nunca apague `data/assistant.db` sem backup.** Faça backup antes de qualquer
manutenção.

---

## 5. Backup e restauração

Pela interface: **Configurações → Backup do banco de dados → Criar backup agora**.
Também é possível baixar e restaurar pela própria tela.

Pela API:

```bat
curl -X POST http://127.0.0.1:8765/api/backup -H "Content-Type: application/json" -d "{\"label\":\"manual\"}"
curl http://127.0.0.1:8765/api/backups
curl -X POST http://127.0.0.1:8765/api/backup/restore -H "Content-Type: application/json" -d "{\"name\":\"assistant-....db\",\"confirm\":true}"
```

- O backup usa a API online do SQLite e é verificado com `PRAGMA integrity_check`.
- A restauração exige `confirm=true` e cria automaticamente um backup `pre-restore`.
- A fila de autorizações pendentes é limpa após restaurar.
- Backups não são apagados automaticamente (política conservadora).

---

## 6. Segurança e autorizações

### Camadas implementadas

- **Backend decide**: `POST /api/tools/execute` ignora o campo `authorized` enviado pelo
  cliente. Ferramentas protegidas sempre geram um pedido pendente.
- **Vínculo à ação e aos parâmetros**: o pedido guarda ferramenta, alvo e hash do payload.
  A aprovação executa exatamente o payload armazenado no servidor.
- **Uso único e expiração**: cada `action_id` vale uma vez, por 120 s (configurável por
  `authorization_ttl_seconds`). Reutilização, expiração e adulteração são recusadas.
- **Auditoria**: pedidos, aprovações, recusas, expirações e execuções vão para
  `audit_logs` no SQLite.
- **Caminhos**: validação imediata antes da operação, com `resolve()` para seguir
  symlinks/junctions; bloqueio de `..`, caminhos absolutos/UNC fora da whitelist.
- **Caminhos protegidos**: código do app, `.venv`, banco, `data/` e backups não podem
  ser escritos nem movidos por ferramentas. Pastas do Windows (`C:\Windows`, `Program Files`,
  `ProgramData`, `AppData`) também ficam fora de alcance para escrita; só a pasta temporária
  do sistema é exceção.
- **Nada é apagado**: `delete_file` manda o item para a Reserva (`_Quarentena/<data-hora>/`)
  dentro da pasta autorizada. Mover (`move_files`), renomear (`rename_file`) e descartar
  pedem aprovação sempre, mesmo no modo turbo; a barra de autorização mostra o plano
  origem → destino. Um lote é validado inteiro antes (destino existente nunca é
  sobrescrito) e, se falhar no meio, o que já foi movido volta. Cada lote fica em
  `data/operations.json` e pode ser desfeito no painel **Organizador**.
- **Origem/Host**: requisições com `Origin` externo recebem 403; `Host` diferente de
  localhost/127.0.0.1 recebe 400 (mitiga DNS rebinding).
- **Conteúdo não confiável**: documentos/páginas são tratados como dados; o prompt
  instrui o modelo a ignorar comandos embutidos. O Markdown do modelo é escapado antes
  de renderizar (sem HTML arbitrário).
- **Tool calling não amplia permissões**: o modelo só escolhe *qual* ferramenta chamar.
  O backend valida nome, parâmetros obrigatórios, caminhos e categoria; ferramentas
  protegidas continuam criando pedido pendente, e a aprovação executa apenas o payload
  guardado no servidor. Chamadas repetidas idênticas na mesma rodada são ignoradas.

### Limitações de segurança (honestas)

- A API local **não tem login/token**. Qualquer processo do próprio usuário pode chamá-la.
  A proteção é contra páginas web (Origin/Host/CSP), não contra malware local.
- Subprocessos não são usados para executar comandos do modelo. Ainda assim, o app roda
  com os privilégios do usuário; não é um sandbox de sistema operacional.
- A validação de caminho tem uma janela teórica de TOCTOU entre validação e operação;
  symlinks/junctions são resolvidos imediatamente antes, o que reduz o risco.
- A extração de PDF usa a camada de texto quando existe. OCR entra apenas em páginas com
  pouco texto; a qualidade depende da digitalização. Nesta máquina só o idioma `eng` do
  Tesseract está instalado — documentos em português podem ter erros de reconhecimento até
  que `por.traineddata` seja adicionado (não baixado automaticamente).
- Tool calling depende do modelo: o padrão emite JSON textual, interpretado por um parser
  restrito (só nomes registrados e chaves conhecidas). Modelos pequenos podem ocasionalmente
  responder em prosa em vez de chamar a ferramenta; nesse caso nada é executado.
- RAG usa similaridade de cosseno local; não há garantia de que toda resposta esteja
  fundamentada. A UI mostra as fontes e o system prompt proíbe inventar citações, mas
  isso não é uma verificação formal.

---

## 7. Funcionalidades

| Funcionalidade | Estado |
|---|---|
| Chat local com streaming SSE | implementado; testado automaticamente e manualmente (real) |
| Cancelamento de geração | implementado (AbortController + fechamento do stream Ollama + resposta parcial salva); testado |
| Personalidade configurável | implementado; testado (edição sem duplicar perfil) |
| Histórico e persistência | implementado; testado após reinício |
| Memórias explícitas (global/projeto), editar/desativar/excluir | implementado; testado |
| Casos (antes Projetos) independentes, com arquivamento, + exclusão em cascata | implementado; testado (inclui remoção do arquivo) |
| Organizador: mover em lote, renomear, Reserva e Desfazer | implementado; testado automaticamente e no navegador |
| Victorique em miniatura andando pela área de trabalho (anda, lê, cochila, fuma o cachimbo, fala pelo balão; arrastar, clique, dois cliques, menu) | implementado (seção 14); substitui o antigo retrato com clipes |
| Expressões e gestos escolhidos pelo modelo (`[expression:ID]`, `[gesture:ID]`, ocultos no texto) | implementado nos dois modos; protocolo adaptado do Victorique-IA-2 |
| RAG PDF/TXT/MD com documento/página | implementado; testado com embeddings reais |
| Isolamento por projeto (conversas, memórias, documentos, RAG) | implementado; testado automaticamente e no E2E |
| Referências às fontes | implementado; testado |
| Ferramentas de arquivos, cálculo e sistema | implementado; testado |
| Tool-calling autônomo pelo modelo (ferramentas livres) | implementado; testado automaticamente (parser JSON, `tool_calls` nativo, limite de rodadas, fallback) e no E2E real com `qwen2.5-coder:7b` e `qwen2.5:3b` |
| Autorizações no backend | implementado; testado (aprovar/recusar/expirar/replay) |
| Internet somente com autorização | implementado; testado que não há chamada antes da aprovação |
| OCR de PDF digitalizado no upload/RAG | implementado; testado automaticamente (PDF só-imagem) e no E2E com citação de página; limitado aos idiomas instalados no Tesseract |
| Interface desktop própria | implementado (WebView2); página e handlers verificados; janela nativa não automatizada |
| Backup/restauração | implementado; testado |
| Voz TTS (texto → fala) | implementado via pyttsx3/SAPI5 (offline); testado; fala automática das respostas |
| Voz STT (fala → texto) | implementado via SpeechRecognition/Sphinx (offline); arquivos de áudio via `/api/stt/transcribe`; microfone requer PyAudio (não disponível no Python 3.15) |
| Backend llama.cpp (servidor local) | implementado via `llama-server.exe` + `Qwen_Qwen3.5-9B-IQ4_XS.gguf` (5,5 GB); E2E real passou (`144 × 15 = 2160`); Ollama continua como alternativa |
| Ollama como backend alternativo | implementado; `qwen2.5-coder:7b` e `qwen2.5:3b` disponíveis |
| Vida própria: tédio (propõe um Caso) e comentários avulsos, com Silêncio e não perturbar | implementado; testado automaticamente, no navegador e com o Claude Code real (seção 13) |

---

## 8. API principal

- `GET /api/health`, `GET /api/models`, `GET/POST /api/settings`
- `POST /api/chat` (SSE: `meta`, `sources`, `reasoning`, `token`, `tool_call`,
  `tool_result`, `authorization_required`, `notice`, `error`, `done`)
- `GET/POST /api/conversations`, `GET /api/conversations/search`,
  `GET /api/conversations/{id}/messages`, `PUT/DELETE`, `GET .../export`
- `GET/POST /api/personalities`, `DELETE /api/personalities/{id}`
- `GET/POST /api/memories`, `PUT/DELETE /api/memories/{id}`
- `GET/POST /api/projects`, `PUT/DELETE /api/projects/{id}`
- `GET /api/documents`, `POST /api/documents/upload`, `DELETE /api/documents/{id}`
- `GET /api/security/pending`, `POST /api/security/authorize`
- `POST /api/tools/execute`, `GET /api/tools/list`
- `POST /api/backup`, `GET /api/backups`, `GET /api/backups/{name}`,
  `POST /api/backup/restore`
- `GET /api/tts/status`, `POST /api/tts/speak`
- `GET /api/stt/status`, `POST /api/stt/listen`, `POST /api/stt/transcribe`
- `GET /api/llama-cpp-server/status`, `POST /api/llama-cpp-server/start`,
  `POST /api/llama-cpp-server/stop`
- `POST /api/life/tick`, `GET /api/life/status`, `POST /api/life/silence`,
  `POST /api/life/resume`, `POST /api/life/test` (vida própria, seção 13)
- `GET /api/avatar/manifest`, `GET /api/mascot/status`, `POST /api/mascot/signal`,
  `POST /api/mascot/say`, `POST /api/mascot/reply`, `POST /api/mascot/command`
  (Victorique na área de trabalho, seção 14)
- `GET /api/ping` (responde na hora, sem checar backends; usado pelo `run.py`)
- `GET /api/claude-code/status` (SDK instalado, caminho do `claude.exe`, pasta de
  trabalho, modelo e último erro)
- `GET/POST /api/settings` também lê e grava `default_backend` (`llama-cpp`,
  `llama-cpp-server`, `ollama` ou `claude-code`) e lista `available_backends`.
  `POST /api/chat` aceita `backend` para escolher o modo de uma mensagem.

O evento SSE `meta` chega antes dos tokens e já contém `conversation_id`; o evento
`done` também o envia. Assim, uma conversa nova não se perde se a geração for cancelada.

---

## 9. Testes

```bat
.venv\Scripts\python.exe -m pytest -q
```

- Os testes usam um diretório temporário (`ASSISTANT_DATA_DIR`) e **não tocam** em
  `data/assistant.db`.
- Cobertura atual: banco/memória/projetos, personalidade, path guard (incluindo junction),
  autorizações (cliente não executa, replay, expiração, recusa), caminhos protegidos,
  Origin/Host, ausência de rede antes da aprovação, upload/RAG, SSE, cancelamento,
  backup/restauração, isolamento por projeto, handlers e recursos offline da UI,
  tool calling (JSON textual, `tool_calls` nativo, ferramenta protegida pendente,
  limite de rodadas, fallback sem suporte), OCR de PDF só-imagem, voz (TTS/STT) e
  servidor llama.cpp.
- Resultado desta rodada: **71 testes passando** (os testes marcados `live_ollama`
  requerem o Ollama rodando e são pulados quando ele está offline).
- A suíte roda com os padrões de fábrica (turbo e acesso total desligados).
- E2E real com `llama-cpp-server` + `Qwen_Qwen3.5-9B-IQ4_XS.gguf`: chat funcionou
  corretamente (`144 × 15 = 2160`).
- O banco real `data/assistant.db` foi comparado com o backup pré-auditoria: schema e
  todas as linhas **logicamente idênticos** (0 conversas/mensagens/memórias/projetos/
  documentos; apenas a personalidade padrão). Nenhum dado do usuário foi alterado.
- A janela nativa WebView2 e os cliques da interface foram verificados por carregamento
  headless do DOM e checagem de handlers; **não** houve automação de cliques na janela.

---

## 10. Estrutura

```
run.py, run.bat
app/
  config.py, main.py
  core/       assistant.py, context_builder.py, personality.py, backup.py
  models/     ollama_client.py, llama_cpp_client.py, llama_cpp_server_client.py
  voice/      __init__.py   (TTS pyttsx3/SAPI5 + STT SpeechRecognition/Sphinx)
  memory/     database.py, conversation_store.py, memory_store.py, project_store.py
  life/       observer.py, policy.py, folders.py, lines.py, generator.py, service.py
  mascot/     sprite.py, behavior.py, balloon.py, win32.py, desktop.py, bus.py, launcher.py
  rag/        document_loader.py, text_splitter.py, vector_store.py
  security/   path_guard.py, permissions.py
  tools/      registry.py, file_tools.py, system_tools.py, web_search.py
  ui/         index.html, css/style.css, js/app.js, js/markdown.js, favicon.svg
tests/
data/         assistant.db, documents/, backups/  (não versionar)
```

---

## 11. Observações de manutenção

- `python-multipart` é obrigatório para o upload multipart do FastAPI. Ele estava ausente
  e impedia o app de iniciar; foi instalado no `.venv` e adicionado ao `requirements.txt`.
- OCR usa `pypdfium2` + `pytesseract` + `Pillow` (licenças permissivas) e o Tesseract
  instalado em `C:\Program Files\Tesseract-OCR`; **não** foi usado PyMuPDF (AGPL).
- Voz usa `pyttsx3` (TTS) e `SpeechRecognition` (STT) — ambos off-line; PyAudio não
  está disponível para Python 3.15, então o STT de microfone é limitado.
- llama.cpp usa o executável `llama-server.exe` já compilado em
  `C:\Users\Usuário\llama.cpp\` com o modelo GGUF local (não há download automático).
  Se precisar reinstalar a biblioteca Python `llama-cpp-python`, note que não há wheel
  pré-compilada para Python 3.15 neste ambiente.
- Git 2.56 foi instalado e o repositório local foi inicializado (commit inicial
  `000b195`). Não há remoto configurado; `.venv`, `data/` e caches ficam fora do controle
  de versão.
- O console do Windows pode exibir acentos quebrados dependendo da fonte/codepage; o
  `run.bat` ativa UTF-8 e o `run.py` reconfigura os streams.
- Antes de atualizar Ollama, modelos, Python ou dependências, faça backup e teste
  compatibilidade. Não há migração destrutiva automática.

---

## 12. Modo Claude Code

A Victorique pode usar o **Claude Code** em vez do modelo local. O app usa o
`claude-agent-sdk` (`requirements.txt`), que já traz o `claude.exe`; não é preciso
instalar o Claude Code à parte.

### Login (uma vez)

O modo usa o login do Claude Code desta máquina (assinatura Pro/Max ou conta da
Anthropic) e consome a sua cota. Para entrar:

```bat
claude auth login
```

Sem o Claude Code instalado, use o executável que vem com o app:

```bat
".venv\Lib\site-packages\claude_agent_sdk\_bundled\claude.exe" auth login
```

Para conferir: `.venv\Scripts\python.exe scripts\claude_login_check.py` (gasta uma
mensagem curta). Se o login faltar ou expirar, a conversa mostra um erro em português
com o comando acima.

### Como funciona

- Escolha **Claude Code** no seletor do topo. A escolha fica salva.
- Cada conversa tem a própria sessão do Claude Code (`conversations.claude_session_id`)
  e é retomada na mensagem seguinte. Se a sessão não puder ser retomada (pasta de
  trabalho trocada, sessão apagada), o app começa outra e avisa.
- A persona, o projeto ativo e a instrução de responder em pt-BR vão como acréscimo ao
  prompt do Claude Code. As memórias e os documentos indexados ficam disponíveis por
  duas ferramentas só de leitura: `buscar_memorias` e `buscar_documentos`.
- As configurações pessoais do Claude Code (`~/.claude`, `CLAUDE.md`, hooks) são
  ignoradas (`setting_sources=[]`).
- Texto, raciocínio, ferramentas e resultados aparecem em tempo real, como no modo
  local. Parar a geração interrompe o Claude Code e salva a resposta parcial.

### Permissões

- Leituras dentro da pasta de trabalho e das pastas autorizadas rodam sem perguntar.
- Escritas, edições, comandos que alteram algo e acesso à internet aparecem na
  **barra de autorização** com a ferramenta e o alvo. Recusar, ou deixar expirar
  (120 s), nega a ação. Comandos que o Claude Code classifica como só leitura (por
  exemplo `ls` na pasta de trabalho) rodam sem perguntar.
- Escrever no código do app, no banco ou nos backups é **negado sem perguntar**.
- **Modo turbo** (`ASSISTANT_TURBO_MODE=1`): escritas e edições são aprovadas
  automaticamente (como o `acceptEdits` do Claude Code), mas comandos e internet
  continuam pedindo, e os caminhos protegidos continuam negados.
- Toda decisão vai para `audit_logs`.

### Configuração

| Variável | Padrão | Uso |
|---|---|---|
| `ASSISTANT_DEFAULT_BACKEND` | `llama-cpp` | Modo inicial (`claude-code` para começar no Claude) |
| `ASSISTANT_CLAUDE_WORKSPACE` | `~/Documents` | Pasta de trabalho do Claude Code |
| `ASSISTANT_CLAUDE_MODEL` | vazio | Modelo do Claude Code; vazio usa o padrão dele |

As pastas autorizadas (`ASSISTANT_AUTHORIZED_DIRS`) entram como pastas extras, menos as
pastas protegidas do app.

### Verificação

- Testes automatizados com um cliente falso do SDK: eventos, sessões, retomada,
  erros de login, cancelamento, opções travadas e a ponte de permissões.
- Verificado no app real em 23/11/2026: seletor e selo funcionando; uma mensagem no
  modo Claude Code chega ao `claude.exe` do pacote e, com o login expirado, mostra a
  ajuda de login em 2,7 s.
- Teste real com login válido em 23/11/2026 (app com dados à parte, Claude Opus 5.5):
  | Pedido | Resultado |
  |---|---|
  | "Oi, quem é você?" | Resposta no tom da Victorique, 8 s |
  | Listar a pasta Documentos | `ls` rodou sem pedir autorização, 10 s |
  | Criar `victorique_teste.txt`, aprovando na barra | Pedido `Write` na barra; aprovado; arquivo criado |
  | Criar `victorique_teste2.txt`, recusando | Negado; nada criado; a Victorique explicou e não tentou de novo |
  O arquivo de teste foi apagado depois.

---

## 13. Vida própria

A Victorique puxa assunto sozinha, de vez em quando. Tudo fica em **Configurações → Vida
própria**, e o ícone de lua na barra lateral (ou o menu dela na área de trabalho) liga o
**não perturbar**.

- **Tédio:** depois de 20 a 45 minutos (sorteado; configurável) sem você falar com ela,
  e com você no computador, ela propõe um enigma, uma pergunta para investigar ou uma
  curiosidade ligada aos Casos abertos e ao que você contou sobre si. **Investigar** cria
  o Caso, seleciona-o e deixa a pergunta pronta no campo de mensagem.
- **Comentários avulsos:** hora tardia (23:30 às 5:00, uma vez por noite), pasta
  bagunçada (25+ arquivos soltos de 5+ tipos numa pasta autorizada ou subpasta direta;
  a mesma pasta no máximo uma vez por semana), organização concluída (3+ arquivos) e
  retorno depois de 45+ minutos longe do PC ou de 6+ horas com o app fechado.
- **Limites:** no máximo 2 falas por hora e 15 minutos entre falas (configuráveis). Um
  minuto de espera depois de uma tentativa sem fala. O teste das Configurações ignora
  os limites e não conta para eles.
- **Ela fica calada** com o não perturbar ligado, durante o «Silêncio» (2 horas, pelo
  balão), com você longe do PC (5+ min sem mexer no teclado ou no mouse), com a janela
  minimizada ou as configurações abertas, enquanto você digita ou ela responde, com
  qualquer app em tela cheia (vídeo, jogo, apresentação) e com os apps da lista de
  silêncio na frente (Teams, Zoom, PowerPoint, OBS e Roblox por padrão).
- **As falas:** com **Variar as falas com o modelo** ligado, o modo atual escreve uma
  fala nova (no Claude Code, numa chamada sem ferramenta nenhuma; leva de 2 a 10 s e
  consome um pouco da cota). Se o modelo estiver desligado, falhar, repetir uma fala
  recente ou quebrar as regras, ela usa o banco `data/falas.md`, que você pode editar.
  O modelo também pode escolher ficar calada. As últimas 12 falas ficam guardadas para
  não se repetirem.
- **Privacidade:** ela comenta só nomes de pastas, contagens e extensões. O conteúdo dos
  arquivos nunca é lido, e o caminho completo das pastas não vai para o modelo. Do
  Windows, o app lê apenas há quanto tempo o teclado e o mouse estão parados, e o nome
  do programa na frente e se ele está em tela cheia. Títulos de janela e a tela não são
  lidos.
- **Voz:** **Falar em voz alta** lê as falas com a voz do app (desligado por padrão).

Como funciona: a interface pergunta ao servidor a cada 20 s (`POST /api/life/tick`) e
envia o próprio estado (digitando, respondendo, janela visível). Com a Victorique na
área de trabalho, a fala vai para o balão dela (e a janela escondida não a cala, já que
o balão continua à vista); sem ela, o balão aparece na própria página. O servidor
(`app/life/`) decide tudo antes de chamar qualquer modelo: `observer.py` lê os sinais do
Windows, `policy.py` aplica os portões e os gatilhos, `generator.py` escreve a fala e
`service.py` a entrega num pedido seguinte, conferindo os portões de novo.

Verificação em 23/11/2026: 50 testes automatizados (`tests/test_life.py`); no navegador,
a pasta bagunçada de teste gerou o comentário, o tédio de teste abriu o Caso com a
pergunta no campo, e o «Silêncio» e o não perturbar bloquearam as falas; com o Claude
Code real, o tédio saiu ligado a um Caso aberto (10 s, primeira chamada) e o comentário
da pasta levou 2 s.

---

## 14. Victorique na área de trabalho

No aplicativo de desktop (`run.bat`), a Victorique em miniatura vive sobre a barra de
tarefas: passeia, para, senta para ler e vira as páginas, fuma o cachimbo, toma chá,
ajeita o cabelo e cochila quando você some. Ela substitui o antigo retrato com clipes
da barra lateral; ali ficou só uma linha com o estado dela e a lua do não perturbar.

- **Com o mouse:** arraste-a para qualquer lugar (ela esperneia e cai de volta na barra
  de tarefas do monitor onde for solta); um clique dá uma reação; dois cliques abrem a
  conversa; o botão direito abre o menu (abrir a conversa, ficar parada, Silêncio de
  2 horas, não perturbar, esconder, encerrar o assistente).
- **Estados:** pensando, ela para e acende o cachimbo; falando, mexe a boca; ouvindo,
  inclina a cabeça; erro, fica preocupada; sem interação (minutos configuráveis),
  senta e dorme com «z z z».
- **Expressões do modelo:** nos dois modos, a resposta final pode começar com
  marcadores ocultos `[expression:ID]` e `[gesture:ID]` (IDs fixos, ver
  `GET /api/avatar/manifest`). Eles saem do texto antes de salvar, mostrar ou ler em voz
  alta e mudam o rosto dela por 22 s. No modo local, um marcador antes de uma chamada de
  ferramenta em JSON não atrapalha a detecção da ferramenta.
- **Balão:** as falas da vida própria (com «Aceitar o Caso» e «Silêncio») aparecem
  acima dela, mesmo com a janela fechada. Se uma resposta termina com a conversa fora da
  frente, ela mostra o começo da resposta com «Abrir a conversa».
- **Fechar a janela** só esconde a conversa (configurável): o assistente continua
  rodando com ela na tela. Para sair de vez, use «Encerrar o assistente» no menu dela.
- **Tela cheia:** com um jogo, vídeo ou apresentação em tela cheia na frente, ela some
  e volta depois.
- **Configurações → Na área de trabalho:** mostrar ou esconder, tamanho (90 a 240 px),
  passear, avisar respostas, sumir em tela cheia e o comportamento ao fechar a janela.
  Para desligar no arranque, use `ASSISTANT_MASCOT=0`.

Como funciona: ela é desenhada em código com o Pillow (`app/mascot/sprite.py`, sem
imagens) e mostrada numa janela Win32 em camadas com alfa por pixel
(`app/mascot/win32.py`). Os pixels transparentes deixam os cliques passarem para o que
estiver atrás. Uma janela transparente do pywebview foi testada e pinta o fundo de
cinza no WebView2, por isso não foi usada. O comportamento (`behavior.py`) é lógica
pura; `desktop.py` junta tudo na thread da janela, e `bus.py` liga a API da conversa a
ela no mesmo processo. No navegador (`--browser`) ela não aparece e os balões ficam na
página.

Origem: o protocolo de expressões e gestos (`app/core/avatar_protocol.py`), o parser
que tira os marcadores do fluxo e o ritmo de piscadas e gestos vêm do projeto irmão
[Victorique-IA-2](https://github.com/Nyzius/Victorique-IA-2), feito sobre esta mesma
base. O retrato em CSS de lá não foi usado: a figura aqui é outra, de corpo inteiro.

Verificação em 23/11/2026: testes automatizados (`tests/test_mascot.py`,
`tests/test_avatar_protocol.py` e dois casos novos em `tests/test_claude_backend.py`).
Na área de trabalho real: a transparência e os cliques atravessando os pixels vazios, a
caminhada, o cachimbo, a queda depois de arrastada e o balão. No app completo
(`run.py`): a fala chegou ao balão, fechar a janela só a escondeu, e «Aceitar o Caso»
no balão reabriu a conversa com o Caso criado.
