# Uma Victorique só: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A mascote da área de trabalho passa por uma portinha, aparece no salão da
Biblioteca e mexe nos arquivos (mover, renomear, Reserva), a pedido ou pela mão do
usuário, sem nunca haver duas Victoriques ao mesmo tempo.

**Architecture:** Um estado de presença em memória no servidor
(`app/library/presence.py`) é o dono de onde ela está. A mascote, que roda no mesmo
processo, recebe ordens pelo `mascot_bus` e avisa quando passou pela porta. O salão
lê o estado junto da consulta de atividade que já faz e avisa quando abre ou fecha a
aba. As edições à mão vão por rotas novas, que chamam o organizador (histórico e
Desfazer).

**Tech Stack:** FastAPI, Python 3.12, Pillow (desenho da portinha), Win32 layered
window (mascote), canvas 2D em JS puro (salão), pytest.

**Spec:** `docs/superpowers/specs/2026-11-24-victorique-entra-na-biblioteca-design.md`

## Global Constraints

- Texto da interface em pt-BR, no tom do app.
- Tempos fixos do design: `DOOR_TIMEOUT = 6.0` s por porta; volta automática após
  `AWAY_IDLE = 30.0` s sem trabalho com a aba fechada e `HALL_IDLE = 300.0` s com a aba
  aberta; a saída da mascote espera no máximo `LEAVE_WAIT = 3.0` s por um estado
  estável.
- Edição à mão: nenhuma barra de aprovação, mas sempre pelo organizador (lote no
  histórico com Desfazer) e com registro em `audit_logs`.
- Só arquivos do primeiro nível de uma seção; nada de subpastas, nada de apagar, nada
  de editar conteúdo.
- A janela grande nunca abre sozinha por trabalho pedido. Ela só abre por clique do
  usuário: «Assistir» no balão ou «Ir para a Biblioteca» no menu.
- Nada de dependências novas. Não instalar Ollama, llama.cpp, modelos nem o Codex.
- Não fazer commit nem push sem o usuário pedir. Nunca enviar ao remoto `origin`.
- Testes: `"C:/Users/h4ast/Downloads/Victorique Bot/.venv/Scripts/python.exe" -m pytest -q -p no:cacheprovider`
  (o worktree não tem `.venv` próprio). Linha de base: 339 passando, 3 pulados.

## Review Focus

1. **Janela grande escondida com a aba Biblioteca aberta.** Ela deve voltar à área de
   trabalho, não ficar 5 min presa no salão invisível. A página informa
   `hall_open=false` no `visibilitychange` (Tarefa 6).
2. **Mascote em tela cheia, desligada ou escondida quando chega `enter-library`.** Ela
   some na hora (`vanish`) e não reaparece na área de trabalho enquanto a presença
   diz `biblioteca` (Tarefa 5).
3. **Abrir, fechar e reabrir a aba rápido, no meio das portas.** `leave` durante
   `entrando` cancela a ida; `enter` durante `saindo` desiste da saída. O estado nunca
   fica em `entrando` ou `saindo` além do limite (Tarefa 1).
4. **Renomear para um nome inválido no Windows** (`CON`, `a:b`, nome com barra, nome
   vazio): resposta 400 ou 403 com mensagem, nunca 500 (Tarefa 3).
5. **Livro que sumiu entre a listagem e o arrastar** (outro programa moveu): 404 com
   «Esse livro não está mais nessa estante.», e o livro volta ao lugar (Tarefas 3 e 7).

---

### Task 1: Estado de presença

**Files:**
- Create: `app/library/presence.py`
- Test: `tests/test_library_presence.py`

**Interfaces:**
- Consumes: `app.mascot.bus.mascot_bus` com `.command(action: str) -> bool` e
  `.visible -> bool` (já existem).
- Produces:
  - `class Presence(clock: Callable[[], float] = time.monotonic, bus: Any = None)`,
    onde `bus=None` significa usar `mascot_bus` (import preguiçoso).
  - `Presence.snapshot() -> dict` com as chaves `state` (`"desktop" | "entrando" |
    "biblioteca" | "saindo"`), `reason` (`"aba" | "trabalho" | "menu" | None`),
    `hall_open: bool`, `out_of_sight: bool` e `since: float`.
  - Métodos que devolvem `snapshot()`:
    - `enter(reason: str, announce: bool = False)`
    - `leave(reason: str)`
    - `set_hall_open(is_open: bool)`
    - `tick()`
  - Métodos que devolvem `None`: `mascot_left()`, `left_hall()`, `note_work()`.
  - Comandos enviados à mascote: `"enter-library"`, `"enter-library-announce"` e
    `"return-from-library"`.
  - Singleton `presence = Presence()`.
  - Constantes `DOOR_TIMEOUT`, `AWAY_IDLE` e `HALL_IDLE`, com os valores das Global
    Constraints.

