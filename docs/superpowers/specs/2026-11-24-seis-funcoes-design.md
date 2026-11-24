# Seis funções: Pensamento Profundo, Biblioteca, Turbo, LaTeX, mini-chat e Codex

Data: 2026-11-24. Aprovado pelo usuário na conversa (o Antigravity ficou de fora).

## Intenção

O usuário quer a Victorique mais presente e mais capaz dentro do app:
ver como ela pensa (no estilo do DeepSeek, mas na voz dela), ver os arquivos
do computador como uma biblioteca onde ela vive, ligar o Modo Turbo sem
variável de ambiente, ler matemática formatada, conversar com ela direto pelo
mascote e poder usar o Codex como motor, além do Claude Code.

## Não-objetivos

- Antigravity: fica de fora. O FAQ do Google proíbe embutir o `agy` em outro
  app com conta pessoal; o usuário preferiu não usar chave de API.
- O Codex não altera arquivos: roda com sandbox somente leitura. Mudanças em
  arquivos continuam no modo Claude Code ou nos modos locais, com a barra de
  autorização.
- A Biblioteca nunca lê o conteúdo dos arquivos sozinha; mostra nome, tamanho
  e data. Ler é algo que a Victorique faz quando o usuário pede.

## Abordagens consideradas (Pensamento Profundo)

1. **Bloco de pensamento na voz dela (escolhida).** Com o botão ligado, o
   prompt pede que ela escreva primeiro `<pensamento>…</pensamento>`, em
   primeira pessoa e com a personalidade do perfil ativo, e depois a resposta.
   O servidor separa o bloco do texto e manda como eventos `reasoning`.
   Funciona em todos os modos e é raciocínio real (vem antes da resposta).
2. Raciocínio nativo do modelo (thinking do Claude, `reasoning_content` do
   Qwen). Não segue a personalidade, sai em inglês no Claude e não existe em
   todos os modelos. Continua aparecendo como "Raciocínio" quando o botão está
   desligado.
3. Gerar um "pensamento" depois da resposta. Seria encenação, não raciocínio;
   descartado.

Com o botão ligado, o raciocínio nativo é escondido para não misturar vozes.

## Design por função

### 1. Pensamento Profundo
- Botão "Pensamento profundo" na barra da caixa de mensagem (pílula com
  estado ligado/desligado), salvo na preferência `deep_thinking`.
- `ChatRequest.deep_thinking` → `assistant_engine` / `claude_code_backend`
  acrescentam a instrução de pensar em voz alta (`app/core/deep_thinking.py`).
- `ThoughtSplitter` (streaming): reconhece `<pensamento>` no começo da
  resposta (depois de espaços e marcadores `[expression:…]`), lida com tags
  partidas entre pedaços e devolve trechos de pensamento e de resposta.
- O pensamento é salvo numa coluna nova `messages.reasoning` (+
  `reasoning_seconds`) e reaparece ao reabrir a conversa. Não volta para o
  histórico enviado ao modelo.
- Interface no estilo DeepSeek: título "Pensando…" com o cachimbo animado,
  texto cinza com linha à esquerda, aberto durante o streaming; ao terminar,
  "Pensou por N s" e recolhe. Clicar alterna.

### 2. Biblioteca
- A aba antiga "Biblioteca" (documentos indexados) passa a se chamar
  "Documentos". A nova aba "Biblioteca" troca a área do chat por um salão em
  pixel art (canvas), com os sprites do mascote (`victorique.webp/json`,
  servidos por `/api/mascot/atlas*`).
- Seções = pastas. Padrão: Downloads, Documentos, Área de Trabalho, Imagens,
  Músicas, Vídeos (só as que existem). "Nova seção" vincula uma pasta
  (seletor nativo pelo pywebview quando disponível; senão, caminho digitado).
  Recusadas: pastas do sistema, as do próprio app, raízes de disco e a pasta
  do usuário inteira. Seções podem ser escondidas/desvinculadas.
