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

ou o atalho `Victorique.exe` (sem janela de console, com o ícone dela). Ele
não vem pronto: gere uma vez na pasta do projeto e deixe-o lá, ao lado do
`run.py` (a saída do app vai para `data\victorique.log`):

```bat
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\python.exe scripts\build_launcher.py
```

A foto da Victorique (sidebar, mensagens, ícone da janela) pode ser trocada em
Configurações → Aparência; a enviada fica em `data\avatar\`.

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

Ao abrir o `run.bat`, a Victorique reinicia o Ollama local e o llama.cpp mesmo
quando outro modo de conversa está selecionado. Isso interrompe os pedidos em
andamento da execução anterior. O inicializador aguarda a API do Ollama responder
e o llama.cpp carrega o modelo em segundo plano. A opção `--no-ollama` e a
configuração `ASSISTANT_LLAMA_CPP_AUTO_START=0` desativam a inicialização dos
respectivos servidores. Nenhum modelo é baixado automaticamente.

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
- **Spotify (seção 20)**: para ela comentar a música, o app lê só o que toca no Spotify
  (título, artista e álbum), pelo título da janela do Spotify, pelos controles de mídia
  do Windows ou pela ponte do Spicetify, que fala só com `127.0.0.1`. Nenhuma outra
  janela tem o título lido. No modo Claude Code, o nome da música vai no pedido da fala.
- **Isolamento por projeto**: conversas, memórias e documentos são filtrados pelo projeto
  ativo. Um chat sem projeto usa apenas documentos globais — nunca recupera conteúdo de
  outro projeto (verificado por teste automatizado e no E2E).

---

## 4. Onde ficam os dados

Tudo por padrão em `data/`:

| Caminho | Conteúdo |
|---|---|
| `data/assistant.db` | histórico, memórias, projetos, personalidades, índice RAG, auditoria |
| `data/documents/` | cópias dos documentos importados (aba Documentos) |
| `data/chat_files/` | imagens e documentos anexados no chat (só da conversa; somem com ela) |
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
a saída em `data/llama-server.log`. Cada vez que a IA local é ligada (ao abrir o app no
modo llama.cpp ou ao trocar para ele), um `llama-server` que tenha ficado aberto na
porta é encerrado e um novo sobe no lugar, sem pedidos antigos. Ao trocar para outro
modo, o servidor é desligado e libera a memória.

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
| Victorique em miniatura, em pixel art, na área de trabalho (anda na barra de tarefas e por cima das janelas abertas, escala, pula, senta na beirada, lê, toma chá, cochila, fala pelo balão; arrastar pela mão, arremessar, clique, dois cliques, menu) | implementado (seção 14); substitui o antigo retrato com clipes |
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
| Pensamento profundo: ela pensa em voz alta, na voz dela, antes de responder (como no DeepSeek) | implementado nos três modos; testado automaticamente e no navegador (seção 15) |
| Botão do Modo Turbo nas Configurações, com confirmação e selo na caixa de mensagem | implementado; testado automaticamente e no navegador (seção 15) |
| Matemática em LaTeX (KaTeX local, sem internet) | implementado; testado automaticamente (Node) e no navegador (seção 15) |
| Conversa rápida: um clique na mascote abre uma janelinha de chat ao lado dela | implementado; testado automaticamente e a página no navegador; o clique na mascote real não foi automatizado (seção 16) |
| Biblioteca: salão em pixel art, uma estante por pasta e um livro por arquivo; ela encena o que faz nos arquivos | implementado; testado automaticamente e no navegador, com uma ação real do organizador (seção 17) |
| Uma Victorique só: a mascote passa por uma portinha e vai trabalhar na Biblioteca; mover, renomear e mandar para a Reserva à mão no salão | implementado; testado automaticamente e no navegador; a porta na área de trabalho de verdade ainda não foi vista (seção 17) |
| Modo Codex (CLI da OpenAI), somente leitura | implementado; testado com um processo falso; não testado com o Codex real (seção 18) |
| Anexar imagens e documentos no chat (clipe, colar ou arrastar); ficam só na conversa, nunca em Documentos | implementado; testado automaticamente e no navegador (seção 19) |
| Ler e editar Word, Excel, PowerPoint, PDF e CSV (o original vai para a Reserva) | implementado; testado automaticamente (seção 19) |

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
- `GET /api/codex/status` (Codex instalado, comando, pasta de trabalho, modelo,
  último erro e os passos de instalação)
- `GET/POST /api/library/sections`, `DELETE /api/library/sections/{id}`,
  `GET /api/library/sections/{id}/books`, `GET /api/library/activity?since=N` (com
  `presence`: onde ela está), `POST /api/library/pick-folder` (Biblioteca, seção 17)
- `POST /api/library/presence` (`hall_open`, `enter`, `left_hall`) e
  `POST /api/library/books/move|rename|reserve` (edição à mão no salão, seção 17)
- `GET /api/mascot/atlas` e `GET /api/mascot/atlas.json` (sprites dela para a
  Biblioteca), `POST /api/mascot/open-conversation` (a conversa rápida passa a
  conversa para a janela grande)
- `GET/POST /api/settings` também lê e grava `default_backend` (`llama-cpp`,
  `llama-cpp-server`, `ollama`, `claude-code` ou `codex`) e lista `available_backends`.
  `POST /api/chat` aceita `backend` para escolher o modo de uma mensagem e
  `deep_thinking` para o Pensamento profundo. O evento `reasoning` com `voice: true`
  é o pensamento dela; o `done` traz `reasoning_seconds`.

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
- Resultado da rodada de 24/11/2026: **383 testes passando e 3 pulados** (os testes
  marcados `live_ollama` requerem o Ollama rodando e são pulados quando ele está offline).
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
  core/       assistant.py, context_builder.py, personality.py, backup.py, deep_thinking.py
  models/     ollama_client.py, llama_cpp_client.py, llama_cpp_server_client.py
  voice/      __init__.py   (TTS pyttsx3/SAPI5 + STT SpeechRecognition/Sphinx)
  memory/     database.py, conversation_store.py, memory_store.py, project_store.py
  life/       observer.py, policy.py, folders.py, lines.py, generator.py, service.py
  library/    sections.py (seções = pastas), activity.py (o que ela faz nos arquivos),
              presence.py (onde ela está), editing.py (edição à mão no salão)
  claude_code/ backend.py, options.py, permissions.py, victorique_tools.py
  codex/      backend.py  (modo Codex: `codex exec --json`, somente leitura)
  mascot/     sprite.py, behavior.py, surfaces.py, balloon.py, win32.py, desktop.py, bus.py,
              launcher.py, assets/ (victorique.webp + victorique.json; source/ com as 20 folhas)
  spotify/    layout.py (bordas dentro do Spotify), bridge.py + victorique.js (ponte do
              Spicetify), spicetify.py (instalador), nowplaying.py, track.py, watcher.py
  rag/        document_loader.py, text_splitter.py, vector_store.py
  security/   path_guard.py, permissions.py
  tools/      registry.py, file_tools.py, system_tools.py, web_search.py
  ui/         index.html, mini.html, css/ (style.css, mini.css),
              js/ (app.js, markdown.js, thought.js, library.js, mini.js), vendor/katex/
scripts/      build_mascot_sprites.py  (gera o atlas da mascote a partir das folhas),
              install_spicetify.py  (instala a ponte do Spotify)
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
- **Modo turbo** (interruptor em Configurações → Modelo e respostas, ou
  `ASSISTANT_TURBO_MODE=1`): escritas e edições são aprovadas
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

No aplicativo de desktop (`run.bat`), a Victorique em miniatura, em pixel art, vive
na área de trabalho: anda sobre a barra de tarefas e por cima das janelas abertas, vira
para os lados, lê e fecha o livro, toma chá, olha em volta, pensa, espia pela borda da
tela, senta no chão ou na beirada de uma janela com as pernas para fora e cochila
quando você some. Ela substitui o antigo retrato com clipes da barra lateral; ali ficou
só uma linha com o estado dela e a lua do não perturbar.

- **Por cima das janelas:** ela anda na borda de cima das janelas abertas que não estão
  maximizadas. Escala a lateral de uma janela que desce até perto da barra de tarefas,
  pula para uma janela um pouco mais alta, desce pulando e senta na beirada. Se a janela
  é arrastada, ela vai junto; se a janela fecha, é minimizada ou fica coberta por outra,
  ela cai no que estiver embaixo. Só vale a parte visível da borda: uma janela na frente
  divide o caminho. Ficam de fora as janelas maximizadas, sem título, de ferramenta e as
  que deixam o clique passar. Desligue em Configurações → «Subir nas janelas abertas».
  Exceção: no Spotify, mesmo maximizado, ela anda por dentro (seção 20).
- **Com o mouse:** arraste-a pela mão: ela fica pendurada na ponta da seta do Windows,
  que continua visível. A pose só muda quando o mouse se mexe: parado, ela fica quieta;
  puxada devagar, se inclina; puxada rápido, voa atrás da mão, sempre do lado oposto ao
  puxão (puxe para a esquerda e ela balança para a direita). Quando a mão para, ela volta
  balançando para baixo dela. Sacudida de um lado para o outro, ao pousar ela bate o pé
  de birra. Solta, ela cai do lado em que estava pendurada, no que estiver embaixo: a
  borda de uma janela ou a barra de tarefas do monitor. Um movimento rápido ao soltar a
  arremessa. Um clique dá
  uma reação e abre a conversa rápida ao lado dela (seção 16); dois cliques abrem a
  janela grande; o botão direito abre o menu (abrir a conversa, conversa rápida, ficar
  parada, Silêncio de 2 horas, não perturbar, esconder, encerrar o assistente).
- **Estados:** pensando, ela para com ar pensativo; falando, mexe a boca; ouvindo, fica
  atenta; erro, fica confusa; sem interação (minutos configuráveis), senta e dorme com
  «z z z». Ao acordar, boceja e esfrega os olhos. De vez em quando boceja ou suspira de
  braços cruzados.
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
  passear, subir nas janelas abertas, avisar respostas, sumir em tela cheia e o
  comportamento ao fechar a janela.
  Para desligar no arranque, use `ASSISTANT_MASCOT=0`.

Como funciona: a arte são 27 folhas de sprites (`app/mascot/assets/source/`, uma por
animação: andar, humores, falar, piscar, sentar, sentada, virar, levantar, arrastada,
pular, cair, escalar, beirada, espiar, chá, ler, fechar o livro, olhar, pensar,
cochilar e, desde 24/11/2026, feliz, apontar, confusa, surpresa, suspirar, despertar e
birra). As expressões `happy`, `surprised`, `annoyed`, `deduction` e `confused` usam
essas folhas novas. O script `scripts/build_mascot_sprites.py` recorta os quadros. Ele tira o
fundo pelo alfa ou pelo branco e as sombras do chão pela cor, e iguala a escala pela
altura dela de pé. Em cada quadro ele marca o ponto de apoio: as solas, o assento na
beirada, a mão quando arrastada (o cursor desenhado nessas folhas é apagado) ou a borda
da tela quando espia.
O resultado é o atlas `app/mascot/assets/victorique.webp` + `victorique.json` (WebP com
alfa sem perda, cerca de 1,7 MB). Para gerar de novo, rode
`.venv\Scripts\python.exe scripts\build_mascot_sprites.py` (cerca de 15 s;
`--debug PASTA` grava folhas de conferência). Duas folhas (arrastada e cair) têm um
traço um pouco diferente, com tiara em vez da touca, e foram usadas como vieram.

`sprite.py` lê o atlas, escala, espelha as vistas de lado conforme a direção e desenha
os «z». A lista de janelas abertas vem do Win32 (`EnumWindows`, da frente para trás,
com o retângulo visível pelo DWM) a cada 0,4 s, e a janela sob os pés dela é relida a
cada quadro. `surfaces.py` transforma isso nos trechos onde ela pode andar. Ela é
mostrada numa janela Win32 em camadas com alfa por pixel (`app/mascot/win32.py`). Os
pixels transparentes deixam os cliques passarem para o que estiver atrás. Uma janela transparente do pywebview foi testada e pinta o fundo de
cinza no WebView2, por isso não foi usada. O comportamento (`behavior.py`) é lógica
pura; `desktop.py` junta tudo na thread da janela, e `bus.py` liga a API da conversa a
ela no mesmo processo. No navegador (`--browser`) ela não aparece e os balões ficam na
página.

Origem: o protocolo de expressões e gestos (`app/core/avatar_protocol.py`), o parser
que tira os marcadores do fluxo e o ritmo de piscadas e gestos vêm do projeto irmão
[Victorique-IA-2](https://github.com/Nyzius/Victorique-IA-2), feito sobre esta mesma
base. O retrato em CSS de lá não foi usado. As folhas de sprites foram fornecidas pelo
dono do projeto; a primeira versão da miniatura era desenhada em código com o Pillow.

Verificação em 23/11/2026: testes automatizados (`tests/test_mascot.py`,
`tests/test_avatar_protocol.py` e dois casos novos em `tests/test_claude_backend.py`).
Na área de trabalho real: a transparência e os cliques atravessando os pixels vazios, a
caminhada, a queda depois de arrastada e o balão. Com os sprites e as janelas
(`tests/test_mascot.py` com 42 testes: atlas, bordas visíveis, pouso, carona na janela
arrastada, queda quando ela fecha ou é coberta, escalada, pulo e arremesso), numa
janela de teste no desktop real: ela pousou na barra de título, foi junto quando a
janela foi arrastada, sentou na beirada, escalou a lateral e caiu na barra de tarefas
quando a janela fechou. No app completo
(`run.py`): a fala chegou ao balão, fechar a janela só a escondeu, e «Aceitar o Caso»
no balão reabriu a conversa com o Caso criado.

---

## 15. Pensamento profundo, Modo Turbo e matemática

**Pensamento profundo.** O botão com a lâmpada, ao lado do perfil na caixa de mensagem,
liga e desliga. Ligado, ela pensa em voz alta antes de responder, no próprio tom, num
bloco `<pensamento>` que o app separa da resposta, do jeito que o DeepSeek mostra o
raciocínio. Durante a resposta aparece «Pensando…» com o texto chegando; no fim, a caixa
fecha e mostra «Pensou por N s», e um clique a abre de novo. O pensamento fica salvo
com a mensagem (`messages.reasoning`) e volta ao reabrir a conversa. Vale nos modos
local, Claude Code e Codex. Com ele ligado, o raciocínio interno do modelo fica
escondido; a opção «Mostrar raciocínio» das Configurações só afeta esse raciocínio
interno.

O pedido ao modelo (`DEEP_THINKING_INSTRUCTIONS`, em `app/core/deep_thinking.py`) descreve o
bloco como uma simulação dos pensamentos da personagem, escrita junto com a mensagem.
Uma versão anterior pedia que o modelo "raciocinasse de verdade" no bloco, e no modo Claude
Code o Sonnet 5.5 e o Opus 5.5 recusavam a mensagem com o erro `[reasoning_extraction]`.

**Modo Turbo.** Configurações → Modelo e respostas → «Modo Turbo». Ligar pede
confirmação; ligado, aparece o selo «Turbo» na caixa de mensagem. No modo local, escrever
arquivos e usar a internet deixam de pedir aprovação; no Claude Code, só escritas e
edições (seção 12). Excluir continua pedindo, e os caminhos protegidos continuam negados.
No Codex não muda nada, porque ele só lê. A escolha fica salva nas preferências.

**Matemática.** As respostas com fórmulas usam LaTeX: `$...$` dentro da frase e `$$...$$`
(ou `\[...\]`) em linha própria; `\(...\)` também vale. O desenho é feito pelo KaTeX
0.16.11, que vem junto em `app/ui/vendor/katex/` (licença MIT), sem nenhuma conexão.
Valores como R$ 10 continuam como texto, e fórmulas dentro de código não são
desenhadas. Uma fórmula inválida aparece como código, sem quebrar a mensagem.

---

## 16. Conversa rápida pela mascote

Um clique na Victorique da área de trabalho abre uma janelinha de conversa (380 × 540,
sempre por cima) ao lado dela; outro clique a fecha. O clique espera o tempo de duplo
clique do Windows, para que dois cliques continuem abrindo a janela grande. A conversa
rápida usa o mesmo modo, perfil, Pensamento profundo e LaTeX da janela grande, e tem a
própria conversa («Conversa rápida», guardada em `mini_conversation_id`). O botão de
expandir leva a conversa para a janela grande; Esc fecha a janelinha. O menu do botão
direito também tem «Conversa rápida».

---

## 17. Biblioteca

A aba **Biblioteca** é um salão em pixel art onde a Victorique passeia. Cada seção é uma
pasta do computador e vira uma estante com uma plaquinha de latão; cada arquivo é um
livro, com a cor pelo tipo (PDF vermelho, planilhas verdes, imagens azul-esverdeado…) e a
altura pelo tamanho. A antiga aba de documentos indexados agora se chama **Documentos**.

- **Seções padrão:** Downloads, Documentos, Área de Trabalho, Imagens, Músicas e Vídeos,
  as que existirem (pelas pastas conhecidas do Windows, seguindo o OneDrive). Elas não
  são criadas com `ASSISTANT_LIBRARY_DEFAULTS=0` nem quando `ASSISTANT_AUTHORIZED_DIRS`
  limita as pastas.
- **Novas seções:** «Nova seção» na barra lateral, com o caminho ou «Escolher…» (seletor
  de pastas do aplicativo). Ficam de fora: uma unidade inteira, a pasta do usuário
  inteira, pastas do Windows, de programas e do AppData e as pastas do próprio app. Até
  24 seções. Desvincular (dois cliques no ×) não mexe na pasta.
- **Permissões:** cada seção vira uma pasta autorizada. Ela lê e lista à vontade lá;
  criar, mover e excluir continuam pedindo aprovação.
- **No salão:** as estantes mostram os 120 arquivos mais recentes de cada pasta (só nome,
  tamanho e data; o conteúdo não é lido). Passar o mouse mostra o nome; clicar abre um
  cartão com estante, tamanho, data, caminho e «Pedir para ela ler». Clique nela para uma
  reação. Arraste, use a roda do mouse ou as setas para olhar o salão; a câmera para
  enquanto o mouse está sobre ele. A janela mostra o céu da hora do dia.
- **O que ela faz vira cena:** mover, renomear, mandar para a Reserva e desfazer (pelo
  organizador), ler, listar e escrever (ferramentas locais, do Claude Code e leituras
  do Codex). Ela vai até a estante e lê, consulta, escreve ou leva o livro para outra
  estante ou para o carrinho da Reserva. Com a aba fechada, as ações viram um contador
  na aba, e ela as encena quando você abre (até 14). Sem nada para fazer, ela passeia,
  lê, toma chá, pensa e cochila.
- **Onde fica:** as seções em `data/library.json`; as ações só na memória (as últimas 200).

### Uma Victorique só

A mascote da área de trabalho e a do salão são a mesma. O servidor sabe onde ela está
(`app/library/presence.py`): na área de trabalho, entrando, na Biblioteca ou saindo.

- **Ela vai à Biblioteca** quando você abre a aba, quando mexe em arquivos das estantes a
  pedido (na conversa ou na conversa rápida) e pelo item «Ir para a Biblioteca» do menu
  dela, que também abre a janela nessa aba. Ler um arquivo fora das estantes não a tira
  da área de trabalho.
- **A porta:** na área de trabalho, ela anda até a ponta de onde está, uma portinha
  aparece, ela passa e some. No salão, ela entra pela porta da esquerda. Na volta é o
  contrário, e ela reaparece onde saiu (no chão, se a janela onde estava fechou).
- **Com a aba fechada:** ela trabalha fora de vista e um balão «Fui à Biblioteca cuidar dos
  seus livros.» aparece onde ficava a porta; «Assistir» abre a janela na aba Biblioteca.
  A janela nunca abre sozinha.
- **A volta:** ao sair da aba (ou esconder a janela), 30 s sem trabalho fora de vista e
  5 min parada com a aba aberta. Com ela fora, o salão mostra «Chamar a Victorique».
- **Sem a mascote** (modo navegador, desligada, em tela cheia): ela some ou aparece na
  hora, sem a caminhada até a porta.

### Edição à mão no salão

Arraste um livro para outra estante (mover) ou para o carrinho da Reserva. O botão
direito num livro abre «Renomear…», «Mover para…», «Mandar para a Reserva» e «Pedir
para ela ler»; o cartão do livro tem os mesmos botões, para quem usa o teclado (a Reserva
pelo cartão pede dois cliques). Ela faz a cena de carregar o livro.

- Sem a barra de aprovação, porque é uma ação sua, mas sempre pelo organizador: cada
  edição vira um lote em **Organizador**, com Desfazer, e fica no registro de auditoria.
- Só arquivos do primeiro nível de uma estante; nada é apagado (a Reserva é o descarte) e
  o conteúdo dos arquivos não é editado.
- Nome que já existe, nome inválido no Windows ou livro que sumiu da pasta: um aviso com
  o motivo, e o livro volta ao lugar.

Verificação em 24/11/2026: `tests/test_library.py` (11 testes) e a página no navegador
com três pastas de teste: estantes, cartão do livro, formulário com erro e uma ação real
do organizador desfeita pelo servidor, com ela carregando o PDF de volta à estante certa.
Depois, `tests/test_library_presence.py`, `tests/test_library_editing.py` e os testes da
porta em `tests/test_mascot.py`; no navegador: ela entrando pela porta, um livro
arrastado entre estantes e outro até o carrinho, renomear pelo cartão, a Reserva pelo
botão direito, a saída ao trocar de aba e «Chamar a Victorique». A caminhada até a porta
na área de trabalho de verdade não foi vista (não dá para testar daqui).

---

## 18. Modo Codex

A Victorique também pode responder pelo **Codex**, o CLI da OpenAI. O app não instala
nada: o Codex é seu.

### Instalação e login (uma vez)

```bat
npm install -g @openai/codex
codex login
```

O `npm` vem com o Node.js (https://nodejs.org). O `codex login` entra com a sua conta do
ChatGPT ou com uma chave da API da OpenAI e consome a sua cota. Sem o Codex, a conversa
mostra esses passos, e `GET /api/codex/status` diz se ele foi encontrado.

### Como funciona

- Escolha **Codex** no seletor de modo. O selo passa a dizer «Dados enviados à OpenAI».
- Cada mensagem roda `codex exec --json --skip-git-repo-check --sandbox read-only -C <pasta> -`
  com o texto pelo stdin. Os eventos JSONL viram os mesmos eventos da interface: texto,
  raciocínio, comandos (como «Shell»), buscas na web, ferramentas MCP, plano e erros.
- **Somente leitura:** o Codex pode ler e listar arquivos para responder, mas não altera
  nada. Pedidos de mover, renomear ou apagar ficam para o modo local ou o Claude Code,
  que pedem a sua aprovação.
- Cada conversa tem a própria sessão do Codex (`conversations.codex_thread_id`),
  retomada com `codex exec resume`. Se a sessão não puder ser retomada, o app começa
  outra com um resumo das últimas 12 mensagens e avisa.
- A persona, o caso ativo, os marcadores de expressão e a regra de responder em pt-BR
  vão no começo de cada sessão nova; nas retomadas vai só um lembrete curto.
- As leituras do Codex aparecem na Biblioteca. Parar a geração encerra o processo e
  salva a resposta parcial.

### Configuração

| Variável | Padrão | Uso |
|---|---|---|
| `ASSISTANT_CODEX_WORKSPACE` | a pasta do Claude Code (`~/Documents`) | Pasta onde o Codex trabalha |
| `ASSISTANT_CODEX_MODEL` | vazio | Modelo do Codex; também em Configurações → «Modelo do Codex» |
| `ASSISTANT_CODEX_PATH` | vazio | Caminho do executável, se o `codex` não estiver no PATH |

### Verificação

`tests/test_codex_backend.py` (7 testes, com um processo falso): o comando só leitura e
a retomada, a tradução dos eventos, o Codex ausente, a retomada que falha, o login
inválido, o Pensamento profundo e a ligação com o app. No navegador, em 24/11/2026: o
seletor, o selo e a ajuda de instalação no chat. O Codex não estava instalado nesta
máquina, então ainda não houve um teste com o Codex real.

---

## 19. Anexos no chat e documentos de escritório

### Anexos

- O clipe da caixa de mensagem anexa **imagens** (PNG, JPG, WEBP, GIF, BMP) e
  **documentos** (PDF, Word, Excel, PowerPoint, CSV, EPUB e textos) à mensagem. Também
  dá para colar um print (Ctrl+V) ou arrastar arquivos para a caixa. Até 10 por
  mensagem; uma mensagem pode ter só anexos.
- Os anexos **ficam só no chat**: vão para `data/chat_files/<id>/`, não entram na aba
  Documentos nem no índice de busca. Apagar a conversa apaga os anexos dela; anexos
  enviados e nunca mandados somem depois de um dia. Para pôr um arquivo na busca de
  documentos, use a aba Documentos.
- Na conversa, as imagens aparecem como miniaturas (clique para ampliar) e os documentos
  como etiquetas (clique para abrir no programa do Windows).
- **Claude Code:** as imagens vão como imagens (reduzidas a no máximo 1568 px) e ela as
  vê; dos documentos vão o caminho e uma prévia do texto, e ela lê o resto com
  `ler_documento`.
- **Codex:** as imagens vão com `--image`; documentos como caminho e prévia.
- **Ollama:** as imagens vão no campo `images` (só modelos com visão as entendem);
  llama.cpp recebe só a prévia dos documentos e avisa que não vê imagens.

### Ler e editar documentos

- `read_file` (modo local) e `ler_documento` (Claude Code) leem Word, Excel (.xlsx,
  .xlsm e o antigo .xls), PowerPoint, CSV, PDF e EPUB em partes: seções do Word,
  planilhas, slides ou blocos de linhas. No Word, `[¶n]` numera os parágrafos; nas
  planilhas aparecem as colunas em letras, as linhas numeradas e as fórmulas. Formatos
  antigos (.doc, .ppt) e do LibreOffice dão uma mensagem pedindo para salvar no formato
  novo.
- Edição (sempre com aprovação; no Modo Turbo, sem perguntar):
  - `edit_word` / `editar_word`: trocar texto (mesmo partido em pedaços de formatação,
    mantendo o negrito e o itálico), inserir, reescrever ou remover parágrafos,
    acrescentar títulos e tabelas;
  - `edit_spreadsheet` / `editar_planilha`: preencher células e fórmulas, acrescentar,
    inserir e remover linhas, criar, renomear e remover planilhas; CSV mantém o
    separador; um .xls vira .xlsx;
  - `edit_pdf` / `editar_pdf`: extrair, reordenar, remover e girar páginas, juntar PDFs,
    metadados. O texto dentro do PDF não é editável: para reescrever, ela cria um .docx;
  - `create_document` / `criar_documento`: .docx e .pptx a partir de texto no estilo
    Markdown (títulos, listas, tabelas), .xlsx e .csv a partir de linhas, .md e .txt.
- **Nada se perde:** antes de alterar um arquivo, o original é copiado para a Reserva
  (`_Quarentena/<data>/…` da pasta autorizada). A gravação é atômica. Anexos do chat
  ficam na pasta protegida do app e nunca são alterados: a versão editada vai para
  `Documentos\Victorique\<nome> (editado).<ext>`. Uma planilha com gráficos ou tabelas
  dinâmicas avisa que o editor pode não preservá-los.
- Bibliotecas: `python-docx`, `openpyxl`, `python-pptx`, `xlrd` e `pypdf`
  (`pip install -r requirements.txt`).

### Verificação

`tests/test_office.py` (13 testes: leitura de cada formato, edições com formatação
preservada, Reserva, arquivos protegidos, aprovação e Modo Turbo, ferramentas do Claude
Code) e `tests/test_chat_attachments.py` (12 testes: os anexos não vão para Documentos,
envios ruins recusados, mensagem só com anexos, exclusão com a conversa, o que cada
motor recebe). No navegador, em 24/11/2026: colar um print e um CSV, as etiquetas na
caixa, o envio, as miniaturas e o visualizador, reabrir a conversa e apagá-la. Com o
Claude Code real: ela leu o texto e a cor de fundo de uma imagem anexada.

---

## 20. Victorique no Spotify

Com o Spotify aberto, ela anda por dentro dele e comenta a música que toca.

- **Por dentro da janela:** ela sobe na barra do player e na borda de cima dos painéis
  (abaixo da barra de navegação), pula entre eles e desce. Vale **também com o Spotify
  maximizado**, a única janela maximizada em que ela entra (no maximizado, a borda de
  cima dos painéis fica colada no topo da tela e não tem espaço para ela; sobram a barra
  do player e o que a ponte informar). Arrastada e solta sobre o Spotify, ela cai na
  primeira borda abaixo. Uma janela na frente divide o caminho, como nas outras.
- **Com a ponte do Spicetify:** ela também pisa nas abas e nos filtros, nas capas e nas
  primeiras faixas das listas, nas posições exatas, e acompanha a página quando você
  rola. Instale em Configurações → Na área de trabalho → «Instalar a ponte do
  Spicetify» (o Spotify reinicia) ou com
  `.venv\Scripts\python.exe scripts\install_spicetify.py`. Precisa do
  [Spicetify](https://spicetify.app). Se o Spotify atualizou e o Spicetify responde que
  o cliente voltou ao original («stock state»), o botão roda `spicetify backup apply`
  sozinho, como o próprio Spicetify pede (e como faz o `spicetify auto`). Depois de
  instalada, o mesmo botão vira «Reaplicar», e «Remover a ponte» a tira do Spotify. Sem a
  ponte, ou se ela parar de responder por 6 s, valem as bordas pelo formato padrão do
  Spotify (64 px de navegação no topo, 88 px de player embaixo, medidos no 1.3.10).
- **Spotify da Microsoft Store:** o Spicetify o suporta só em parte. Aberto pelo menu
  Iniciar, ele vem sem as modificações (sem a ponte). Para abri-lo com a ponte, use
  «Reaplicar» ou o comando `spicetify auto`; pedir uma música no chat também o reabre com
  a ponte (seção 21). Cada atualização do Spotify pela Store o
  devolve ao original, e então é preciso reaplicar. Sem a ponte, ela continua andando na
  barra do player e lendo a música pelos controles de mídia do Windows.
- **Comentários:** depois de 20 s ouvindo uma faixa nova (pular não conta), ela pode
  comentar a escolha no balão. Passa pelos mesmos portões e limites da vida própria
  (seção 13): silêncio, não perturbar, intervalo mínimo, limite por hora e apps calados.
  A mesma faixa não é comentada de novo na mesma sessão. O modelo só recebe título,
  artista e álbum e não pode citar letra. O banco de falas ganhou a seção `## musica`
  (marcadores `{musica}`, `{artista}`, `{album}`). Um `data/falas.md` criado antes dessa
  seção a recebe uma vez, no fim do arquivo, para você editar. Quando falta um marcador
  (um podcast sem artista, por exemplo), ela prefere as falas que não dependem dele.