- [ ] **Step 1: Escrever os testes que falham**

  Use um `FakeBus` com `commands: list`, `visible: bool` e `command()` que anota e
  devolve `True`, e um relógio falso (`t` mutável). Os testes:

```python
def test_enter_with_visible_mascot_waits_for_the_door():
    p, bus, clock = make(visible=True)
    assert p.enter("aba")["state"] == "entrando"
    assert bus.commands == ["enter-library"]
    p.mascot_left()
    assert p.snapshot()["state"] == "biblioteca"

def test_enter_without_mascot_goes_straight_in():
    p, bus, clock = make(visible=False)
    assert p.enter("aba")["state"] == "biblioteca"
    assert bus.commands == ["enter-library"]        # um mascote escondido some na hora

def test_door_timeout_finishes_entering_and_leaving():
    p, bus, clock = make(visible=True)
    p.set_hall_open(True)
    clock.t += 6.1
    assert p.tick()["state"] == "biblioteca"
    p.leave("aba")                                    # aba aberta: o salão anima a saída
    assert p.snapshot()["state"] == "saindo"
    clock.t += 6.1
    assert p.tick()["state"] == "desktop"
    assert bus.commands[-1] == "return-from-library"

def test_closing_the_tab_returns_her_at_once():
    p, bus, clock = make(visible=False)
    p.set_hall_open(True)
    assert p.set_hall_open(False)["state"] == "desktop"
    assert bus.commands == ["enter-library", "return-from-library"]

def test_left_hall_completes_the_exit():
    p, bus, clock = make(visible=False)
    p.set_hall_open(True); p.leave("menu")
    p.left_hall()
    assert p.snapshot()["state"] == "desktop"

def test_work_with_the_tab_closed_sends_her_out_of_sight_and_announces():
    p, bus, clock = make(visible=True)
    p.note_work()
    snap = p.snapshot()
    assert snap["state"] == "entrando" and snap["out_of_sight"] and snap["reason"] == "trabalho"
    assert bus.commands == ["enter-library-announce"]

def test_out_of_sight_returns_after_30s_without_work_and_work_renews_it():
    p, bus, clock = make(visible=False)
    p.note_work()
    clock.t += 20; p.note_work()
    clock.t += 20
    assert p.tick()["state"] == "biblioteca"
    clock.t += 11
    assert p.tick()["state"] == "desktop"

def test_open_tab_idle_for_five_minutes_sends_her_home():
    p, bus, clock = make(visible=False)
    p.set_hall_open(True)
    clock.t += 299; assert p.tick()["state"] == "biblioteca"
    clock.t += 2;   assert p.tick()["state"] == "saindo"

def test_leave_while_entering_cancels_and_enter_while_leaving_stays():
    p, bus, clock = make(visible=True)
    p.enter("aba"); p.leave("aba")
    assert p.snapshot()["state"] == "desktop"
    assert bus.commands == ["enter-library", "return-from-library"]
    p2, bus2, _ = make(visible=False)
    p2.set_hall_open(True); p2.leave("menu")
    assert p2.enter("aba")["state"] == "biblioteca"

def test_opening_the_tab_after_work_brings_her_into_view():
    p, bus, clock = make(visible=False)
    p.note_work()
    assert p.set_hall_open(True)["out_of_sight"] is False
```

- [ ] **Step 2: Rodar e ver falhar**

  Run: `... -m pytest tests/test_library_presence.py -q -p no:cacheprovider`
  Expected: FAIL com `ModuleNotFoundError: app.library.presence`.

- [ ] **Step 3: Implementar `Presence` em `app/library/presence.py`**

  - Um `threading.Lock` protege tudo; os comandos ao `bus` saem fora do lock.
  - `enter` vindo de `desktop`:
    - manda `"enter-library-announce"` quando `announce`, senão `"enter-library"`;
    - vai para `entrando` só se `bus.command(...)` for verdadeiro **e** `bus.visible`;
    - senão vai direto para `biblioteca`.
  - `leave`:
    - de `entrando`: vai para `desktop` e manda `"return-from-library"`;
    - de `biblioteca` com `hall_open`: vai para `saindo`;
    - de `biblioteca` sem a aba: vai para `desktop` e manda o comando.
  - `out_of_sight = not hall_open`, recalculado em cada transição e em
    `set_hall_open`.
  - `note_work()`:
    - renova o relógio de trabalho;
    - em `desktop`, chama `enter("trabalho", announce=not hall_open)`.
  - `tick()`:
    - aplica os limites de porta;
    - aplica `AWAY_IDLE` quando `not hall_open` e o estado é `biblioteca`;
    - aplica `HALL_IDLE` quando `hall_open` e o estado é `biblioteca`, contando
      desde o maior entre a última entrada e o último trabalho.
  - `snapshot()` chama a mesma checagem de limites antes de responder.

