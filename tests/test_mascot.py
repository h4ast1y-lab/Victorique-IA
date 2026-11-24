"""Victorique em miniatura na área de trabalho (app/mascot).

The sprite atlas, the surfaces, the behaviour and the controller are tested
without Windows: the native window, the monitor geometry, the list of open
windows, the cursor and the clock are fakes.
"""
import random

import pytest

from app.mascot import sprite
from app.mascot.balloon import Bubble, Button, plain_text, render_balloon, wrap
from app.mascot.behavior import BLINK_LENGTH, Brain
from app.mascot.bus import MascotBus, mascot_bus
from app.mascot.desktop import DesktopMascot
from app.mascot.sprite import Look
from app.mascot.surfaces import WindowBox, build_world, window_tops

AREA = (0, 0, 1920, 1032)
H = 136


def world(*windows, area=AREA, height=H):
    return build_world(area, height, windows)


FLOOR = world()


# ----------------- Sprite atlas -----------------
ANIMATIONS = {"walk", "moods", "talk", "blink", "sit_down", "sitting", "turn", "stand_up", "held",
              "jump", "fall", "climb", "edge", "peek", "tea", "read", "close_book", "glance",
              "think", "doze"}


def test_every_frame_of_the_atlas_renders_with_its_anchor_inside():
    assert set(sprite.animations()) == ANIMATIONS
    assert sprite.stand_height() == 240
    for anim in sprite.animations():
        assert sprite.facing_of(anim) in ("left", "right", "front")
        for f in range(sprite.frame_count(anim)):
            img, (ax, ay) = sprite.render(Look(anim, f), 120)
            assert img.mode == "RGBA"
            alpha = img.getchannel("A")
            lo, hi = alpha.getextrema()
            assert lo == 0 and hi == 255, (anim, f)        # real transparency around her
            # A climbing frame's anchor is the line of the sheet row, a little
            # below the drawing when her feet are off the ground.
            slack = 2 if anim != "climb" else 30
            assert -2 <= ax <= img.width + 2 and -2 <= ay <= img.height + slack, (anim, f)


def test_standing_frames_have_her_soles_on_the_anchor():
    for anim in ("blink", "walk", "talk", "think", "tea"):
        img, (ax, ay) = sprite.render(Look(anim, 0), H)
        bottom = img.getchannel("A").getbbox()[3]
        assert abs(ay - bottom) <= 2, anim
        assert abs(img.height - H) <= 3, anim
        assert 0.2 * img.width < ax < 0.8 * img.width, anim


