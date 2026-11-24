"""
The desktop mascot: Victorique in miniature walking on top of the taskbar.

Ties together the behaviour (behavior.Brain), the drawing (sprite, balloon)
and the native window (win32.LayeredWindow). Everything runs on the window's
own thread, driven by its timer; other threads talk to it through `post`
(see bus.MascotBus). The chat window is reached through a small `bridge`
object supplied by run.py (open_chat, accept_case, quit).

Interactions: drag her around (she falls back to the taskbar), click for a
reaction, double-click to open the chat, right-click for a menu. Her balloon
carries the "vida própria" lines and, when the chat window is not in front,
a short excerpt of a finished reply.
"""
from __future__ import annotations

import logging
import queue
import random
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple

from PIL import Image

from app.mascot import sprite
from app.mascot.balloon import WIDTH as BALLOON_WIDTH, Bubble, Button, plain_text, render_balloon
from app.mascot.behavior import Brain, Floor, wobble
from app.mascot.bus import mascot_bus

logger = logging.getLogger(__name__)

TICK_MS = 40
PREFS_EVERY = 2.0
FULLSCREEN_EVERY = 1.0
TOPMOST_EVERY = 5.0
DRAG_THRESHOLD = 5
REPLY_CHARS = 320
LIFE_TAGS = {
    "tedio": "entediada", "tarde": "hora tardia", "bagunca": "sobre uma pasta",
    "organizado": "organização concluída", "retorno": "de volta",
}
LIFE_EXPRESSIONS = {
    "tedio": "sleepy", "tarde": "concerned", "bagunca": "skeptical",
    "organizado": "happy", "retorno": "neutral",
}
SILENCE_MINUTES = 120

MENU_OPEN, MENU_STAY, MENU_SILENCE, MENU_DND, MENU_HIDE, MENU_QUIT = 1, 2, 3, 4, 5, 6

DEFAULT_PREFS = {
    "mascot_enabled": True, "mascot_size": 136, "mascot_walk": True, "mascot_replies": True,
    "mascot_hide_fullscreen": True, "life_dnd": False,
}


@dataclass
class Shown:
    """The balloon on screen and what it is for."""
    bubble: Bubble
    kind: str                    # life, reply, note
    until: float
    event: Optional[Dict[str, Any]] = None