- [ ] **Step 4: Rodar e ver passar**

  Run: o mesmo comando. Expected: 10 passed.

---

### Task 2: Presença ligada à atividade e às rotas

**Files:**
- Modify: `app/library/activity.py` (`record`, `since`)
- Modify: `app/main.py` (rota nova perto de `/api/library/activity`, cerca da linha 1065)
- Test: `tests/test_library_presence.py` (acrescentar)

**Interfaces:**
- Consumes: `presence.note_work()`, `presence.snapshot()`, `presence.enter()`,
  `presence.set_hall_open()` e `presence.left_hall()` (Tarefa 1).
- Produces:
  - `GET /api/library/activity` passa a devolver
    `{"events", "last", "presence": snapshot}`.
  - `POST /api/library/presence` recebe o corpo `LibraryPresence {hall_open:
    Optional[bool], enter: bool = False, left_hall: bool = False}` e devolve
    `snapshot`. Ordem de aplicação: `hall_open`, `enter` (motivo `"menu"`) e
    `left_hall`.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_recording_shelf_work_notifies_presence(monkeypatch, library):
    calls = []
    monkeypatch.setattr(presence_mod.presence, "note_work", lambda: calls.append(1))
    downloads = library["home"] / "Downloads" / "a.txt"; downloads.write_text("x")
    activity.record("read", str(downloads))
    activity.record("read", str(library["root"] / "fora.txt"))   # fora das estantes
    assert calls == [1]

def test_activity_route_carries_presence(client):
    data = client.get("/api/library/activity?since=0").json()
    assert data["presence"]["state"] in ("desktop", "entrando", "biblioteca", "saindo")

def test_presence_route_opens_and_closes_the_hall(client, monkeypatch):
    p = presence_mod.Presence(bus=FakeBus(visible=False))
    monkeypatch.setattr(presence_mod, "presence", p)
    assert client.post("/api/library/presence", json={"hall_open": True}).json()["state"] == "biblioteca"
    assert client.post("/api/library/presence", json={"hall_open": False}).json()["state"] == "desktop"
```

  O fixture `library` fica em `tests/test_library.py`. Mova-o para
  `tests/conftest.py`, ou importe-o com `from tests.test_library import library`.

- [ ] **Step 2: Rodar e ver falhar**

  Expected: os três falham (sem `note_work` chamado, sem a chave `presence`, 404 na
  rota).

- [ ] **Step 3: Implementar**

  - **`activity.record`:** depois de guardar o evento, chamar
    `presence.note_work()` só quando `src_section` ou `dst_section` não for `None`.
    O import fica dentro da função, com `try/except Exception: pass`.
  - **`since`:** acrescenta `presence` pelo `snapshot()`, também dentro de `try`.
    Numa falha, devolve `None`.
  - **Rota:** o modelo pydantic fica junto de `LibrarySectionCreate`. A rota
    referencia o módulo (`presence_mod.presence`) para o monkeypatch funcionar.

- [ ] **Step 4: Rodar e ver passar**, depois a suíte inteira.

  Expected: tudo verde, contagem = linha de base + novos.

---

### Task 3: Edição de livros pelo servidor

**Files:**
- Create: `app/library/editing.py`
- Modify: `app/tools/organizer.py`: `move_files`, `rename_file`, `send_to_reserve`,
  `_run` e `_tell_library` ganham `actor: str = "victorique"`, repassado a
  `activity.record_moves(kind, moves, actor)`.
- Modify: `app/main.py` (três rotas)
- Test: `tests/test_library_editing.py`

**Interfaces:**
- Consumes:
  - `sections.list_sections()` e `sections.get_section(id)` (com `path`);
  - as funções do organizador acima;
  - `security_manager.log_action(action_type, ActionCategory.FREE, resource,
    True, details)`.
- Produces (cada função devolve o resultado do organizador: `batch_id`, `moved` e
  `ops`):
  - `editing.move_book(path: str, section_id: str) -> dict`: chama o organizador com
    a descrição `"Biblioteca: {nome} para {seção}"`.
  - `editing.rename_book(path: str, new_name: str) -> dict`: chama o organizador com
    a descrição `"Biblioteca: {antigo} para {novo}"`. Isso pede um parâmetro opcional
    `descricao` em `rename_file`.
  - `editing.reserve_book(path: str) -> dict`: chama o organizador com a descrição
    `"Biblioteca: {nome} para a Reserva"`.
  - `class BookNotFound(LookupError)`.
  - Rotas, todas com corpo JSON:
    - `POST /api/library/books/move {path, section_id}`
    - `POST /api/library/books/rename {path, new_name}`
    - `POST /api/library/books/reserve {path}`
  - Erros das rotas:
    - `BookNotFound` vira 404;
    - `ValueError` vira 400;
    - `FileExistsError` vira 409;
    - `PermissionError` vira 403;
    - o `detail` é a mensagem da exceção.
  - `actor="usuario"` em todas.

- [ ] **Step 1: Escrever os testes que falham** (use o fixture `library`; as seções
  padrão `downloads` e `documentos` são pastas reais em `tmp_path`):

```python
def test_move_book_between_shelves_is_an_undoable_batch(library):
    src = library["home"] / "Downloads" / "nota.txt"; src.write_text("x")
    result = editing.move_book(str(src), "documentos")
    assert (library["home"] / "Documents" / "nota.txt").exists() and not src.exists()
    ev = activity.since(0)["events"][-1]
    assert ev["kind"] == "move" and ev["actor"] == "usuario"
    organizer.undo(result["batch_id"])
    assert src.exists()