- **De onde vem a música:** a ponte; os controles de mídia do Windows (SMTC, com os pacotes
  `winrt` opcionais do `requirements.txt`; funciona também com o Spotify escondido na
  bandeja, sabe se está pausado e o álbum, e ignora anúncios); ou o título da janela do
  Spotify («Artista - Música»; pausado, ele vira «Spotify Premium»).
- **Configurações:** «Andar pelo Spotify» (Na área de trabalho; depende de «Subir nas
  janelas abertas») e «Comentar as músicas do Spotify» (Vida própria; depende de
  «Comentários avulsos», mas não de andar pelo Spotify). O cartão de estado diz se a ponte
  está conectada, instalada mas sem contato, ou instalada com outra porta ou chave (aí é
  só reinstalar), se o Spotify está aberto, o que toca, se o Spicetify aponta para uma
  pasta antiga do Spotify e se o Spotify é o da Store. «Testar uma fala agora» tem a opção
  «Música no Spotify». `GET /api/spotify/status?detail=true` mostra os retângulos que a
  ponte mandou, para depurar as bordas.

Como funciona: `win32.top_windows` marca as janelas do `Spotify.exe`. Para elas,
`spotify/layout.py` devolve bordas (`surfaces.Ledge`), que `surfaces.window_ledges`
transforma em superfícies com a chave `w<hwnd>/<nome>`. Por isso ela continua sabendo em
que janela está, vai junto quando a janela é arrastada e cai quando ela fecha. A ponte
(`spotify/victorique.js`) roda dentro do Spotify e manda, por WebSocket para
`127.0.0.1:8765/api/spotify/ws` (ou POST em `/api/spotify/bridge`, se não houver
WebSocket), o tamanho da página, os retângulos dos elementos em pixels CSS e a faixa.
`layout.py` converte isso para a tela pela proporção entre a página e a janela, o que
já cobre DPI e zoom. Se a proporção não bate (o miniplayer, por exemplo), valem as bordas
padrão. Segurança: a ponte só é aceita com o token aleatório de
`data/spotify_bridge.json`, gravado na extensão ao instalar. A origem
`https://xpui.app.spotify.com` só é liberada nesse endpoint, e cada relatório tem até
64 KB e 48 elementos. `spotify/watcher.py` lê a faixa a cada 2 s e entrega o momento
`musica` à vida própria.

