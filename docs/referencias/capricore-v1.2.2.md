# Estudo: CapriCore v1.2.2

Fonte: <https://github.com/CapriChooms/CapriCore/releases/tag/v1.2.2> (commit `828f272`).
Estudado em 23/11/2026 para levar ao Victorique o que serve.

## O que é

Companheira de desktop para Windows ("Capri"): Electron + Node.js (cerca de 1.100 arquivos
`.mjs`), llama.cpp/Ollama local ou API compatível com OpenAI, voz local, memória, ferramentas
com permissão, avatar animado que anda pela tela, iniciativa (comentários espontâneos),
xadrez, Spotify, Discord, chamadas.

## Licença: por que nada foi copiado literalmente

- O código do CapriCore é **GPL-3.0-only**. Copiar ou traduzir trechos para o Victorique
  obrigaria o Victorique (repositório público) a ser distribuído também sob GPL-3.0.
- Sprites, ícone, música e voz da Capri têm um aviso de licença separado e não são
  cobertos pela GPL ("The code license grants no rights to those materials").
- Por isso, o que entrou no Victorique foi **reescrito do zero em Python** a partir das ideias
  e das regras de projeto descritas na documentação, sem copiar o código. Ideias e números
  de configuração não são protegidos; texto e código são.

## Já incorporado (23/11/2026)

| Ideia do CapriCore | No Victorique |
| --- | --- |
| `dialogue-style`: detecta aberturas e frases repetidas nas últimas 12 respostas e avisa o modelo **sem citar** as frases (citar reforça o bordão) | `app/core/dialogue_style.py`, aplicado no modo Local (`context_builder`) e no Claude Code (`build_append_prompt`). Extra nosso: detecta também a mesma *ação em itálico* repetida. Testes: `tests/test_dialogue_style.py` |
| `filesystem/permissions`: recusa caminhos de rede (UNC), nomes de dispositivo (CON, NUL, COM1…), fluxos alternativos (`arquivo:fluxo`), nomes com ponto/espaço no fim e arquivos com hard link | `check_windows_path_syntax` e `ensure_not_hardlinked` em `app/security/path_guard.py`. UNC é recusado sempre: abrir `\\servidor\pasta` pode mandar a credencial do Windows para outra máquina. Testes: `tests/test_path_syntax.py` |

## Pendências que valem a pena (por ordem de valor)

### 1. Vida própria: tédio e comentários avulsos (spec, seção 8)

O `initiative-*` do CapriCore resolve exatamente a seção 8 da spec. Regras de projeto a
reaproveitar (todas deterministas, decididas **antes** de chamar o modelo):

- **Desligado por padrão.** Presets: *Ocasional* (mín. 6 min entre falas, máx. 10/h) e
  *Conversador* (mín. 2 min, máx. 30/h). Limite próprio de 1 a 30/h; o espaçamento mínimo é
  `1 h / limite`. A spec pede no máximo 2 intervenções/h para o tédio.
- **Orçamento persistente**: horários das últimas falas na janela de 1 h, última tentativa,
  últimos 8 textos ditos e categorias dispensadas sobrevivem a reinício (JSON em `data/`).
- **Portões** (qualquer um bloqueia, e a UI mostra o motivo): desligado, candidato expirado,
  tela bloqueada, suspensão, usuário ausente, tela de configurações aberta, modelo ocupado,
  falando, usuário digitando, horário de silêncio (padrão 23:00–09:00), categoria dispensada,
  app em **tela cheia**, app excluído (Discord, Teams, Zoom, PowerPoint, OBS por padrão).
- **Tentativa falha ou silêncio**: 1 min de espera. Depois de uma resposta normal, 45 s de
  silêncio. Primeiro comentário espontâneo só após uns 45–70 s.
- **Sem fila de atraso**: o candidato expira em 15–20 s e é descartado se a janela em foco mudar.
- **Ficar calada é uma resposta válida.** O modelo devolve JSON `{speak, text}` e pode escolher
  silêncio. Máx. 25 palavras, sem ferramentas, sem pergunta que exija resposta imediata.
- **Contra a repetição**: os últimos comentários entram no prompt como "proibido repetir",
  não como exemplo. Um filtro final descarta falas que mencionem "evento do sistema",
  "metadados" ou um "bem-vinda de volta" falso.