def test_facing_mirrors_side_views_only():
    right, (rax, ray) = sprite.render(Look("walk", 2, 1), H)
    left, (lax, lay) = sprite.render(Look("walk", 2, -1), H)
    assert sprite.facing_of("walk") == "left"
    assert sprite.mirrored(Look("walk", 2, 1)) and not sprite.mirrored(Look("walk", 2, -1))
    assert left.size == right.size and ray == lay
    assert abs(lax - (left.width - rax)) <= 1
    for x in (5, left.width // 2, left.width - 6):
        assert left.getpixel((x, 60)) == right.getpixel((left.width - 1 - x, 60))
    # Front views and the dragged frames (they carry a drawn cursor) never flip.
    for anim in ("blink", "held"):
        a, anchor_a = sprite.render(Look(anim, 1, 1), H)
        b, anchor_b = sprite.render(Look(anim, 1, -1), H)
        assert anchor_a == anchor_b and a.tobytes() == b.tobytes()


def test_size_scales_and_the_dragged_anchor_is_her_hand():
    small, _ = sprite.render(Look(), 90)
    big, _ = sprite.render(Look(), 240)
    assert abs(small.height - 90) <= 2 and abs(big.height - 240) <= 2
    img, (ax, ay) = sprite.render(Look("held", 6), H)
    assert img.width * 0.5 < ax < img.width and img.height * 0.3 < ay < img.height * 0.75


def test_sleeping_frame_gets_drifting_zzz():
    plain, (_, ay0) = sprite.render(Look("sitting", 3), H)
    zzz, (_, ay1) = sprite.render(Look("sitting", 3, 1, "zzz", 2), H)
    other, _ = sprite.render(Look("sitting", 3, 1, "zzz", 6), H)
    assert zzz.width > plain.width and zzz.height > plain.height
    assert ay1 - ay0 == zzz.height - plain.height
    assert zzz.tobytes() != other.tobytes()


# ----------------- Surfaces -----------------
def test_window_tops_are_split_by_windows_in_front():
    front = WindowBox(1, 100, 200, 600, 700)
    back = WindowBox(2, 400, 300, 1200, 800)        # its title bar runs behind `front`
    higher = WindowBox(3, 1300, 150, 1800, 500)
    tops = window_tops([front, back, higher], AREA, H)
    spans = {(s.key, s.left, s.right, s.y) for s in tops}
    assert spans == {("w1", 100, 600, 200), ("w2", 600, 1200, 300), ("w3", 1300, 1800, 150)}
    w2 = next(s for s in tops if s.key == "w2")
    assert (w2.wall_left, w2.wall_right, w2.bottom) == (400, 1200, 800)


def test_title_bar_above_a_front_window_stays_walkable():
    front = WindowBox(1, 100, 400, 600, 800)
    back = WindowBox(2, 300, 200, 900, 700)          # sticks out above `front`
    assert {s.key: (s.left, s.right) for s in window_tops([front, back], AREA, H)} == {
        "w1": (100, 600), "w2": (300, 900)}


def test_unusable_windows_are_left_out():
    boxes = [
        WindowBox(1, 0, 0, 1920, 1032, maximized=True),
        WindowBox(2, 100, 30, 900, 600),          # no room above it for her
        WindowBox(3, 100, 1000, 900, 1200),       # down at the taskbar
        WindowBox(4, 100, 400, 160, 800),         # too narrow
        WindowBox(5, 2000, 400, 2600, 800),       # on another monitor
        WindowBox(6, 300, 500, 900, 520),         # a thin strip
    ]
    assert window_tops(boxes, AREA, H) == []
    # A maximized window gives her no floor, but it still hides what is behind it.
    normal = WindowBox(7, 100, 400, 900, 800)
    assert [s.key for s in window_tops([normal, boxes[0]], AREA, H)] == ["w7"]
    assert window_tops([boxes[0], normal], AREA, H) == []


def test_landing_finds_the_highest_surface_crossed():
    w = world(WindowBox(1, 100, 400, 900, 800), WindowBox(2, 500, 600, 1500, 900))
    assert w.landing(700, 300, 700).key == "w1"
    assert w.landing(700, 450, 1100).key == "ground"  # w2's edge is hidden behind w1 there
    assert w.landing(1000, 300, 700).key == "w2"
    assert w.landing(1000, 300, 500) is None
    assert w.ground.y == 1032 and w.find("w2", 1490).key == "w2"
    assert w.find("w2", 1600) is None and w.find("w2", 800) is None


# ----------------- Behaviour -----------------
class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def run(brain, clock, w, seconds, dt=0.04, until=None, **kw):
    for _ in range(int(seconds / dt)):
        clock.t += dt
        brain.step(dt, clock.t, w, **kw)
        if until and until(brain):
            return True
    return False


def test_she_stands_on_the_taskbar_and_walks_within_it():
    clock = Clock()
    brain = Brain(random.Random(7))
    brain.place(FLOOR, clock.t, x=100)
    modes = set()
    for _ in range(9000):
        clock.t += 0.04
        brain.step(0.04, clock.t, FLOOR)
        modes.add(brain.mode)
        assert brain.y == 1032 and brain.surface_key == "ground"
        assert 0 <= brain.x <= 1920
        if brain.mode != "peek":
            assert H * 0.25 <= brain.x <= 1920 - H * 0.25
        brain.look(clock.t)
    assert {"walk", "turn", "idle", "act"} <= modes


def test_no_walking_when_the_preference_is_off():
    clock = Clock()
    brain = Brain(random.Random(3))
    w = world(WindowBox(1, 900, 700, 1500, 1000))
    brain.place(w, clock.t, x=700)
    for _ in range(4000):
        clock.t += 0.04
        brain.step(0.04, clock.t, w, walk=False)
        assert brain.mode not in ("walk", "climb", "air", "crouch", "peek")
    assert brain.x == 700


def test_thinking_stops_her_and_shows_the_thinking_frames():
    clock = Clock()
    brain = Brain(random.Random(1))
    brain.place(FLOOR, clock.t, x=500)
    brain._start_walk(900, clock.t)
    run(brain, clock, FLOOR, 1.0)
    assert brain.mode == "walk"
    brain.set_app_state("pensando")
    run(brain, clock, FLOOR, 0.04)
    assert brain.mode == "idle"
    assert brain.look(clock.t).anim == "think"


def test_sleeps_when_the_app_dozes_and_wakes_sleepy():
    clock = Clock()
    brain = Brain(random.Random(1))
    brain.place(FLOOR, clock.t)
    brain.set_app_state("dormindo")
    assert run(brain, clock, FLOOR, 8, until=lambda b: b.mode == "sleep")
    look = brain.look(clock.t)
    assert look.anim == "sitting" and look.effect == "zzz"
    brain.set_app_state("acordada")
    run(brain, clock, FLOOR, 0.04)
    assert brain.mode == "stand_up" and brain.expression == "sleepy"
    assert run(brain, clock, FLOOR, 2, until=lambda b: b.mode == "idle")


def test_talking_moves_the_mouth():
    clock = Clock()
    brain = Brain(random.Random(1))
    brain.place(FLOOR, clock.t)
    brain.set_app_state("falando")
    frames = set()
    for _ in range(30):
        clock.t += 0.05
        look = brain.look(clock.t)
        assert look.anim == "talk"
        frames.add(look.frame)
    assert len(frames) >= 3


def test_picked_up_she_dangles_then_falls_back_to_the_floor():
    clock = Clock()
    brain = Brain(random.Random(1))
    brain.place(FLOOR, clock.t, x=600)
    brain.grab(clock.t)
    brain.drag_to(800, 400)
    run(brain, clock, FLOOR, 0.04)
    assert (brain.x, brain.y) == (800, 400)
    assert brain.look(clock.t).anim == "held"
    run(brain, clock, FLOOR, 1.0)
    assert brain.look(clock.t).frame >= 4                   # the dangling loop
    brain.release(clock.t)
    assert brain.mode == "air"
    assert run(brain, clock, FLOOR, 4, dt=0.02, until=lambda b: b.mode == "land")
    assert brain.y == 1032 and brain.x == pytest.approx(800 - H * 0.3)
    assert brain.expression == "annoyed"                     # a hard landing
    assert brain.look(clock.t).anim == "fall"


def test_a_flick_throws_her_but_she_stays_on_screen():
    clock = Clock()
    brain = Brain(random.Random(1))
    brain.place(FLOOR, clock.t, x=600)
    brain.grab(clock.t)
    brain.drag_to(1700, 500)
    brain.release(clock.t, vx=5000, vy=-5000)
    assert brain.vx == 1800 and brain.vy == -1800           # clamped
    xs = []
    assert run(brain, clock, FLOOR, 6, dt=0.02, until=lambda b: xs.append(b.x) or b.mode == "land")
    assert max(xs) <= 1920 and brain.y == 1032


def test_floor_moving_up_or_down():
    clock = Clock()
    brain = Brain(random.Random(1))
    brain.place(FLOOR, clock.t, x=600)
    brain.step(0.04, clock.t, world(area=(0, 0, 1920, 900)))     # taskbar got taller
    assert brain.y == 900
    brain.step(0.04, clock.t, world(area=(0, 0, 1920, 1080)))    # auto-hide taskbar: she falls
    assert brain.mode == "air"


def _drop_onto(brain, clock, w, x, y=150):
    if not brain.placed:
        brain.place(w, clock.t)
    brain.grab(clock.t)
    brain.drag_to(x + H * 0.3, y - H * 0.5)
    brain.release(clock.t)
    assert run(brain, clock, w, 4, dt=0.02, until=lambda b: b.mode == "land")


def test_dropped_over_a_window_she_lands_on_its_title_bar_and_rides_it():
    clock = Clock()
    brain = Brain(random.Random(4))
    win = WindowBox(42, 400, 500, 1200, 900)
    brain.place(world(win), clock.t)
    _drop_onto(brain, clock, world(win), 700)
    assert brain.surface_key == "w42" and brain.y == 500 and brain.on_window() == "w42"
    # The window is dragged: she rides along.
    x0 = brain.x
    moved = WindowBox(42, 520, 430, 1320, 830)
    run(brain, clock, world(moved), 0.04, walk=False)
    assert brain.y == 430 and brain.x == pytest.approx(x0 + 120)
    # Standing still on it for a while, she never leaves its top.
    for _ in range(1500):
        clock.t += 0.04
        brain.step(0.04, clock.t, world(moved), climb=False)
        if brain.mode in ("idle", "walk", "edge", "sit", "act", "turn"):
            assert brain.surface_key == "w42" and brain.y == 430
            assert 520 <= brain.x <= 1320
    # It closes: she falls to the taskbar.
    brain._idle(clock.t, 50, 60)
    run(brain, clock, FLOOR, 0.04)
    assert brain.mode == "air"
    assert run(brain, clock, FLOOR, 4, dt=0.02, until=lambda b: b.mode == "land")
    assert brain.surface_key == "ground" and brain.y == 1032


def test_a_window_in_front_covering_her_spot_makes_her_fall():
    clock = Clock()
    brain = Brain(random.Random(4))
    win = WindowBox(42, 400, 500, 1200, 900)
    _drop_onto(brain, clock, world(win), 700)
    cover = WindowBox(7, 300, 300, 1000, 800)
    run(brain, clock, world(cover, win), 0.04, walk=False)
    assert brain.mode == "air"


def test_she_climbs_the_side_of_a_window():
    clock = Clock()
    brain = Brain(random.Random(2))
    w = world(WindowBox(9, 800, 700, 1400, 1010))
    brain.place(w, clock.t, x=300)
    options = brain._climb_options(w, w.ground)
    assert {o["side"] for o in options} == {"left", "right"}
    plan = next(o for o in options if o["side"] == "left")
    brain._start_walk(plan["x"], clock.t, plan)
    seen = set()
    assert run(brain, clock, w, 40, until=lambda b: seen.add(b.mode) or b.mode == "arrive")
    assert {"walk", "climb"} <= seen
    assert brain.surface_key == "w9" and brain.y == 700 and 800 < brain.x < 900
    assert brain.look(clock.t).anim == "climb"


def test_she_jumps_up_onto_a_lower_window_and_hops_down():
    clock = Clock()
    brain = Brain(random.Random(2))
    w = world(WindowBox(5, 300, 950, 900, 1300))
    brain.place(w, clock.t, x=1000)
    options = brain._jump_options(w, w.ground)
    assert len(options) == 1
    land_x, land_y = options[0]
    brain._launch(land_x, land_y, clock.t)
    styles = set()
    assert run(brain, clock, w, 4, dt=0.02, until=lambda b: styles.add(b.look(clock.t).anim) or b.mode == "land")
    assert brain.surface_key == "w5" and brain.y == 950
    assert brain.x == pytest.approx(land_x, abs=H * 0.2)
    assert "jump" in styles and brain.expression != "annoyed"
    # Hop down to the taskbar.
    brain._idle(clock.t, 0, 0)
    brain._start_walk(320, clock.t, {"kind": "hop", "dir": -1})
    assert run(brain, clock, w, 30, dt=0.02, until=lambda b: b.surface_key == "ground" and b.mode == "land")
    assert brain.y == 1032


def test_a_long_life_among_moving_windows_keeps_her_on_something():
    for seed in (11, 12, 13):
        rng = random.Random(seed)
        clock = Clock()
        brain = Brain(random.Random(seed))
        wins = [WindowBox(1, 200, 600, 900, 1032), WindowBox(2, 700, 420, 1300, 900),
                WindowBox(3, 1350, 760, 1800, 1032)]
        w = world(*wins)
        brain.place(w, clock.t, x=1500)
        visited = set()
        for i in range(30000):
            clock.t += 0.04
            if i % 2500 == 2499:                      # someone moves a window around
                k = rng.randrange(len(wins))
                b = wins[k]
                dx, dy = rng.randint(-150, 150), rng.randint(-120, 120)
                wins[k] = WindowBox(b.hwnd, b.left + dx, b.top + dy, b.right + dx, b.bottom + dy)
                w = world(*wins)
            brain.step(0.04, clock.t, w)
            brain.look(clock.t)
            visited.add(brain.surface_key)
            if brain.mode in ("idle", "walk", "sit", "edge", "act"):
                here = w.find(brain.surface_key, brain.x, H * 0.15) if brain.surface_key != "ground" else w.ground
                assert here is not None and brain.y == here.y, (seed, i, brain.mode, brain.surface_key)
        assert "ground" in visited and visited & {"w1", "w2", "w3"}, seed


def test_model_expression_lingers_then_returns_to_neutral():
    clock = Clock()
    brain = Brain(random.Random(1))
    brain.place(FLOOR, clock.t)
    brain.set_expression("invented", clock.t)
    assert brain.expression == "neutral"
    brain.set_expression("deduction", clock.t)
    assert brain.look(clock.t) == Look("think", 4, brain.facing)
    brain.set_gesture("tea", clock.t)
    run(brain, clock, FLOOR, 0.04)
    assert brain.mode == "act" and brain.look(clock.t).anim == "tea"
    clock.t += 23
    brain.step(0.04, clock.t, FLOOR)
    assert brain.expression == "neutral"


def test_poke_gives_a_reaction_and_blinks_happen():
    clock = Clock()
    brain = Brain(random.Random(2))
    brain.place(FLOOR, clock.t)
    brain.poke(clock.t)
    assert brain.expression in ("embarrassed", "annoyed")
    brain.expression_until = clock.t
    blinks = 0
    for _ in range(400):
        clock.t += BLINK_LENGTH / 2
        blinks += brain.look(clock.t) == Look("blink", 3, brain.facing)
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
    hwnd = 777

    def __init__(self, on_event, interval_ms=40):
        self.on_event = on_event
        self.updates = []
        self.visible = False
        self.hand_cursor = False
        self.cursor_hidden = []
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

    def hide_cursor(self, hidden):
        self.cursor_hidden.append(hidden)

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


def make_mascot(prefs=None, foreground=None, windows=()):
    clock = Clock()
    cursor = {"pos": (0, 0)}
    state = {"prefs": dict(prefs or {}), "fg": foreground, "windows": list(windows), "excluded": []}

    def list_windows(exclude=()):
        state["excluded"].append(list(exclude))
        return list(state["windows"])

    def one_window(hwnd):
        return next((w for w in state["windows"] if w.hwnd == hwnd), None)

    m = DesktopMascot(
        FakeBridge(),
        prefs_loader=lambda: state["prefs"],
        prefs_saver=lambda changes: state["prefs"].update(changes),
        life=FakeLife(),
        window_factory=FakeWindow,
        area_fn=lambda x, y: (AREA, 1.0),
        cursor_fn=lambda: cursor["pos"],
        foreground_fn=lambda: state["fg"],
        windows_fn=list_windows,
        window_box_fn=one_window,
        clock=clock,
        rng=random.Random(5),
    )
    return m, clock, cursor, state


def tick(m, clock, n=1):
    for _ in range(n):
        clock.t += 0.04
        m._on_event("tick")


def test_she_appears_on_top_of_the_taskbar():
    m, clock, _c, state = make_mascot()
    tick(m, clock)
    img, x, y = m.window.updates[-1]
    assert m.on_screen and m.brain.y == 1032
    bottom = img.getchannel("A").getbbox()[3]
    assert abs(y + bottom - 1032) <= 2
    assert 0 <= x and x + img.width <= 1920
    assert state["excluded"][0] == [FakeWindow.hwnd]        # never stands on herself


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


def _drag(m, clock, cursor, to, steps=4):
    """Presses on her, drags to the screen point `to` and lets go."""
    px, py = _sprite_point(m)
    wx, wy = m.window.updates[-1][1:]
    start = (wx + px, wy + py)
    cursor["pos"] = start
    m._on_event("down", px, py)
    for k in range(1, steps + 1):
        clock.t += 0.02
        cx = start[0] + (to[0] - start[0]) * k // steps
        cy = start[1] + (to[1] - start[1]) * k // steps
        cursor["pos"] = (cx, cy)
        m._on_event("move", cx - wx, cy - wy)
    m._on_event("up", to[0] - wx, to[1] - wy)


def test_drag_by_the_hand_and_drop_then_click_and_double_click():
    m, clock, cursor, _s = make_mascot()
    tick(m, clock)
    px, py = _sprite_point(m)
    wx, wy = m.window.updates[-1][1:]
    cursor["pos"] = (wx + px, wy + py)
    m._on_event("down", px, py)
    cursor["pos"] = (wx + px + 40, wy + py - 200)
    m._on_event("move", px + 40, py - 200)
    assert m.brain.mode == "held" and m.window.cursor_hidden == [True]
    assert (m.brain.x, m.brain.y) == cursor["pos"]          # the drawn cursor's tip follows the real one
    tick(m, clock)
    img, x, y = m.window.updates[-1]
    _, (ax, ay) = sprite.render(m.brain.look(clock.t), 136)
    assert (x + ax, y + ay) == cursor["pos"]
    m._on_event("up", px + 40, py - 200)
    assert m.brain.mode == "air" and m.window.cursor_hidden == [True, False]
    tick(m, clock, 60)
    assert m.brain.y == 1032
    # A plain click: a reaction, not a drag.
    tick(m, clock)
    px, py = _sprite_point(m)
    wx, wy = m.window.updates[-1][1:]
    cursor["pos"] = (wx + px, wy + py)
    m._on_event("down", px, py)
    m._on_event("up", px, py)
    assert m.brain.expression in ("embarrassed", "annoyed")
    m._on_event("dblclick", px, py)
    assert ("open_chat",) in m.bridge.calls


def test_a_quick_drag_throws_her():
    m, clock, cursor, _s = make_mascot()
    tick(m, clock)
    start_x = m.brain.x
    _drag(m, clock, cursor, (1000, 300))                   # up and to the left, fast
    assert start_x > 1500
    assert m.brain.mode == "air" and m.brain.vx < -500 and m.brain.vy < -500


def test_dropped_on_a_window_she_rides_it_and_falls_when_it_closes():
    win = WindowBox(4242, 500, 500, 1300, 900)
    m, clock, cursor, state = make_mascot(windows=[win])
    tick(m, clock)
    _drag(m, clock, cursor, (900, 200), steps=1)
    tick(m, clock, 60)
    assert m.brain.surface_key == "w4242" and m.brain.y == 500
    x0 = m.brain.x
    state["windows"] = [WindowBox(4242, 560, 470, 1360, 870)]
    tick(m, clock)                                         # re-read every tick while she stands on it
    assert m.brain.y == 470 and m.brain.x == pytest.approx(x0 + 60)
    state["windows"] = []
    tick(m, clock, 80)
    assert m.brain.surface_key == "ground" and m.brain.y == 1032


def test_windows_are_ignored_when_climbing_is_off():
    win = WindowBox(4242, 500, 500, 1300, 900)
    m, clock, cursor, state = make_mascot(prefs={"mascot_climb": False}, windows=[win])
    tick(m, clock)
    _drag(m, clock, cursor, (900, 200), steps=1)
    tick(m, clock, 80)
    assert m.brain.surface_key == "ground" and m.brain.y == 1032
    assert state["excluded"] == []


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