Como a ponte acha as coisas: o Spotify 1.3.x trocou as classes `.Root__*` por nomes
embaralhados que mudam a cada versão. A ponte procura a grade CSS da janela pelos nomes
das áreas (`global-nav`, `left-sidebar`, `main-view`, `right-sidebar`,
`now-playing-bar`), que não mudam, e os itens pelos identificadores dos componentes
(`data-encore-id` `card`, `chip` e `listRow`, `data-testid="tracklist-row"` e
`role="tab"`). As classes antigas continuam como reserva para versões velhas. Capas de um
carrossel que passam da borda do painel são cortadas nela (as escondidas somem), para ela
não pisar em capas invisíveis. Quando o app está fechado, a ponte espera cada vez mais
entre as tentativas (até 1 min). O instalador roda o Spicetify sem abrir janela de console,
lê a saída em UTF-8 sem os códigos de cor e nunca fica preso numa pergunta dele.

Verificação em 26/11/2026: `tests/test_spotify.py` (34 testes: título da janela, bordas
no Spotify maximizado e flutuante, janela na frente, conversão das posições da ponte
com DPI de 120 %, pouso numa capa e carona na rolagem, a mascote no player bar e as
preferências, token e relatórios ruins (inclusive token com acentos e corpo grande demais),
a faixa contada só depois de 20 s e uma vez, comentários sem depender de andar pelo
Spotify, SMTC com anúncios, ordem das fontes, instalador com um Spicetify falso (backup
refeito, cores, sem console, remoção, estado), falas do banco e seção nova num banco antigo,
endpoints HTTP e WebSocket com origem e token). No Windows real, com o Spotify 1.3.10 da
Microsoft Store e o Spicetify 2.45.3: a janela foi reconhecida (maximizada) e a música foi
lida pelo SMTC numa thread. A ponte foi instalada pelo endpoint, depois de
`spicetify backup apply`, e conectou por WebSocket. Ela mandou painéis, a barra do player
(y 946, 88 px), abas, capas e faixas. As bordas calculadas, desenhadas sobre uma captura
da tela, caíram no topo de cada elemento. Não visto: a mascote andando sobre o Spotify
na tela.