- **"Menos desse tipo de comentário"** dispensa a última categoria; "restaurar" desfaz.
- **Ociosidade/retorno no Windows**: `GetLastInputInfo` (ociosidade de 5 min e retorno),
  `SetWinEventHook` (app em primeiro plano/tela cheia), sem ler títulos de janela, sem
  capturar a tela. Em Python dá para fazer com `ctypes` (sem processo nativo extra).
- Encaixe no Victorique: a fala vai para a conversa como mensagem da assistente com rótulo
  interno (não como mensagem do usuário) e aparece no balão/retrato no estado adequado. A
  spec quer comentar só nomes e estrutura de pastas, nunca conteúdo; o tédio propõe um
  enigma e, se aceito, abre um Caso.

### 2. Limites de tempo por etapa da resposta (`context-management.md`)

- 30 s sem texto visível → cancela; uma ferramenta que realmente começou troca para uma janela
  de 45 s; o resultado da ferramenta abre outra de 30 s para a resposta final. Prazo absoluto
  de 180 s.
- Batimentos e marcadores ocultos **não** renovam os prazos; nada é reenviado
  automaticamente; texto parcial fica marcado como incompleto.
- Útil no modo Local com llama-server, onde hoje um travamento só acaba no timeout HTTP.

### 3. Sampling contra repetição no modo Local (`dialogue-quality.md`)

- Para Qwen3.5 (o modelo do Victorique), o model card recomenda `presence_penalty 1.5`,
  `top_k 20` e `top_p 0.95`. O CapriCore usa `temperature 0.85` e `repeat_last_n 512` na
  conversa, e `temperature 0.2` com `presence_penalty 0` só para confirmar resultado de
  ferramenta.
- O Victorique manda só `temperature 0.7` ao llama-server. Testar antes de mudar o padrão.

### 4. Ações de arquivo mais seguras (`file-actions.md`)

- **Substituir arquivo só com o hash da última leitura** (recusa se o arquivo mudou desde
  que o modelo o leu) e cópia de recuperação privada antes de sobrescrever. Hoje o
  `write_file` sobrescreve direto.
- **Lixeira do Windows** para exclusões (já estava na lista do Victorique).
- **Diário com ID por operação**: a mesma chamada de ferramenta repetida não repete a
  mutação; operação interrompida fica marcada como "incerta" e nunca é refeita sozinha. O
  `data/operations.json` do Organizador pode ganhar esse ID.
- Cópia limitada a 20 MiB; mover só na mesma unidade; criação exclusiva (nunca sobrescreve um
  nome ao criar).

### 5. Redação de segredos em relatórios (`diagnostics/redact.mjs`)

Se o Victorique ganhar "exportar diagnóstico": trocar a pasta do usuário por `<USER>`, o
diretório do app por `<INSTALL>`, `Bearer …`, `sk-…`, `ghp_…`, `hf_…` e chaves `api_key=` por
`[SECRET]`, e-mails por `[EMAIL]`, query strings de URL por `?[REDACTED]`; campos como
`messages`, `prompt`, `content` e `filePath` são omitidos inteiros. Hoje o app não grava log
em arquivo, então ficou para depois.

### 6. Estilos de conversa rápidos (`communication-styles.md`)

Um seletor (Neutro / Afetuoso / Objetivo / Teatral) que muda só a entrega da próxima
resposta, sem reiniciar modelo nem mexer no texto da persona. Simples respostas: 1–2 frases e
parar, sem pergunta de seguimento por hábito. Os sliders de estilo do Victorique já cobrem
parte disso.

### 7. Ferramentas do usuário (`user-tools.md`)

Pasta com `manifest.json` por ferramenta (nome, descrição, esquema JSON dos parâmetros,
runtime, permissões de rede/arquivos, timeout). Desativada até o usuário revisar e aprovar;
qualquer arquivo alterado invalida a aprovação. Bom modelo se o Victorique ganhar plugins.

## Conferido e sem uso

- **SSRF**: a busca web do CapriCore só consulta endpoints fixos com `redirect: 'error'` e
  timeout de 12 s; não tem leitor de URL arbitrária, então não resolve a pendência de SSRF do
  `read_url` do Victorique.
- **Controle de carga de CPU/GPU** (Job Object do Windows com cota de CPU, alvo de GPU de 85%
  ajustado a cada 500 ms): interessante, mas depende de helper nativo em C#; só vale se o
  llama-server travar a máquina.
- Avatar que anda pela tela, xadrez, Spotify, Discord, chamadas, treino de voz, instalador e
  atualizador Electron: fora do escopo do Victorique.
- Arte, sprites, música e voz da Capri: outra personagem, licença separada. Não usar.