def test_rename_and_reserve(library):
    src = library["home"] / "Downloads" / "a.txt"; src.write_text("x")
    editing.rename_book(str(src), "b.txt")
    renamed = library["home"] / "Downloads" / "b.txt"
    assert renamed.exists()
    editing.reserve_book(str(renamed))
    assert not renamed.exists()
    assert activity.since(0)["events"][-1]["kind"] == "reserve"

@pytest.mark.parametrize("make_path", ["subpasta", "fora", "sumiu"])
def test_refuses_books_not_on_the_first_level_of_a_shelf(library, make_path):
    # subpasta: Downloads/sub/x.txt; fora: tmp_path/x.txt; sumiu: Downloads/nao-existe.txt
    with pytest.raises(editing.BookNotFound):
        editing.move_book(str(path_for(library, make_path)), "documentos")

def test_same_shelf_and_unknown_shelf_are_refused(library):
    src = library["home"] / "Downloads" / "a.txt"; src.write_text("x")
    with pytest.raises(ValueError): editing.move_book(str(src), "downloads")
    with pytest.raises(ValueError): editing.move_book(str(src), "nao-existe")

def test_routes_map_errors(client, library):
    a = library["home"] / "Downloads" / "a.txt"; a.write_text("x")
    (library["home"] / "Documents" / "a.txt").write_text("y")
    assert client.post("/api/library/books/move", json={"path": str(a), "section_id": "documentos"}).status_code == 409
    assert client.post("/api/library/books/rename", json={"path": str(a), "new_name": "x/y"}).status_code == 400
    assert client.post("/api/library/books/rename", json={"path": str(a), "new_name": "CON"}).status_code in (400, 403)
    gone = library["home"] / "Downloads" / "sumiu.txt"
    r = client.post("/api/library/books/reserve", json={"path": str(gone)})
    assert r.status_code == 404 and "não está mais" in r.json()["detail"]