- Seções ficam em `DATA_DIR/library.json`. Cada seção vira diretório
  autorizado (leitura livre; escrever/mover continua pedindo autorização).
- Livros = arquivos da seção (até 120 por estante, mais recentes primeiro),
  cor pela extensão, altura pelo tamanho. Clicar num livro mostra nome,
  tamanho, data e "Pedir para ela ler".
- Atividade: `app/library/activity.py` registra o que ela faz (ler, listar,
  mover, renomear, mandar para a Reserva, desfazer), alimentado pelo
  organizador, pelas ferramentas locais e pelos resultados de ferramentas do
  Claude Code e do Codex. A tela consome a fila: ela anda até a estante e lê
  (anim. `read`), carrega o livro até a outra estante (mover), ou até o
  carrinho da Reserva. Fora da tela, um contador aparece na aba e ela repete
  as ações quando a aba abre.
- Sem atividade, ela perambula: anda, para numa estante, lê, toma chá,
  pensa, cochila.

### 3. Modo Turbo
- Preferência `turbo_mode` (padrão: o valor de `ASSISTANT_TURBO_MODE`,
  desligado) espelhada em `settings.turbo_mode`. Interruptor em
  Configurações → Modelo e respostas, com confirmação ao ligar. Exclusões e
  o organizador continuam pedindo autorização (já é assim no código).

### 4. LaTeX
- KaTeX 0.16.x copiado para `app/ui/vendor/katex/` (js, css, fontes woff2,
  licença MIT). Sem CDN (a CSP só permite `'self'`).
- `markdown.js` separa `$$…$$`, `\[…\]`, `$…$` e `\(…\)` antes de escapar o
  texto (como faz com blocos de código), renderiza com `katex.renderToString`
  (`throwOnError:false`, `trust:false`) e devolve o texto original se falhar.
  `$` de dinheiro não vira fórmula (regra: sem espaço depois do `$` de
  abertura e antes do de fechamento, e o de fechamento não seguido de dígito).
- O prompt de sistema (todos os modos) pede LaTeX para matemática.

### 5. Mini-chat pelo mascote
- Um clique na Victorique abre/fecha uma janela pequena do pywebview
  (`/ui/mini.html`, ~380×520, sempre por cima, perto dela). Dois cliques
  continuam abrindo a janela grande; o clique simples espera o tempo de
  duplo clique do Windows para não disparar os dois.
- O mini-chat tem conversa própria ("Conversa rápida"), usa o mesmo
  `/api/chat` em streaming (mesmo modo e perfil da janela grande), mostra
  pensamento e LaTeX, e tem botão "Abrir na janela grande".
- A reação de "cutucar" continua acontecendo no clique.

### 6. Modo Codex
- Novo modo `codex` no seletor. `app/codex/backend.py` roda
  `codex exec --json --skip-git-repo-check --sandbox read-only -C <pasta>`,
  lê a mensagem pelo stdin e traduz os eventos JSONL (`thread.started`,
  `item.*` com `agent_message`, `reasoning`, `command_execution`,
  `file_change`, `mcp_tool_call`, `web_search`, `todo_list`, `error`,
  `turn.completed/failed`) para os eventos SSE da interface.
- Sessão por conversa (`conversations.codex_thread_id`), retomada com
  `codex exec resume <id>`; se falhar, começa nova com aviso.
- Persona e regras vão no começo do prompt de cada turno novo; em turnos
  retomados, só um lembrete curto.
- Status em `/api/codex/status` (instalado? caminho), com instruções de
  instalação (`npm install -g @openai/codex`, `codex login`). Não instalamos
  nada automaticamente.

## Restrições

- Tudo offline na interface (CSP `'self'`); nada de CDN.
- Testes nunca tocam o banco real (conftest isola `ASSISTANT_DATA_DIR`).
- Preview usa porta 8777 com dados isolados.

## Deixado para quem implementa

- Paleta exata das lombadas, tamanho do salão, ritmo do passeio.
- Textos de interface, desde que em pt-BR e no tom do app.