class DesktopMascot:
    def __init__(self, bridge: Any = None, *,
                 prefs_loader: Optional[Callable[[], Dict[str, Any]]] = None,
                 prefs_saver: Optional[Callable[[Dict[str, Any]], Any]] = None,
                 life: Any = None,
                 window_factory: Optional[Callable[..., Any]] = None,
                 area_fn: Optional[Callable[[int, int], Tuple[Tuple[int, int, int, int], float]]] = None,
                 cursor_fn: Optional[Callable[[], Tuple[int, int]]] = None,
                 foreground_fn: Optional[Callable[[], Optional[Dict[str, Any]]]] = None,
                 clock: Callable[[], float] = time.monotonic,
                 rng: Optional[random.Random] = None):
        if window_factory is None or area_fn is None or cursor_fn is None:
            from app.mascot import win32
            window_factory = window_factory or win32.LayeredWindow
            area_fn = area_fn or win32.work_area_at
            cursor_fn = cursor_fn or win32.cursor_pos
        if foreground_fn is None:
            from app.life.observer import foreground_window as foreground_fn
        if prefs_loader is None or prefs_saver is None:
            from app.core import preferences
            prefs_loader = prefs_loader or preferences.load
            prefs_saver = prefs_saver or preferences.update
        if life is None:
            from app.life.service import life_service as life
        self.bridge = bridge
        self.prefs_loader = prefs_loader
        self.prefs_saver = prefs_saver
        self.life = life
        self.area_fn = area_fn
        self.cursor_fn = cursor_fn
        self.foreground_fn = foreground_fn
        self.clock = clock
        self.window = window_factory(self._on_event, interval_ms=TICK_MS)
        self.brain = Brain(rng)
        self.inbox: "queue.Queue[Tuple[str, Any]]" = queue.Queue()
        self.prefs: Dict[str, Any] = dict(DEFAULT_PREFS)
        self.shown: Optional[Shown] = None
        self.hover: Optional[str] = None
        self.fullscreen_hidden = False
        self.on_screen = False
        self._last_tick = 0.0
        self._next_prefs = 0.0
        self._next_fullscreen = 0.0
        self._next_topmost = 0.0
        self._last_frame: Optional[tuple] = None
        self._layout: Dict[str, Any] = {}
        self._press: Optional[Dict[str, Any]] = None
        self._dragging = False
        self._balloon_cache: Dict[tuple, Tuple[Image.Image, Dict[str, tuple]]] = {}
        self._load_prefs()

    # ----------------- Lifecycle and cross-thread API -----------------
    @property
    def enabled(self) -> bool:
        return bool(self.prefs.get("mascot_enabled", True))

    def start(self) -> None:
        self.window.start()
        mascot_bus.attach(self)

    def stop(self) -> None:
        mascot_bus.detach(self)
        self.window.close()

    def post(self, kind: str, payload: Any = None) -> None:
        """Thread-safe: queue something for the window thread."""
        self.inbox.put((kind, payload))

    # ----------------- Window events -----------------
    def _on_event(self, name: str, *args) -> None:
        handler = getattr(self, f"_ev_{name}", None)
        if handler:
            handler(*args)

    def _ev_tick(self) -> None:
        now = self.clock()
        dt = now - self._last_tick if self._last_tick else TICK_MS / 1000.0
        self._last_tick = now
        self._drain(now)
        if now >= self._next_prefs:
            self._load_prefs()
            self._next_prefs = now + PREFS_EVERY
        if now >= self._next_fullscreen:
            self.fullscreen_hidden = self._fullscreen_in_front()
            self._next_fullscreen = now + FULLSCREEN_EVERY
        show = self.enabled and not self.fullscreen_hidden
        if not show:
            self.window.set_visible(False)
            self.on_screen = False
            self._last_frame = None
            return
        self._frame(now, dt)
        if now >= self._next_topmost:
            self.window.keep_on_top()
            self._next_topmost = now + TOPMOST_EVERY

    def _ev_down(self, x: int, y: int) -> None:
        target = self._hit(x, y)
        if target is None:
            return
        kind, ident = target
        cx, cy = self.cursor_fn()
        self._press = {"kind": kind, "id": ident, "start": (cx, cy),
                       "offset": (self.brain.x - cx, self.brain.y - cy)}
        self._dragging = False

    def _ev_move(self, x: int, y: int) -> None:
        press = self._press
        if press and press["kind"] == "sprite":
            cx, cy = self.cursor_fn()
            sx, sy = press["start"]
            if not self._dragging and max(abs(cx - sx), abs(cy - sy)) >= DRAG_THRESHOLD:
                self._dragging = True
                self.brain.grab(self.clock())
            if self._dragging:
                ox, oy = press["offset"]
                self.brain.drag_to(cx + ox, cy + oy)
            return
        target = self._hit(x, y)
        hover = target[1] if target and target[0] == "button" else None
        if hover != self.hover:
            self.hover = hover
            self._last_frame = None
        self.window.hand_cursor = bool(target and target[0] in ("button", "sprite"))

    def _ev_up(self, x: int, y: int) -> None:
        press, self._press = self._press, None
        now = self.clock()
        if self._dragging:
            self._dragging = False
            self.brain.release(now)
            return
        if not press:
            return
        target = self._hit(x, y)
        if press["kind"] == "sprite":
            self.brain.poke(now)
        elif press["kind"] == "button" and target == ("button", press["id"]):
            self._button(press["id"])
        elif press["kind"] == "balloon" and self.shown and self.shown.kind == "reply":
            self._button("open")

    def _ev_lost_capture(self) -> None:
        if self._dragging:
            self._dragging = False
            self._press = None
            self.brain.release(self.clock())

    def _ev_dblclick(self, x: int, y: int) -> None:
        target = self._hit(x, y)
        if target and target[0] == "sprite":
            self._open_chat()

    def _ev_rclick(self, x: int, y: int) -> None:
        if self._hit(x, y) is None:
            return
        self._menu(*self.cursor_fn())

    def _ev_leave(self) -> None:
        if self.hover:
            self.hover = None
            self._last_frame = None
        self.window.hand_cursor = False

    # ----------------- Inbox -----------------
    def _drain(self, now: float) -> None:
        while True:
            try:
                kind, payload = self.inbox.get_nowait()
            except queue.Empty:
                return
            try:
                self._handle(kind, payload, now)
            except Exception:
                logger.exception("Mascote: mensagem %s", kind)

    def _handle(self, kind: str, payload: Any, now: float) -> None:
        if kind == "state":
            self.brain.set_app_state(str(payload))
        elif kind == "avatar":
            if payload.get("expression"):
                self.brain.set_expression(payload["expression"], now)
            if payload.get("gesture"):
                self.brain.set_gesture(payload["gesture"], now)
        elif kind == "say":
            self._say(payload, now)
        elif kind == "reply":
            if self.prefs.get("mascot_replies", True):
                self._reply(str(payload or ""), now)
        elif kind == "note":
            self._note(str(payload), now)
        elif kind == "command":
            if payload == "home":
                self.brain.placed = False
            elif payload == "hide":
                self._set_pref("mascot_enabled", False)

    def _say(self, event: Dict[str, Any], now: float) -> None:
        text = str(event.get("text") or "").strip()
        if not text:
            return
        category = event.get("category") or ""
        case = event.get("case") if category == "tedio" else None
        tag = ("teste · " if event.get("test") else "") + LIFE_TAGS.get(category, "")
        if case:
            buttons = (Button("later", "Depois"), Button("accept", "Aceitar o Caso", True))
            stay = 300.0
        else:
            buttons = (Button("silence", "Silêncio"),)
            stay = min(90.0, 30.0 + len(text) * 0.12)
        bubble = Bubble(text=text, tag=tag, case_title=(case or {}).get("titulo"), buttons=buttons)
        self.shown = Shown(bubble, "life", now + stay, event)
        self.brain.talk(len(text) / 14.0, now)
        expression = LIFE_EXPRESSIONS.get(category)
        if expression:
            self.brain.set_expression(expression, now, hold=12.0)
        self._last_frame = None

    def _reply(self, text: str, now: float) -> None:
        excerpt = plain_text(text)
        if not excerpt:
            return
        if len(excerpt) > REPLY_CHARS:
            excerpt = excerpt[:REPLY_CHARS].rsplit(" ", 1)[0] + "…"
        bubble = Bubble(text=excerpt, tag="respondeu", buttons=(Button("open", "Abrir a conversa", True),))
        self.shown = Shown(bubble, "reply", now + 25.0)
        self.brain.talk(min(5.0, len(excerpt) / 14.0), now)
        self._last_frame = None

    def _note(self, text: str, now: float, seconds: float = 4.0) -> None:
        self.shown = Shown(Bubble(text=text), "note", now + seconds)
        self._last_frame = None

    # ----------------- Actions -----------------
    def _button(self, ident: str) -> None:
        shown = self.shown
        if ident in ("close", "later"):
            self.shown = None
        elif ident == "accept":
            self.shown = None
            self._bridge("accept_case", (shown.event if shown else None))
        elif ident == "open":
            self.shown = None
            self._open_chat()
        elif ident == "silence":
            self.shown = None
            self._silence()
        self._last_frame = None

    def _open_chat(self) -> None:
        self._bridge("open_chat")

    def _bridge(self, name: str, *args) -> None:
        fn = getattr(self.bridge, name, None)
        if fn:
            try:
                fn(*args)
            except Exception:
                logger.exception("Mascote: ponte %s", name)

    def _silence(self) -> None:
        try:
            until = self.life.silence(SILENCE_MINUTES)
            hour = datetime.fromtimestamp(until).strftime("%H:%M")
            self._note(f"Silêncio até {hour}. Hmph.", self.clock())
        except Exception:
            logger.exception("Mascote: silêncio")

    def _set_pref(self, key: str, value: Any) -> None:
        try:
            self.prefs_saver({key: value})
        except Exception:
            logger.exception("Mascote: preferência %s", key)
        self.prefs[key] = value
        self._last_frame = None

    def _menu(self, x: int, y: int) -> None:
        from app.mascot.win32 import menu_items
        silenced = False
        try:
            silenced = bool(self.life.status().get("silenced_until"))
        except Exception:
            pass
        walk = bool(self.prefs.get("mascot_walk", True))
        dnd = bool(self.prefs.get("life_dnd", False))
        items = menu_items([
            (MENU_OPEN, "Abrir a conversa", False, True),
            (MENU_STAY, "Ficar parada aqui", not walk, True),
            (MENU_SILENCE, "Voltar a falar" if silenced else "Silêncio por 2 horas", False, True),
            (MENU_DND, "Não perturbar", dnd, True),
            (0, "", False, True),
            (MENU_HIDE, "Esconder (volta pelas Configurações)", False, True),
            (MENU_QUIT, "Encerrar o assistente", False, True),
        ])
        chosen = self.window.popup_menu(items, x, y)
        if chosen == MENU_OPEN:
            self._open_chat()
        elif chosen == MENU_STAY:
            self._set_pref("mascot_walk", not walk)
        elif chosen == MENU_SILENCE:
            if silenced:
                self.life.resume()
                self._note("Muito bem, voltei a falar.", self.clock())
            else:
                self._silence()
        elif chosen == MENU_DND:
            self._set_pref("life_dnd", not dnd)
        elif chosen == MENU_HIDE:
            self._set_pref("mascot_enabled", False)
        elif chosen == MENU_QUIT:
            self._bridge("quit")

    # ----------------- Frame -----------------
    def _load_prefs(self) -> None:
        try:
            loaded = self.prefs_loader() or {}
        except Exception:
            return
        for key, default in DEFAULT_PREFS.items():
            self.prefs[key] = loaded.get(key, default)

    def _fullscreen_in_front(self) -> bool:
        if not self.prefs.get("mascot_hide_fullscreen", True):
            return False
        try:
            fg = self.foreground_fn()
        except Exception:
            return False
        return bool(fg and fg.get("fullscreen") and not fg.get("own"))

    def _metrics(self) -> Tuple[Floor, float, int]:
        probe_x = self.brain.x if self.brain.placed else 0
        probe_y = self.brain.y - 2 if self.brain.placed else 0
        (left, top, right, bottom), dpi = self.area_fn(int(probe_x), int(probe_y))
        size = max(60, min(320, int(self.prefs.get("mascot_size") or 136)))
        size_px = max(40, round(size * dpi))
        self.brain.scale = size_px / 136.0
        return Floor(left, right, bottom), dpi, size_px

    def _frame(self, now: float, dt: float) -> None:
        floor, dpi, size_px = self._metrics()
        sprite_w, sprite_h = sprite.size_for(size_px)
        if not self.brain.placed:
            self.brain.place(floor, now, x=floor.right - 190 * self.brain.scale)
        if self.shown and now >= self.shown.until and not (self.hover or self._press):
            self.shown = None
            self._last_frame = None
        self.brain.step(dt, now, floor, sprite_w * 0.42,
                        walk=bool(self.prefs.get("mascot_walk", True)), busy=self.shown is not None)
        look, facing = self.brain.look(now)
        img = sprite.render_facing(look, size_px, facing)
        shake = wobble(now) * self.brain.scale if self.brain.app_state == "erro" and self.brain.is_resting() else 0
        sx = round(self.brain.x - sprite_w / 2 + shake)
        sy = round(self.brain.y - sprite_h + sprite.feet_offset(size_px))
        key = (look, facing, sx, sy, id(self.shown), self.hover, size_px)
        if key == self._last_frame and self.window.visible:
            return
        self._last_frame = key
        canvas, ox, oy = self._compose(img, sx, sy, floor, dpi, size_px)
        self.window.update(canvas, ox, oy)
        self.on_screen = True

    def _compose(self, img: Image.Image, sx: int, sy: int, floor: Floor, dpi: float,
                 size_px: int) -> Tuple[Image.Image, int, int]:
        if not self.shown:
            self._layout = {"sprite": (0, 0, img), "balloon": None}
            return img, sx, sy
        scale = max(0.75, dpi * max(0.9, min(1.3, size_px / dpi / 136.0)))
        bw = round(BALLOON_WIDTH * scale)
        centre = sx + img.width / 2
        bx = int(min(max(centre - bw / 2, floor.left + 4), floor.right - bw - 4))
        tail_at = (centre - bx) / bw
        key = (id(self.shown), self.hover, round(scale, 2), round(tail_at, 2))
        cached = self._balloon_cache.get(key)
        if cached is None:
            self._balloon_cache.clear()
            cached = render_balloon(self.shown.bubble, scale, self.hover, tail_at)
            self._balloon_cache[key] = cached
        bimg, rects = cached
        head_top = sy + round(img.height * 0.10)
        by = head_top - bimg.height + round(4 * scale)
        x0, y0 = min(sx, bx), min(sy, by)
        x1, y1 = max(sx + img.width, bx + bimg.width), max(sy + img.height, by + bimg.height)
        canvas = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
        canvas.alpha_composite(img, (sx - x0, sy - y0))
        canvas.alpha_composite(bimg, (bx - x0, by - y0))
        self._layout = {"sprite": (sx - x0, sy - y0, img),
                        "balloon": (bx - x0, by - y0, bimg, rects)}
        return canvas, x0, y0

    def _hit(self, x: int, y: int) -> Optional[Tuple[str, Optional[str]]]:
        """What is under client point (x, y): button, balloon, sprite or None."""
        balloon = self._layout.get("balloon")
        if balloon:
            bx, by, bimg, rects = balloon
            lx, ly = x - bx, y - by
            for ident, (x0, y0, x1, y1) in rects.items():
                if x0 <= lx <= x1 and y0 <= ly <= y1:
                    return ("button", ident)
            if 0 <= lx < bimg.width and 0 <= ly < bimg.height and bimg.getpixel((lx, ly))[3] > 24:
                return ("balloon", None)
        spr = self._layout.get("sprite")
        if spr:
            sx, sy, img = spr
            lx, ly = x - sx, y - sy
            if 0 <= lx < img.width and 0 <= ly < img.height and img.getpixel((lx, ly))[3] > 24:
                return ("sprite", None)
        return None
