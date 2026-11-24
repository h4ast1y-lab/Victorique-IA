# Uma Victorique só: a mascote entra na Biblioteca

Data: 24/11/2026. Estado: aguardando aprovação.

## Intenção

Hoje existem duas Victoriques: a mascote que anda pela área de trabalho e a do salão
da Biblioteca. O usuário quer uma só. A mascote passa por uma portinha, some da área
de trabalho e aparece no salão; lá dentro, ela mexe nos arquivos de verdade (os
livros) e depois volta. Nunca as duas aparecem ao mesmo tempo.

## Decisões do usuário

- **Quem decide a edição: os dois (opção C).**
  - **À mão:** o usuário arrasta livros entre estantes, solta no carrinho da Reserva e
    renomeia pelo botão direito; ela executa.
  - **A pedido:** o usuário pede na conversa e ela vai à Biblioteca fazer o trabalho.
  - Os dois caminhos passam pelo organizador, com histórico e Desfazer.
- **Janela grande fechada durante um trabalho pedido: opção 2.**
  - Ela some da área de trabalho e trabalha fora de vista.
  - Aparece um balão «Fui à Biblioteca…» com «Assistir», que abre a janela grande na
    aba Biblioteca.
  - A janela nunca abre sozinha.

## Propostas aceitas sem objeção (podem ser revistas na leitura deste documento)

- **Entrada.** Ela anda até a beira da superfície onde está, uma portinha aparece, ela
  passa e a porta some. No salão, ela entra pela porta que já existe à esquerda.
- **Volta.** O caminho contrário: sai pela porta do salão e reaparece na área de
  trabalho no ponto de onde saiu.
- **Quando ela entra:**
  - o usuário abre a aba Biblioteca;
  - ela mexe em arquivos a pedido;
  - o usuário escolhe o item novo «Ir para a Biblioteca» no menu do botão direito da
    mascote.
- **Quando ela volta:**
  - o usuário sai da aba Biblioteca;
  - fica 5 minutos sem nada para fazer com a aba aberta;
  - fica 30 s sem trabalho quando está lá fora de vista.
- **Edição à mão.**
  - Não pede a barra de aprovação: é ação do próprio usuário, como o Desfazer do
    Organizador.
  - Entra no histórico do Organizador com Desfazer.
  - Os livros só andam entre estantes da Biblioteca.

## Objetivos

1. Um estado de presença único, que a mascote e o salão obedecem.
2. Animações de saída e chegada nos dois lados, sem a Victorique duplicada nem
   sumida dos dois lugares por mais que a duração da porta.
3. Edição à mão no salão: mover entre estantes, mandar para a Reserva e renomear,
   por arrastar e também pelo teclado (cartão do livro).
4. Trabalho pedido leva a mascote para a Biblioteca, com o balão quando a janela está
   fechada.

## Fora do escopo

- Editar o conteúdo de um arquivo (texto, imagem) pelo salão. «Editar» aqui é mover,
  renomear e mandar para a Reserva.
- Apagar de verdade: a Reserva continua sendo o único descarte.
- Subpastas: as estantes seguem mostrando só os arquivos do primeiro nível da pasta.
- Mexer no modo Codex: ele continua somente leitura (as leituras dele levam a
  Victorique à Biblioteca como qualquer outra).

## Antiobjetivos (falha mesmo que funcione)

- Duas Victoriques visíveis ao mesmo tempo, ou nenhuma por muito tempo sem
  explicação.
- A janela grande abrindo sozinha na frente do que o usuário está fazendo.
- Arquivo alterado sem passar pelo organizador (sem Desfazer).
- O salão travado esperando uma mascote que não existe (modo navegador, mascote
  desligada ou escondida).

## Abordagens consideradas

| Abordagem | Como | Por que sim ou não |
|---|---|---|
| **Servidor é dono da presença (escolhida)** | `app/library/presence.py` guarda onde ela está; a mascote recebe ordens pelo `mascot_bus` (mesmo processo); o salão lê o estado na consulta de atividade que já faz | Funciona com a janela fechada (decisão 2), no modo navegador e com a mascote desligada |
| Página da Biblioteca decide | `library.js` manda a mascote sair e entrar | Sem janela aberta não há página: quebra a decisão 2 |
| Mascote decide | `desktop.py` guarda o estado e a página pergunta a ela | Sem mascote (navegador, desligada) o salão fica sem dono |

## Desenho

### 1. Presença (`app/library/presence.py`, novo)

Estados: `desktop`, `entrando`, `biblioteca`, `saindo`. Guarda também desde quando,
o motivo (`aba`, `trabalho`, `menu`) e o momento do último trabalho.

- **`enter(reason)`:**
  - de `desktop`: vai para `entrando` e manda `mascot_bus.command("enter-library")`;
  - sem mascote ativa e visível: vai direto para `biblioteca`;
  - em `saindo`: volta para `biblioteca` (ela desiste de sair);
  - nos outros estados: nada.