```

  Para as rotas, as seções padrão devem estar autorizadas no `path_guard`:
  `sections.apply_authorization()` no começo do teste.

- [ ] **Step 2: Rodar e ver falhar.** Expected: `ModuleNotFoundError: app.library.editing`.

- [ ] **Step 3: Implementar `app/library/editing.py` e as rotas**

  - `_book(path) -> (section: dict, file: Path)`:
    - resolve o caminho;
    - procura a seção cujo `os.path.normcase(resolve(section.path))` é igual ao
      `normcase` de `file.parent`;
    - se não acha a seção, ou se `file.is_file()` é falso, lança
      `BookNotFound("Esse livro não está mais nessa estante.")`.
  - Destino de `move_book`:
    - a seção precisa existir; senão, `ValueError("Essa estante não existe.")`;
    - precisa ser outra; senão, `ValueError("O livro já está nessa estante.")`;
    - o arquivo vai para `Path(destino.path) / file.name`.
  - Cada função chama `security_manager.log_action` depois do sucesso, com
    `action_type` igual a `"library_move"`, `"library_rename"` ou
    `"library_reserve"`.
  - As rotas rodam em `asyncio.to_thread`.

- [ ] **Step 4: Rodar e ver passar**, depois a suíte inteira (testes do organizador
  incluídos).

---

### Task 4: A portinha e o caminho da mascote (comportamento)

**Files:**
- Modify: `app/mascot/behavior.py` (`Brain`)
- Modify: `app/mascot/sprite.py`
- Test: `tests/test_mascot.py` (acrescentar)

**Interfaces:**
- Produces, em `Brain`:
  - `go_away(now: float) -> None`. Marca `self.leaving = True`. Quando ela está
    de pé (fora de `held`, `air` e `climb`), anda até a ponta mais próxima de
    `_walk_range` da superfície atual e entra no modo `"door_in"`.
  - `vanish(now: float) -> None`: vai direto para `"away"`.
  - `come_back(now: float, world: World) -> None`:
    - de `"away"`, faz `"door_out"` no ponto guardado `self.away_spot = (x,
      surface_key)`;
    - se a superfície sumiu, usa o chão, com o x preso no `_walk_range` do chão;
    - em `"door_in"`, ou com `leaving` ainda andando, cancela e vai para `idle`.
  - `is_away -> bool`: verdadeiro no modo `"away"`.
  - `door -> Optional[Tuple[float, float, int]]`: `(x, y, quadro 0..2)` enquanto
    a porta aparece.
  - `hidden -> bool`: o sprite não deve ser desenhado.
  - Constantes `DOOR_STEP = 0.15` (s por quadro da porta) e `PASS_SECONDS = 0.6`.
  - Linha do tempo de `"door_in"`, com a porta a `0.35 * height` à frente dela:
    1. porta 0, 1 e 2;
    2. ela anda até a porta;
    3. `hidden` fica verdadeiro;
    4. porta 2, 1 e 0;
    5. `"away"`.
  
    `"door_out"` é o contrário.
- Produces, em `sprite.py`: `door_image(frame: int, height: int) -> Image.Image`.
  - Pixel art com fundo transparente, altura `round(0.75 * height)`.
  - Usa as mesmas cores de madeira e latão do salão: `#5a3b26`, `#7a5236`, `#3e2718`
    e `#c9a55a`.
  - O quadro 0 é a porta fechada, o 1 entreaberta e o 2 aberta, com o interior
    escuro.

- [ ] **Step 1: Escrever os testes que falham** (use `world()`, `Clock` e `run` que
  já existem no arquivo):

```python
def test_go_away_walks_to_the_edge_opens_the_door_and_disappears():
    b, clock, w = Brain(random.Random(1)), Clock(), world()
    run(b, clock, w, 1)
    b.go_away(clock.t)
    seen_frames = set()
    run(b, clock, w, 40, until=lambda: b.is_away,
        each=lambda: b.door and seen_frames.add(b.door[2]))
    assert b.is_away and b.hidden and seen_frames == {0, 1, 2}
    lo, hi = b._walk_range(w.ground)
    assert b.away_spot[0] in (pytest.approx(lo, abs=2), pytest.approx(hi, abs=2))

def test_come_back_reappears_at_the_spot_and_idles():
    b, clock, w = Brain(random.Random(1)), Clock(), world()
    run(b, clock, w, 1); b.go_away(clock.t)
    run(b, clock, w, 40, until=lambda: b.is_away)
    spot = b.away_spot
    b.come_back(clock.t, w)
    run(b, clock, w, 5, until=lambda: b.mode == "idle")
    assert not b.hidden and b.door is None and abs(b.x - spot[0]) < 0.5 * b.height

def test_away_ignores_steps_and_states():
    b, clock, w = Brain(random.Random(1)), Clock(), world()
    run(b, clock, w, 1); b.vanish(clock.t)
    b.set_app_state("pensando"); run(b, clock, w, 3)
    assert b.is_away and b.hidden

def test_come_back_while_going_cancels():
    b, clock, w = Brain(random.Random(1)), Clock(), world()
    run(b, clock, w, 1); b.go_away(clock.t); run(b, clock, w, 0.2)
    b.come_back(clock.t, w)
    assert not b.leaving and b.mode in ("idle", "turn")

def test_door_image_frames():
    imgs = [sprite.door_image(f, 136) for f in (0, 1, 2)]
    assert all(i.height == 102 and i.mode == "RGBA" for i in imgs)
    assert imgs[0].tobytes() != imgs[2].tobytes()
```

  Se `run` não aceitar `each`, acrescente esse parâmetro opcional ao `run` do teste:
  uma chamada por passo.

- [ ] **Step 2: Rodar e ver falhar.** Expected: `AttributeError: 'Brain' object has no attribute 'go_away'`.

- [ ] **Step 3: Implementar**

  - No `Brain.step`:
    - `"away"`: retorna logo depois de `self.now = now`;
    - `"door_in"` e `"door_out"`: avançam a linha do tempo e retornam;
    - `leaving` com ela parada de pé: começa a caminhada, com
      `plan={"kind": "door"}`.
  - No `_stop_walking`, o plano `"door"` inicia `"door_in"`.
  - `is_resting()` não inclui os modos novos.