## 21. Pedir coisas do Spotify pelos chats

No chat principal ou na conversa rápida da mascote, peça em português: «toca Bohemian
Rhapsody», «põe minha playlist de estudos», «toca as minhas curtidas», «coloca Under
Pressure na fila», «pausa», «próxima», «volume 30», «liga o aleatório», «repete essa»,
«curte essa música», «o que está tocando?». Ela busca no próprio Spotify, toca o melhor
resultado, diz o que ficou tocando e guarda outras opções, caso a escolha não fosse essa.

- **Ferramentas:** `spotify_tocar` (música, artista, álbum, playlist, podcast, episódio ou
  as Músicas Curtidas; as playlists da sua biblioteca vêm antes da busca; aceita link ou
  URI do Spotify), `spotify_fila`, `spotify_buscar` (opções sem tocar),
  `spotify_controlar` (pausar, continuar, próxima, anterior, volume, aleatório, repetir,
  curtir, descurtir) e `spotify_tocando` (faixa, álbum, posição, volume, aleatório,
  repetição, se está curtida e as próximas). Controlar música não pede aprovação.
- **Em que modo:** Claude Code (ferramentas MCP `mcp__victorique__spotify_*`, liberadas
  sem pergunta) e modo local (llama.cpp/Ollama, pelo registro de ferramentas). O Codex não
  recebe ferramentas do app: nele ela diz que o Claude Code ou o modo local fazem isso.