- **`mascot_left()`:** chamado pela mascote quando passou pela porta. Muda para
  `biblioteca`. Se a mascote não avisar em 6 s, o estado muda sozinho
  (`tick`/leitura preguiçosa).
- **`leave(reason)`:**
  - de `biblioteca`: vai para `saindo`. Quem anima a saída é o salão, se estiver
    aberto;
  - com a aba fechada (fora de vista): conclui na hora.
- **`left_hall()`:** chamado pela página quando ela passou pela porta do salão.
  - Muda para `desktop` e manda `mascot_bus.command("return-from-library")`.
  - Se a página não avisar em 6 s, o estado conclui sozinho.
- **`note_work()`:** chamado por `activity.record`, só quando o evento tem seção
  (`src_section` ou `dst_section`). Ler um arquivo fora das estantes não a tira da
  área de trabalho.
  - Em `desktop`: faz `enter("trabalho")` e marca `out_of_sight` quando a aba não está
    aberta (`hall_open` falso). Nesse caso, pede o balão «Fui à Biblioteca…» com o botão
    «Assistir».
  - Em qualquer estado: renova o último trabalho.
- **`hall_open`:** a página informa quando abre e fecha a aba (`POST
  /api/library/presence` com `{hall_open: bool}`). Fechar a aba chama
  `leave("aba")`; abrir chama `enter("aba")`.
- **Volta automática** (verificada na leitura do estado e num `tick` da mascote):
  - 30 s sem trabalho e aba fechada;
  - 5 min sem trabalho com a aba aberta.
  - Depois da volta automática com a aba aberta, o salão fica vazio, com «Ela voltou
    para a área de trabalho» e o botão «Chamar a Victorique».
- O estado vai junto na resposta de `GET /api/library/activity` (`"presence": {...}`),
  sem consulta nova. As transições ficam só na memória, como a atividade.
- Thread-safe (lock), porque a mascote roda numa thread própria.

### 2. Mascote (`app/mascot/desktop.py`, `behavior.py`, `sprite.py`, `bus.py`)

- **`enter-library`:**
  - O `Brain` ganha um objetivo «sair»: anda até a beira mais próxima da superfície
    atual (barra de tarefas ou borda de janela).
  - A portinha aparece ao lado dela: pixel art desenhada com Pillow no estilo da porta
    do salão, cerca de 0,75× a altura dela, num quadro que abre em 3 passos.
  - Ela vira para a porta, passa, a porta fecha e some.
  - A janela em camadas fica invisível (`away = True`, separado de `enabled` e da tela
    cheia) e chama `presence.mascot_left()`.
  - Se estiver sendo arrastada, dormindo sentada ou caindo, a saída espera o estado
    estável (máximo 3 s) e então vai assim mesmo.
- **`return-from-library`:** a porta aparece no ponto guardado da saída (se a superfície
  sumiu, na barra de tarefas do mesmo monitor), abre, ela sai andando e a porta some.
- **Longe** (`away`):
  - não desenha, ignora sinais de estado (pensando/falando) e não abre a conversa
    rápida;
  - o balão «Fui à Biblioteca…» aparece ancorado onde a porta ficava, por 10 s.
    «Assistir» chama `bridge.open_library()`: abre a janela grande e troca para a aba
    Biblioteca pelo `evaluate_js`, como o `open_conversation`;
  - os balões da vida própria continuam: ancorados no mesmo ponto, e «Aceitar o Caso»
    funciona como antes.
- **Menu:** item novo «Ir para a Biblioteca» (`MENU_LIBRARY`). Como é um pedido
  explícito do usuário, ela passa pela porta e a janela grande abre na aba
  Biblioteca (`bridge.open_library()`); a regra «a janela nunca abre sozinha» vale
  para o trabalho pedido, não para este clique. Enquanto ela está longe não há menu,
  porque não há onde clicar; ela volta sozinha.
- **Sem a mascote** (`run.py --browser`, mascote desligada ou escondida): nenhum
  comando é enviado e a presença pula as animações do lado da área de trabalho.

### 3. Salão (`app/ui/js/library.js`)

- **Lê `presence` a cada consulta:**
  - `desktop`: o salão fica sem ela; a linha de estado diz «Ela está na área de
    trabalho» e aparece o botão «Chamar a Victorique» (`POST
    /api/library/presence {enter: true}`);
  - `entrando` ou `biblioteca`, se ela ainda não está no salão: a porta do salão abre
    e ela entra andando até o centro da vista;
  - `saindo`: ela termina a cena atual, anda até a porta, a porta abre, ela passa e a
    página chama `POST /api/library/presence {left_hall: true}`.
- Abrir e fechar a aba informam `hall_open`.
- **A porta do salão ganha 3 quadros** (fechada, entreaberta, aberta), desenhados no
  canvas como o resto.