- [ ] **Step 4: Rodar e ver passar**, depois `tests/test_mascot.py` inteiro.

---

### Task 5: A mascote obedece à presença

**Files:**
- Modify: `app/mascot/desktop.py`
- Modify: `app/mascot/launcher.py` (`ChatWindowBridge.open_library`)
- Modify: `app/ui/js/app.js` (`window.victoriqueDesktop.openLibrary`)
- Test: `tests/test_mascot.py` (acrescentar)

**Interfaces:**
- Consumes: `Brain.go_away`, `vanish`, `come_back`, `is_away`, `door`, `hidden` e
  `away_spot` (Tarefa 4); `sprite.door_image` (Tarefa 4); `presence.mascot_left()`,
  `presence.enter("menu")` e `presence.tick()` (Tarefa 1).
- Produces:
  - **Construtor:** `DesktopMascot(..., presence: Any = None)`, com o padrão
    `from app.library.presence import presence`, importado no `__init__` como `life`.
  - **Menu:** `MENU_LIBRARY = 8`, rótulo `"Ir para a Biblioteca"`, logo depois de
    `MENU_MINI`.
  - **Balão** ao chegar em `away` depois de `"enter-library-announce"`:
    `Bubble(text="Fui à Biblioteca cuidar dos seus livros.", tag="biblioteca",
    buttons=(Button("watch", "Assistir", True),))`, com `kind "library"` e duração de
    10 s.
  - **Botão `"watch"`:** chama `_bridge("open_library")`.
  - **Ponte:** `ChatWindowBridge.open_library()` faz `open_chat()` e depois
    `evaluate_js("window.victoriqueDesktop && window.victoriqueDesktop.openLibrary()")`.
  - **`app.js`:** `openLibrary: () => showSidebarTab('hall')`.

- [ ] **Step 1: Escrever os testes que falham.**

  O `FakeBridge` ganha `open_library`. Um `FakePresence` registra `mascot_left`,
  `enter` e `tick`. O `make_mascot` passa `presence=FakePresence()`.

```python
def test_enter_library_walks_out_hides_and_tells_presence():
    m, clock, _c, _s = make_mascot()
    tick(m, clock)
    m.post("command", "enter-library")
    tick(m, clock, 1200)
    assert m.brain.is_away and not m.window.visible and not m.on_screen
    assert m.presence.calls.count("mascot_left") == 1

def test_announce_shows_watch_balloon_that_opens_the_library():
    m, clock, cursor, _s = make_mascot()
    tick(m, clock); m.post("command", "enter-library-announce"); tick(m, clock, 1200)
    assert m.shown and m.shown.kind == "library" and m.window.visible
    click_button(m, clock, "watch")      # helper que já clica em rects do balão, como no teste do tédio
    assert ("open_library",) in m.bridge.calls

def test_hidden_mascot_vanishes_at_once_and_stays_hidden_after_fullscreen():
    m, clock, _c, state = make_mascot(prefs={"mascot_enabled": False})
    tick(m, clock); m.post("command", "enter-library"); tick(m, clock)
    assert m.brain.is_away and m.presence.calls.count("mascot_left") == 1
    state["prefs"]["mascot_enabled"] = True
    tick(m, clock, 200)
    assert not m.window.visible

def test_return_from_library_reappears_where_she_left():
    m, clock, _c, _s = make_mascot()
    tick(m, clock); m.post("command", "enter-library"); tick(m, clock, 1200)
    x = m.brain.away_spot[0]
    m.post("command", "return-from-library"); tick(m, clock, 200)
    assert m.window.visible and not m.brain.hidden and abs(m.brain.x - x) < 0.5 * m.brain.height

def test_menu_has_go_to_library_and_it_opens_the_hall():
    m, clock, _c, _s = make_mascot()
    tick(m, clock)
    m.window.menu_choice = 8
    m._menu(0, 0)
    assert any(item[1] == "Ir para a Biblioteca" for item in m.window.menu)
    assert ("enter", "menu") in m.presence.calls and ("open_library",) in m.bridge.calls

def test_no_mini_chat_while_away_and_presence_is_ticked():
    m, clock, cursor, _s = make_mascot()
    tick(m, clock); m.post("command", "enter-library"); tick(m, clock, 1200)
    m._pending_click = clock.t; tick(m, clock)
    assert not _mini_calls(m)
    assert m.presence.calls.count("tick") >= 40       # cerca de 1 por segundo em 48 s
```

  Ajuste o número de ticks se a caminhada até a borda for mais longa. A área de
  teste tem 1920 px, e ela anda cerca de 40 px/s.

- [ ] **Step 2: Rodar e ver falhar.**