- **Precisa da ponte do Spicetify** (seção 20), que agora também recebe pedidos. Se o
  Spotify estiver fechado, ou se for o da Microsoft Store aberto pelo menu Iniciar (sem a
  ponte), um pedido para tocar reabre o Spotify pelo Spicetify (`spicetify restart`) e
  espera a ponte conectar, até 25 s. Isso só acontece quando a ponte instalada é a deste
  app (mesma porta e chave). Sem ponte nenhuma, pausar, continuar e pular ainda funcionam
  pelos controles de mídia do Windows. Um pedido para tocar abre a busca no Spotify para
  você escolher, e ela diz como ligar a ponte.
- **Comentários:** a música que ela pôs a seu pedido não vira comentário avulso depois.

Como funciona: o WebSocket da ponte agora vai e volta. `bridge.command()` manda
`{"cmd", "id", "args"}`; a extensão faz o pedido e responde `{"reply": id, "ok", "result"
| "error"}`, com o mesmo token dos relatórios. A resposta tem prazo, e o pedido falha
limpo se o Spotify fechar no meio. Só o WebSocket leva pedidos (o POST de reserva só manda
relatórios). Dentro do Spotify, a extensão usa as APIs do próprio cliente expostas pelo
Spicetify (`Spicetify.Platform.PlayerAPI`, `PlaybackAPI`, `LibraryAPI`, `RootlistAPI` e o
`GraphQLLoader`). Elas existem desde a abertura; o `Spicetify.Player` só fica completo
depois, e com o Spotify recém-aberto isso pode levar mais de 40 s. A busca usa as
consultas da página de busca, se ela já foi aberta, ou a da caixa de busca
(`searchSuggestions`), que existe desde o início. A Web API (`api.spotify.com`) fica de
reserva, porque costuma responder 429 para o token do cliente. Toda a lógica em Python
fica em `spotify/control.py` (tipos, links, volume em palavras, mensagens) e
`spotify/tools.py` (nomes, descrições e esquemas, os mesmos nos dois modos).

