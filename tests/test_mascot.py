"""Victorique em miniatura na área de trabalho (app/mascot).

The drawing, the behaviour and the controller are tested without Windows:
the native window, the monitor geometry, the cursor and the clock are fakes.
"""
import random

import pytest

from app.core.avatar_protocol import EXPRESSIONS, GESTURES
from app.mascot import sprite
from app.mascot.balloon import Bubble, Button, plain_text, render_balloon, wrap
from app.mascot.behavior import BLINK_LENGTH, Brain, Floor
from app.mascot.bus import MascotBus, mascot_bus
from app.mascot.desktop import DesktopMascot
from app.mascot.sprite import Look

FLOOR = Floor(0, 1920, 1032)


# ----------------- Sprite -----------------
def test_every_pose_expression_and_prop_renders_with_real_transparency():
    looks = [Look(pose=p) for p in sprite.POSES]
    looks += [Look(expression=e) for e in EXPRESSIONS]
    looks += [Look(prop=p, prop_frame=3) for p in sprite.PROPS]
    looks += [Look(eyes="blink"), Look(eyes="closed"), Look(mouth="talk1"), Look(mouth="talk2")]
    looks += [Look(pose="walk", frame=f) for f in range(sprite.WALK_FRAMES)]
    for look in looks:
        img = sprite.render(look, 120)
        assert img.mode == "RGBA"
        assert img.size == sprite.size_for(120)
        assert img.getpixel((0, 0))[3] == 0, look            # corners show the desktop
        assert img.getpixel((img.width // 2, int(img.height * 0.66)))[3] == 255, look  # her dress


def test_facing_left_is_a_mirror_and_size_scales():
    look = Look(prop="pipe")
    right = sprite.render_facing(look, 140, 1)
    left = sprite.render_facing(look, 140, -1)
    assert left.size == right.size
    assert left.getpixel((left.width - 1 - 80, 60)) == right.getpixel((80, 60))
    assert sprite.size_for(240)[1] == 240 and sprite.size_for(90)[1] == 90
    assert 0 <= sprite.feet_offset(136) < 6


# ----------------- Behaviour -----------------
class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_she_stands_on_the_floor_and_walks_within_it():
    clock = Clock()
    brain = Brain(random.Random(7))
    brain.place(FLOOR, clock.t, x=100)
    seen_walk = False
    for _ in range(6000):
        clock.t += 0.04
        brain.step(0.04, clock.t, FLOOR, 45)
        assert 45 <= brain.x <= FLOOR.right - 45
        assert brain.y == FLOOR.y
        seen_walk = seen_walk or brain.mode == "walk"
    assert seen_walk


def test_no_walking_when_the_preference_is_off():
    clock = Clock()
    brain = Brain(random.Random(3))
    brain.place(FLOOR, clock.t, x=700)
    for _ in range(4000):
        clock.t += 0.04
        brain.step(0.04, clock.t, FLOOR, 45, walk=False)
        assert brain.mode != "walk"
    assert brain.x == 700


def test_thinking_stops_her_with_the_pipe():
    clock = Clock()
    brain = Brain(random.Random(1))
    brain.place(FLOOR, clock.t, x=500)
    brain.mode, brain.target_x = "walk", 900
    brain.set_app_state("pensando")
    clock.t += 0.04
    brain.step(0.04, clock.t, FLOOR, 45)
    look, _ = brain.look(clock.t)
    assert brain.mode == "idle"
    assert look.prop == "pipe" and look.expression == "focused"


def test_sleeps_when_the_app_dozes_and_wakes_sleepy():
    clock = Clock()
    brain = Brain(random.Random(1))
    brain.place(FLOOR, clock.t)
    brain.set_app_state("dormindo")
    clock.t += 0.04
    brain.step(0.04, clock.t, FLOOR, 45)
    look, _ = brain.look(clock.t)
    assert look.pose == "sleep" and look.eyes == "closed" and look.prop == "zzz"
    brain.set_app_state("acordada")
    clock.t += 0.04
    brain.step(0.04, clock.t, FLOOR, 45)
    assert brain.mode == "idle" and brain.expression == "sleepy"


def test_talking_moves_the_mouth():
    clock = Clock()
    brain = Brain(random.Random(1))
    brain.place(FLOOR, clock.t)
    brain.set_app_state("falando")
    mouths = set()
    for _ in range(20):
        clock.t += 0.05
        mouths.add(brain.look(clock.t)[0].mouth)
    assert {"talk1", "talk2"} <= mouths


def test_picked_up_she_dangles_then_falls_back_to_the_floor():
    clock = Clock()
    brain = Brain(random.Random(1))
    brain.place(FLOOR, clock.t, x=600)
    brain.grab(clock.t)
    brain.drag_to(800, 400)
    clock.t += 0.04
    brain.step(0.04, clock.t, FLOOR, 45)
    assert (brain.x, brain.y) == (800, 400)
    assert brain.look(clock.t)[0].pose == "held"
    brain.release(clock.t)
    for _ in range(200):
        clock.t += 0.02
        brain.step(0.02, clock.t, FLOOR, 45)
        if brain.mode == "land":
            break
    assert brain.mode == "land" and brain.y == FLOOR.y and brain.x == 800
    assert brain.expression == "annoyed"  # a hard landing


def test_floor_moving_up_or_down():
    clock = Clock()
    brain = Brain(random.Random(1))
    brain.place(FLOOR, clock.t, x=600)
    higher = Floor(0, 1920, 900)       # taskbar got taller: she steps up
    brain.step(0.04, clock.t, higher, 45)
    assert brain.y == 900
    lower = Floor(0, 1920, 1080)       # auto-hide taskbar: she falls
    brain.step(0.04, clock.t, lower, 45)
    assert brain.mode == "fall"


def test_model_expression_lingers_then_returns_to_neutral():
    clock = Clock()
    brain = Brain(random.Random(1))
    brain.place(FLOOR, clock.t)
    brain.set_expression("invented", clock.t)
    assert brain.expression == "neutral"
    brain.set_expression("deduction", clock.t)
    brain.set_gesture("tea", clock.t)
    assert brain.look(clock.t)[0].prop == "tea"
    clock.t += 23
    look, _ = brain.look(clock.t)
    assert look.expression == "neutral" and look.prop is None


def test_poke_gives_a_reaction_and_blinks_happen():
    clock = Clock()
    brain = Brain(random.Random(2))
    brain.place(FLOOR, clock.t)
    brain.poke(clock.t)
    assert brain.expression in ("embarrassed", "annoyed")
    assert brain.gesture == "hair-adjust"
    blinks = 0
    for _ in range(400):
        clock.t += BLINK_LENGTH / 2
        blinks += brain.look(clock.t)[0].eyes == "blink"
    assert blinks > 0


# ----------------- Balloon -----------------
def test_wrap_respects_the_width_and_breaks_long_paths():
    lines = wrap("Uma frase *com gesto* e C:\\Users\\alguem\\Downloads\\um-nome-de-arquivo-muito-comprido.txt", 160, 13)
    assert len(lines) >= 2
    assert any(it for line in lines for _w, it in line)


def test_balloon_buttons_and_close_are_clickable_areas():
    bubble = Bubble(text="Hmph.", tag="entediada", case_title="O relógio",
                    buttons=(Button("later", "Depois"), Button("accept", "Aceitar o Caso", True)))
    img, rects = render_balloon(bubble, 1.0)
    assert set(rects) == {"close", "later", "accept"}
    for x0, y0, x1, y1 in rects.values():
        assert 0 <= x0 < x1 <= img.width and 0 <= y0 < y1 <= img.height
    assert img.getpixel((0, img.height - 1))[3] == 0  # rounded corner / tail area is transparent


def test_plain_text_strips_markdown():
    text = plain_text("# Título\n**negrito** e `código` e [link](http://x)\n- item\n```py\nx=1\n```")
    assert "#" not in text and "**" not in text and "`" not in text and "http" not in text
    assert "• item" in text


# ----------------- Controller (fake window) -----------------
class FakeWindow:
    def __init__(self, on_event, interval_ms=40):
        self.on_event = on_event
        self.updates = []
        self.visible = False
        self.hand_cursor = False
        self.menu_choice = 0
        self.menu = None

    def start(self):
        pass

    def close(self):
        pass

    def update(self, img, x, y):
        self.updates.append((img, x, y))
        self.visible = True

    def set_visible(self, visible):
        self.visible = visible

    def keep_on_top(self):
        pass

    def popup_menu(self, items, x, y):
        self.menu = items
        return self.menu_choice


class FakeLife:
    def __init__(self):
        self.silenced = []

    def silence(self, minutes):
        self.silenced.append(minutes)
        return 1_900_000_000

    def resume(self):
        pass

    def status(self):
        return {}


class FakeBridge:
    def __init__(self):
        self.calls = []

    def open_chat(self):
        self.calls.append(("open_chat",))

    def accept_case(self, event):
        self.calls.append(("accept_case", event))

    def quit(self):
        self.calls.append(("quit",))


def make_mascot(prefs=None, foreground=None):
    clock = Clock()
    cursor = {"pos": (0, 0)}
    state = {"prefs": dict(prefs or {}), "fg": foreground}
    m = DesktopMascot(
        FakeBridge(),
        prefs_loader=lambda: state["prefs"],
        prefs_saver=lambda changes: state["prefs"].update(changes),
        life=FakeLife(),
        window_factory=FakeWindow,
        area_fn=lambda x, y: ((0, 0, 1920, 1032), 1.0),
        cursor_fn=lambda: cursor["pos"],
        foreground_fn=lambda: state["fg"],
        clock=clock,
        rng=random.Random(5),
    )
    return m, clock, cursor, state


def tick(m, clock, n=1):
    for _ in range(n):
        clock.t += 0.04
        m._on_event("tick")


def test_she_appears_on_top_of_the_taskbar():
    m, clock, _c, _s = make_mascot()
    tick(m, clock)
    img, x, y = m.window.updates[-1]
    assert m.on_screen
    assert y + img.height - sprite.feet_offset(136) == 1032
    assert 0 <= x and x + img.width <= 1920


def test_tedio_balloon_accept_reaches_the_chat_window():
    m, clock, cursor, _s = make_mascot()
    tick(m, clock)
    event = {"category": "tedio", "text": "Estou entediada.", "case": {"titulo": "O relógio", "pergunta": "Por quê?"}}
    m.post("say", event)
    tick(m, clock)
    bx, by, _img, rects = m._layout["balloon"]
    x0, y0, x1, y1 = rects["accept"]
    px, py = bx + (x0 + x1) // 2, by + (y0 + y1) // 2
    m._on_event("down", px, py)
    m._on_event("up", px, py)
    assert m.bridge.calls == [("accept_case", event)]
    assert m.shown is None


def test_silence_button_silences_and_says_so():
    m, clock, _c, _s = make_mascot()
    tick(m, clock)
    m.post("say", {"category": "bagunca", "text": "Que bagunça."})
    tick(m, clock)
    bx, by, _img, rects = m._layout["balloon"]
    x0, y0, x1, y1 = rects["silence"]
    m._on_event("down", bx + x0 + 3, by + y0 + 3)
    m._on_event("up", bx + x0 + 3, by + y0 + 3)
    assert m.life.silenced == [120]
    assert m.shown and m.shown.kind == "note" and "Silêncio até" in m.shown.bubble.text


def _sprite_point(m):
    sx, sy, img = m._layout["sprite"]
    return sx + img.width // 2, sy + int(img.height * 0.66)


def test_drag_and_drop_then_click_and_double_click():
    m, clock, cursor, _s = make_mascot()
    tick(m, clock)
    px, py = _sprite_point(m)
    wx, wy = m.window.updates[-1][1:]
    cursor["pos"] = (wx + px, wy + py)
    m._on_event("down", px, py)
    cursor["pos"] = (wx + px + 40, wy + py - 200)
    m._on_event("move", px + 40, py - 200)
    assert m.brain.mode == "held"
    m._on_event("up", px + 40, py - 200)
    assert m.brain.mode == "fall"
    tick(m, clock, 60)
    assert m.brain.y == 1032
    # A plain click: a reaction, not a drag.
    tick(m, clock)
    px, py = _sprite_point(m)
    wx, wy = m.window.updates[-1][1:]
    cursor["pos"] = (wx + px, wy + py)
    m._on_event("down", px, py)
    m._on_event("up", px, py)
    assert m.brain.gesture == "hair-adjust"
    m._on_event("dblclick", px, py)
    assert ("open_chat",) in m.bridge.calls


def test_transparent_pixels_are_not_hits():
    m, clock, _c, _s = make_mascot()
    tick(m, clock)
    assert m._hit(0, 0) is None


def test_hidden_in_fullscreen_and_when_disabled():
    m, clock, _c, state = make_mascot(foreground={"fullscreen": True, "own": False})
    tick(m, clock)
    assert not m.window.visible and not m.on_screen
    state["fg"] = None
    clock.t += 1.1
    tick(m, clock)
    assert m.window.visible
    state["prefs"]["mascot_enabled"] = False
    clock.t += 2.1
    tick(m, clock)
    assert not m.window.visible and not m.enabled


def test_reply_excerpt_and_menu_actions():
    m, clock, _c, state = make_mascot(prefs={"mascot_replies": True})
    tick(m, clock)
    m.post("reply", "**Resposta** longa " + "palavra " * 200)
    tick(m, clock)
    assert m.shown.kind == "reply" and m.shown.bubble.text.endswith("…") and "**" not in m.shown.bubble.text
    m.window.menu_choice = 2  # "Ficar parada aqui"
    m._on_event("rclick", *_sprite_point(m))
    assert state["prefs"]["mascot_walk"] is False
    m.window.menu_choice = 6  # "Encerrar o assistente"
    m._on_event("rclick", *_sprite_point(m))
    assert ("quit",) in m.bridge.calls


def test_replies_can_be_turned_off():
    m, clock, _c, _s = make_mascot(prefs={"mascot_replies": False})
    tick(m, clock)
    m.post("reply", "Oi")
    tick(m, clock)
    assert m.shown is None


# ----------------- Bus and API -----------------
class FakeMascot:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.on_screen = True
        self.posted = []

        class B:
            app_state = "acordada"
            mode = "idle"
        self.brain = B()

    def post(self, kind, payload=None):
        self.posted.append((kind, payload))


def test_bus_without_a_mascot_is_a_no_op():
    bus = MascotBus()
    assert bus.say({"text": "x"}) is False
    assert bus.signal("pensando") is False
    assert bus.status()["running"] is False


@pytest.fixture
def fake_mascot():
    m = FakeMascot()
    mascot_bus.attach(m)
    yield m
    mascot_bus.detach(m)


def test_api_routes_lines_and_signals_to_the_mascot(client, fake_mascot):
    r = client.post("/api/mascot/say", json={"category": "tedio", "text": "Oi",
                                             "case": {"titulo": "T", "pergunta": "P"}})
    assert r.json() == {"shown": True}
    r = client.post("/api/mascot/signal", json={"state": "pensando", "expression": "invented",
                                                "gesture": "tea"})
    assert r.json() == {"delivered": True}
    assert ("state", "pensando") in fake_mascot.posted
    assert ("avatar", {"expression": None, "gesture": "tea"}) in fake_mascot.posted
    assert client.post("/api/mascot/reply", json={"text": "Feito."}).json() == {"shown": True}
    status = client.get("/api/mascot/status").json()
    assert status["running"] and status["active"] and status["visible"]
    assert client.post("/api/mascot/command", json={"action": "rm -rf"}).status_code == 422


def test_life_tick_counts_the_mascot_as_visible(client, fake_mascot, monkeypatch):
    seen = {}

    async def fake_tick(ui):
        seen.update(ui)
        return {"status": {}, "event": None}

    monkeypatch.setattr("app.main.life_service.tick", fake_tick)
    r = client.post("/api/life/tick", json={"visible": False})
    assert r.json()["mascot"] is True
    assert seen["visible"] is True


def test_disabled_mascot_leaves_the_page_balloon(client):
    m = FakeMascot(enabled=False)
    mascot_bus.attach(m)
    try:
        assert client.post("/api/mascot/say", json={"category": "tarde", "text": "Tarde."}).json() == {"shown": False}
    finally:
        mascot_bus.detach(m)