- [ ] **Step 3: Implementar em `desktop.py`**

  - **`_handle("command", ...)`:**
    - `"enter-library"` e `"enter-library-announce"` guardam
      `self._announce` e `self._leave_asked = now`;
    - se `self.on_screen`, chamam `brain.go_away(now)`; senão, `brain.vanish(now)`;
    - `"return-from-library"` liga `self._return_pending = True`.
  - **`_ev_tick`:**
    - chama `presence.tick()` no máximo uma vez por segundo, antes do teste `show`,
      dentro de `try/except`;
    - quando `brain.leaving` está há mais de `LEAVE_WAIT` em `held`, `air` ou
      `climb`, chama `brain.vanish(now)`;
    - quando o cérebro passa a `is_away`, chama `presence.mascot_left()` uma vez, e
      `_library_note(now)` se `self._announce`;
    - o `_return_pending` aplica `brain.come_back(now, world)` no próximo `_frame`.
    - Essa checagem de `is_away` roda mesmo com a mascote desligada. Assim
      `vanish()` avisa a presença na hora.
  - **`_frame`:**
    - com `brain.hidden` e sem balão: `window.set_visible(False)`,
      `on_screen = False` e retorna;
    - com `brain.hidden` e com balão: compõe um sprite transparente do tamanho de
      `sprite.render(Look("blink", 0, 1), size_px)`, ancorado em `away_spot`;
    - com `brain.door`: compõe `door_image` atrás do sprite, com a base em `door[1]`
      e centrada em `door[0]`. Estenda `_compose` com uma camada opcional antes do
      sprite.
  - **Sem conversa rápida longe:** `_toggle_mini` e o duplo clique retornam sem
    fazer nada quando `brain.is_away`.
  - **Menu:** `MENU_LIBRARY` chama `presence.enter("menu")` e
    `_bridge("open_library")`.

- [ ] **Step 4: Rodar e ver passar**, depois `tests/test_mascot.py` e a suíte inteira.

---

### Task 6: O salão segue a presença

**Files:**
- Modify: `app/ui/js/library.js`
- Modify: `app/ui/index.html`: dentro do cabeçalho de `#libraryView`, um
  `<button id="btnLibraryCall" class="btn-ghost" hidden>Chamar a Victorique</button>`.
- Modify: `app/ui/css/style.css`, só se o botão precisar de ajuste.
- Test: `tests/test_stream_and_ui.py` (estender `test_library_hall_page_is_wired`)

**Interfaces:**
- Consumes: `POST /api/library/presence` e a chave `presence` na atividade (Tarefa 2).
- Produces, em `library.js`:
  - `herWhere`, que vale `'out' | 'arriving' | 'in' | 'leaving'`;
  - `applyPresence(p)`;
  - `reportHall(isOpenAndVisible: boolean)`;
  - `doorOpen` (0..1), desenhado por `drawDoor()`.

- [ ] **Step 1: Estender o teste de interface (falha)**

```python
assert 'id="btnLibraryCall"' in html
for needle in ("applyPresence", "reportHall", "visibilitychange", "/api/library/presence", "left_hall"):
    assert needle in js
```

- [ ] **Step 2: Rodar e ver falhar.**

- [ ] **Step 3: Implementar em `library.js`**

  - **Abrir e fechar a aba:**
    - `open()` chama `reportHall(true)` e aplica a resposta;
    - `close()` chama `reportHall(false)`.
  - **`visibilitychange`:** com `isOpen`, chama `reportHall(document.visibilityState
    === 'visible')`.
  - **`poll()`:** chama `applyPresence(data.presence)` antes de `enqueue`.
  - **`applyPresence`:**
    - `entrando` ou `biblioteca` com `herWhere === 'out'`:
      - ela aparece em `world.door`;
      - `doorOpen` vai a 1 em 0,45 s;
      - ela anda até o centro da vista e a porta fecha;
      - `herWhere = 'in'`.
    - `saindo` com `'in'`:
      - termina a tarefa de cena atual, se houver;
      - anda até a porta e a porta abre;
      - ela some, a porta fecha;
      - `api('/api/library/presence', {method: 'POST', body: {left_hall: true}})`;
      - `herWhere = 'out'`.
    - `desktop`: `herWhere = 'out'` na hora, sem animação, e o rótulo
      «Ela está na área de trabalho.»
  - **Com `herWhere === 'out'`:**
    - `update()` não roda tarefas e a fila continua guardando as cenas;
    - `drawHer` não desenha;
    - `#btnLibraryCall` aparece, e no clique faz o POST `{enter: true}` e aplica a
      resposta.
  - **Com ela dentro:** `#btnLibraryCall` some.
  - **Sem ela no salão:** clicar onde ela ficaria não faz nada.