O instalador também entende o aviso do Spicetify depois de atualizar o próprio Spicetify
(«Preprocessed Spotify data is outdated»): roda `spicetify restore backup apply`, como ele
pede.

Verificação em 26/11/2026, com o Spicetify atualizado para 2.46.7 e o Spotify 1.3.10 da
Store. Testes automáticos em `tests/test_spotify_control.py` (18 testes):
- o canal de pedidos: resposta, erro, prazo, fechamento no meio, token, a conexão mais
  nova vence e chamada de outra thread;
- tipos, links e volume em palavras;
- tocar, com e sem ponte, inclusive o Spotify fechado sendo aberto;
- controles pela ponte e pelo Windows, e o que está tocando;
- as ferramentas no registro e no servidor MCP;
- um pedido de ponta a ponta pelo WebSocket do app;
- `restore backup apply`, a detecção do Spotify da Store sem a ponte e os controles de
  mídia do Windows.

A extensão rodou no Node contra um Spicetify falso: todos os pedidos, inclusive o caso do
Spotify recém-aberto. No Spotify real, com uma cópia do app na porta 8777:
- com o Spotify fechado, `spotify_tocar` («Clair de Lune Debussy») o abriu pelo Spicetify
  e tocou em 8,5 s;
- busca de música, artista, playlist e álbum, fila, próxima, anterior, volume, pausar e
  continuar funcionaram;
- num turno real do Claude Code, «Toca Bohemian Rhapsody do Queen no Spotify» chamou
  `spotify_tocar` e a música tocou.

Não testado ao vivo: o modo local (sem modelo instalado aqui) e curtir/descurtir (para
não mexer na sua biblioteca).