### 4. Edição à mão (salão + rotas novas)

- **Arrastar:**
  - Botão esquerdo num livro e mais de 6 px de movimento: o livro sai da estante e
    acompanha o cursor.
  - As estantes de destino e o carrinho da Reserva brilham em latão sob o cursor.
  - Soltar fora, ou na estante de origem, devolve o livro.
  - O arrastar do salão (câmera) continua quando o clique não começa num livro.
- **Botão direito num livro:** menu pequeno no canvas com «Renomear…», «Mover para…»,
  «Mandar para a Reserva» e «Pedir para ela ler».
- **Teclado e alternativa ao arrastar:** o cartão do livro ganha «Mover para…» (lista
  das outras estantes), «Renomear» (campo no próprio cartão, Enter confirma, Esc
  cancela) e «Mandar para a Reserva» (dois cliques para confirmar, como o desvincular).
- **Rotas novas:**
  - `POST /api/library/books/move {path, section_id}`
  - `POST /api/library/books/rename {path, new_name}`
  - `POST /api/library/books/reserve {path}`
- **Validação no servidor:**
  - o `path` é um arquivo do primeiro nível de uma seção visível;
  - a seção de destino existe e é outra;
  - erros do organizador viram 400 (`ValueError`) e 409 (`FileExistsError`) com a
    mensagem dele.
- **Execução:**
  - Chama `organizer.move_files`, `rename_file` e `send_to_reserve` com descrição
    «Biblioteca: …», e registra no `audit_logs` como ação do usuário.
  - A atividade gerada vira cena: ela anda até o livro, pega, leva e guarda.
  - Para a cena começar logo, a página chama `notifyActivity()` depois do sucesso.
  - O livro fica «reservado» na estante (meio transparente) até a cena pegá-lo.
- **Erro:** aviso (toast) com a mensagem; o livro volta ao lugar.
- **Se ela ainda não está no salão** (`entrando`): a edição é enviada mesmo assim, e a
  cena espera ela chegar.

### 5. Trabalho a pedido

`activity.record` chama `presence.note_work()` (sem lançar exceção; import dentro da
função para não criar ciclo `activity` ↔ `presence`). As cenas já existentes cuidam
do resto: com a aba aberta ela é vista fazendo; com a aba fechada, as cenas ficam na
fila e o contador da aba sobe, como hoje.

O balão «Fui à Biblioteca…» aparece sempre que a aba Biblioteca não está aberta,
também com a janela grande aberta em outra aba (por exemplo, quando o pedido veio da
conversa). «Assistir» só troca de aba nesse caso.

As edições à mão usam `actor="usuario"` na atividade. A cena é a mesma (é ela quem
carrega o livro); o campo serve para o histórico e para testes.

## Testes previstos

- **Presença:**
  - entrar com e sem mascote;
  - sair com a aba aberta e fechada;
  - timeouts de 6 s;
  - volta automática (30 s e 5 min, com relógio injetável);
  - `note_work` com a aba fechada pedindo o balão;
  - desistir de sair.
- **Rotas de livros:**
  - mover, renomear e Reserva viram lotes no Organizador com Desfazer e geram
    atividade;
  - recusam arquivo fora de seção, em subpasta, destino igual e nome que já existe
    (409).
- **Mascote** (com os falsos de `tests/test_mascot.py`):
  - `enter-library` termina invisível e avisa a presença;
  - `return-from-library` reaparece no ponto guardado;
  - o menu tem «Ir para a Biblioteca»;
  - o balão «Assistir» chama `open_library`;
  - longe, o clique não abre a conversa rápida.
- **Interface:** os ids novos existem no `index.html`; `node --check`.
- **Navegador:**
  - chamar e dispensar a Victorique;
  - arrastar um livro entre estantes e conferir o arquivo movido e o lote no
    Organizador;
  - renomear pelo cartão;
  - mandar para a Reserva.
- **Área de trabalho real:** não automatizável daqui. Fica como verificação manual do
  usuário (porta, saída e volta).

## Decisões minhas na revisão (confira)

- Só trabalho em arquivos das estantes a leva à Biblioteca.
- «Ir para a Biblioteca» no menu abre a janela grande na aba Biblioteca.
- O balão aparece também com a janela aberta em outra aba.
- Tempos: 6 s de limite para cada porta, volta após 30 s fora de vista e 5 min com a
  aba aberta e parada.
- Sem barra de aprovação nas edições à mão; continuam com Desfazer e registro.
- A portinha da área de trabalho é desenhada no código (Pillow), não vem das folhas de
  sprite.

## Deixado para quem constrói

- Desenho exato da portinha e do menu de botão direito no canvas.
- Velocidade da caminhada até a porta e duração de cada quadro da porta.
- Texto exato dos avisos, em pt-BR e no tom do app.