- [ ] **Step 4: Rodar o teste de interface e `node --check app/ui/js/library.js`.**

---

### Task 7: Edição à mão no salão

**Files:**
- Modify: `app/ui/js/library.js`
- Modify: `app/ui/index.html`
  - **No `#bookCard`:** os botões `#btnBookMove`, `#btnBookRename` e
    `#btnBookReserve`, a lista `#bookMoveList` (role `listbox`, hidden) e o
    formulário `form#bookRenameForm` (hidden) com `#bookRenameInput`.
  - **Menu de contexto:** `#bookMenu` (role `menu`, hidden), dentro de
    `#libraryStage`, com os itens `data-act` `rename`, `move`, `reserve` e `read`.
- Modify: `app/ui/css/style.css`: `.book-menu`, `.book-move-list` e o estado
  `.armed` do botão de Reserva, reaproveitando `.hall-unlink.armed`.
- Test: `tests/test_stream_and_ui.py`

**Interfaces:**
- Consumes: as rotas da Tarefa 3; `api()` e `toast()` (globais do `app.js`);
  `notifyActivity()`.
- Produces: `moveBook(book, shelf, targetShelf)`, `renameBook(book, shelf, newName)`
  e `reserveBook(book, shelf)`. Cada uma devolve uma promessa; no erro, mostra um
  toast com o `detail` e devolve o livro ao lugar.

- [ ] **Step 1: Estender o teste de interface (falha)**

```python
for ident in ("btnBookMove", "btnBookRename", "btnBookReserve", "bookMoveList",
              "bookRenameForm", "bookRenameInput", "bookMenu"):
    assert f'id="{ident}"' in html
for route in ("/api/library/books/move", "/api/library/books/rename", "/api/library/books/reserve"):
    assert route in js
assert "contextmenu" in js
```

- [ ] **Step 2: Rodar e ver falhar.**

- [ ] **Step 3: Implementar**

  - **Arrastar:**
    - `onDown` num livro começa `bookDrag = {hit, x, y, moved: false}` em vez do
      arrasto da câmera;
    - acima de 6 px, `moved` fica verdadeiro e o livro é desenhado no cursor (fora
      da estante);
    - a estante ou o carrinho sob o cursor ganham contorno em latão (`C.brass`);
    - `onUp` sobre outra estante chama `moveBook`; sobre o carrinho, `reserveBook`;
      em qualquer outro lugar, cancela;
    - sem passar de 6 px, o clique continua abrindo o cartão.
  - **Menu de contexto:**
    - `contextmenu` num livro chama `preventDefault`;
    - `#bookMenu` abre na posição do cursor, com foco no primeiro item;
    - Esc ou um clique fora fecham.
  - **Cartão:**
    - «Mover para…» abre `#bookMoveList` com as outras estantes, como botões;
    - «Renomear» mostra o formulário com o nome atual selecionado sem a extensão;
      Enter confirma e Esc cancela;
    - «Mandar para a Reserva» pede dois cliques em até 4 s; no primeiro, mostra
      «Clique de novo para mandar».
  - **Depois do sucesso:**
    - o livro fica `pending = true` (desenhado com opacidade 0,45) até a cena
      pegá-lo;
    - chama `notifyActivity()`.
  - **Se ela não está no salão:** chama `POST /api/library/presence {enter: true}`
    antes, para ela vir fazer o trabalho.

- [ ] **Step 4: Rodar o teste de interface e `node --check app/ui/js/library.js`.**

---

### Task 8: README e verificação no navegador

**Files:**
- Modify: `README.md`: na seção 17, Biblioteca, explicar a porta, a edição à mão e
  as rotas novas na lista da API. Atualizar a contagem de testes.

- [ ] **Step 1: Suíte inteira.** Expected: tudo verde, a linha de base mais os
  testes novos.

- [ ] **Step 2: Preview.**
  - `preview_start` com o servidor `victorique-ui` (porta 8777). A pasta de dados
    de teste já tem três seções.
  - Abrir a aba Biblioteca e conferir que ela entra pela porta.
  - Arrastar um livro de Downloads para Documentos e conferir:
    - o arquivo movido no disco;
    - o lote em `/api/organizer/batches`, ou na rota equivalente que já existe;
    - a cena.
  - Renomear pelo cartão; mandar para a Reserva.
  - Trocar de aba e conferir que ela sai pela porta.
  - Voltar e usar «Chamar a Victorique».
  - Por fim, tirar uma captura.

- [ ] **Step 3: Relatar ao usuário o que não dá para verificar daqui:** a porta e a
  caminhada na área de trabalho de verdade.
