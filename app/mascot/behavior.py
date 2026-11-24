"""
What the miniature Victorique does from moment to moment (pure logic).

Positions are physical screen pixels: ``x, y`` is where her anchor sits,
normally the middle of her soles on the line she stands on. The window code
feeds a :class:`~app.mascot.surfaces.World` (the work area of her monitor,
her height and the surfaces she can stand on: the taskbar and the visible
tops of open windows) and draws what :meth:`Brain.look` returns. No Windows
calls here, so it is easy to test with a fake clock and a seeded random
generator.

She walks, turns, sits on the floor or on a window's title bar with her legs
dangling, reads, drinks tea, glances around, peeks in from a screen edge,
climbs up the side of a window, jumps onto a nearby one or hops down, rides
along when the window she stands on is dragged, falls when it closes, and
dozes off when the app does. Blink and gesture timings and how long a
model-chosen expression lingers follow the Victorique-IA-2 avatar engine.
"""
from __future__ import annotations

import math
import random
from typing import Callable, List, Optional, Tuple

from app.core.avatar_protocol import EXPRESSIONS, GESTURE_DURATIONS
from app.mascot.sprite import Look
from app.mascot.surfaces import Surface, World

APP_STATES = ("acordada", "dormindo", "ouvindo", "pensando", "falando", "erro")
BUSY_STATES = ("ouvindo", "pensando", "falando", "erro")

REFERENCE_HEIGHT = 136.0        # speeds below are px/s at this height
EXPRESSION_HOLD = 22.0          # seconds a model-chosen expression lingers
BLINK_EVERY = (3.2, 7.3)
BLINK_LENGTH = 0.13
GESTURE_WAIT = 6.0              # a model gesture not played by then is dropped
GRAVITY = 2600.0
HARD_LANDING = 900.0
WALK_SPEED = 40.0
WALK_FPS = 6.0
CLIMB_SPEED = 55.0
TALK_STEP = 0.22
DOOR_STEP = 0.15                # seconds per frame of the little door (closed, ajar, open)
PASS_SECONDS = 0.6              # walking through the doorway
HURRY = 2.5                     # she walks faster to her door (the hall is waiting)
DOOR_GAP = 0.35                 # the door stands this many heights beyond her
TURN_STEP = 0.09
WALK_FRAMES = 6

Step = Tuple[str, int, float]    # animation, frame, seconds


def seq(anim: str, frames, fps: float) -> List[Step]:
    return [(anim, int(f), 1.0 / fps) for f in frames]


# The turn sheet goes from facing right (0) through the front (2) to left (4).
TURN_TO = {1: [2, 1, 0], -1: [2, 3, 4]}

# Idle face for each model expression: (animation, frame).
EXPRESSION_FRAMES = {
    "neutral": ("blink", 0), "skeptical": ("glance", 4), "annoyed": ("moods", 3),
    "concerned": ("moods", 2), "happy": ("blink", 4), "surprised": ("talk", 2),
    "embarrassed": ("moods", 4), "focused": ("think", 2), "sleepy": ("doze", 0),
    "deduction": ("think", 4),
}


def gesture_steps(gesture: str) -> List[Step]:
    if gesture == "page-turn":
        return seq("read", range(12), 2.4) + seq("close_book", range(6), 4.0)
    if gesture == "pipe":
        return seq("think", [1, 2, 2, 3, 3, 2, 5], 2.2)
    if gesture == "deduction":
        return seq("think", [1, 2, 4, 4, 4, 5], 2.5)
    if gesture == "tea":
        return seq("tea", range(12), 4.0)
    if gesture == "hair-adjust":
        return seq("glance", range(6), 3.5)
    return []


PEEK_STEPS = seq("peek", [8, 1, 2, 3, 3, 4, 5, 6, 6, 7, 6, 5, 3, 2, 1, 8], 2.6)
HARD_LAND_STEPS = [("fall", 3, 0.3), ("fall", 4, 0.55), ("fall", 5, 0.25), ("fall", 6, 0.2), ("fall", 7, 0.15)]
SOFT_LAND_STEPS = [("jump", 7, 0.2)]


class Brain:
    def __init__(self, rng: Optional[random.Random] = None):
        self.rng = rng or random.Random()
        self.height = REFERENCE_HEIGHT
        self.x = 0.0
        self.y = 0.0
        self.facing = 1
        self.mode = "idle"   # idle walk turn act sit_down sit stand_up sleep edge
        #                      held air crouch land climb arrive peek
        #                      door_in away door_out (the Biblioteca's door)
        self.mode_t0 = 0.0
        self.until = 0.0
        self.surface_key = "ground"
        self.ride_ref: Optional[float] = None
        self.target_x: Optional[float] = None
        self.plan: Optional[dict] = None
        self.vx = 0.0
        self.vy = 0.0
        self.air_style = "drop"
        self.script: List[Step] = []
        self.script_i = 0
        self.script_t = 0.0
        self.after: Optional[Callable[[float], None]] = None
        self.model_act = False
        self.walk_phase = 0.0
        self.app_state = "acordada"
        self.expression = "neutral"
        self.expression_t0 = 0.0
        self.expression_until = 0.0
        self.gesture: Optional[str] = None
        self.gesture_at = 0.0
        self.blink_until = 0.0
        self.next_blink = 0.0
        self.talk_until = 0.0
        self.placed = False
        self.now = 0.0
        # The little door to the Biblioteca (app/library/presence).
        self.leaving = False
        self.hidden = False
        self.door: Optional[Tuple[float, float, int]] = None   # x, y, frame 0..2
        self.away_spot: Optional[Tuple[float, str, int]] = None  # x, surface, side
        self._door_x = 0.0
        self._door_from = 0.0

    @property
    def scale(self) -> float:
        return self.height / REFERENCE_HEIGHT

    # ----------------- Inputs -----------------
    def place(self, world: World, now: float, x: Optional[float] = None) -> None:
        self.height = float(world.height)
        ground = world.ground
        self.x = float(x if x is not None else ground.right - 1.3 * self.height)
        self.y = float(ground.y)
        self.surface_key = "ground"
        self.ride_ref = None
        self.plan = None
        self.target_x = None
        self.script = []
        self._set_mode("idle", now)
        self.until = now + self.rng.uniform(2.0, 5.0)
        self.next_blink = now + self.rng.uniform(*BLINK_EVERY)
        self.placed = True

    def set_app_state(self, state: str) -> None:
        if state in APP_STATES:
            self.app_state = state

    def set_expression(self, expression: str, now: float, hold: float = EXPRESSION_HOLD) -> None:
        if expression in EXPRESSIONS:
            self.expression = expression
            self.expression_t0 = now
            self.expression_until = now + hold

    def set_gesture(self, gesture: str, now: float) -> None:
        if gesture in GESTURE_DURATIONS:
            self.gesture = gesture
            self.gesture_at = now

    def talk(self, seconds: float, now: float) -> None:
        self.talk_until = max(self.talk_until, now + max(0.5, min(8.0, seconds)))

    def grab(self, now: float) -> None:
        self._clear()
        self.door = None
        self.hidden = False
        self.surface_key = ""
        self.ride_ref = None
        self._set_mode("held", now)
        self.set_expression("surprised", now, hold=0.8)

    def drag_to(self, x: float, y: float) -> None:
        if self.mode == "held":
            self.x, self.y = float(x), float(y)

    def release(self, now: float, vx: float = 0.0, vy: float = 0.0) -> None:
        if self.mode != "held":
            return
        limit = 1800.0 * self.scale
        # Dragged, her anchor is the drawn cursor's tip at her hand; falling,
        # it is her soles again (about half her height lower, a bit left).
        self.x -= self.height * 0.3
        self.y += self.height * 0.5
        self.vx = max(-limit, min(limit, vx))
        self.vy = max(-limit, min(limit, vy))
        self.air_style = "drop"
        self._set_mode("air", now)
        self.set_expression("annoyed", now, hold=4.0)

    def poke(self, now: float) -> None:
        """A click on her: a flustered or annoyed look."""
        self.set_expression(self.rng.choice(("embarrassed", "annoyed")), now, hold=4.0)
        if self.mode in ("held", "air", "climb", "crouch", "land", "arrive"):
            return
        if self.mode in ("sit", "sleep", "sit_down"):
            self._stand_up(now)
        elif self.mode in ("walk", "act", "turn", "edge", "peek"):
            self._idle(now, 4.0, 8.0)

    # ----------------- Simulation -----------------
    def step(self, dt: float, now: float, world: World, *, walk: bool = True,
             climb: bool = True, busy: bool = False) -> None:
        """Advances `dt` seconds. `busy` = a balloon is open (she stays put)."""
        self.now = now
        if self.mode == "away":
            return
        self.height = float(world.height)
        if not self.placed:
            self.place(world, now)
        dt = max(0.0, min(dt, 0.25))
        if self.mode in ("door_in", "door_out"):
            self._door_step(now)
            return
        if self.mode == "held":
            return
        if self.mode == "air":
            self._fly(dt, now, world)
            return
        if self.mode == "climb":
            self._climb(dt, now, world)
            return
        if not self._stand(world, now):
            return
        self._expire(now)
        if self.leaving:
            self._head_for_door(dt, now, world)
            return
        state = self.app_state
        busy = busy or now < self.talk_until or state in BUSY_STATES
        if self.gesture and now - self.gesture_at > GESTURE_WAIT:
            self.gesture = None

        if self.script:
            if busy and self.mode in ("act", "peek") and not self.model_act:
                self._idle(now, 3.0, 6.0)
            else:
                self._run_script(now)   # its `after` may start a new mode
                return

        if state == "dormindo":
            self._doze_off(now)
            return
        if self.mode == "sleep":            # woke up
            self.set_expression("sleepy", now, hold=4.0)
            self._stand_up(now)
            return

        if busy:
            if self.mode == "walk":
                self._idle(now, 3.0, 6.0)
            elif self.mode == "sit":
                self._stand_up(now)
            elif self.mode == "edge":
                self._idle(now, 3.0, 6.0)
            self.plan = None
            if self.mode == "idle" and self.gesture:
                self._play_gesture(now)
            return

        if self.mode == "walk":
            self._walk(dt, now, world, walk)
            return
        if self.mode == "sit":
            if now >= self.until:
                self._stand_up(now)
            return
        if self.mode == "edge":
            if now >= self.until:
                self._idle(now, 2.0, 5.0)
            return
        if self.mode != "idle":
            self._idle(now, 1.0, 3.0)
            return
        if self.gesture:
            self._play_gesture(now)
            return
        if now >= self.until:
            self._decide(now, world, walk, climb)

    # ----------------- Standing, falling, landing -----------------
    def _stand(self, world: World, now: float) -> bool:
        """Keeps her on her surface (following a moving window); False when
        it is gone and she starts to fall."""
        if self.surface_key == "ground":
            ground = world.ground
            if self.mode == "peek":
                return True
            if ground.y > self.y + 2:        # the floor went down (auto-hide taskbar)
                self._drop(now)
                return False
            self.y = float(ground.y)
            lo, hi = self._walk_range(ground)
            self.x = min(max(self.x, lo), hi)
            return True
        segments = world.segments(self.surface_key)
        if segments:
            ref = segments[0].wall_left
            dx = ref - self.ride_ref if self.ride_ref is not None else 0.0
            nx = self.x + dx
            for s in segments:
                if s.contains(nx, self.height * 0.15):
                    self.x, self.y, self.ride_ref = nx, float(s.y), ref
                    if self.target_x is not None:
                        self.target_x += dx
                    return True
        self._drop(now)
        return False

    def _drop(self, now: float) -> None:
        self._clear()
        self.surface_key = ""
        self.ride_ref = None
        self.air_style = "drop"
        self.vx = self.vy = 0.0
        self._set_mode("air", now)

    def _fly(self, dt: float, now: float, world: World) -> None:
        h = self.height
        self.vy += GRAVITY * self.scale * dt
        nx = self.x + self.vx * dt
        ny = self.y + self.vy * dt
        left, top, right, _ = world.area
        lo, hi = left + h * 0.15, right - h * 0.15
        if nx < lo:
            nx, self.vx = lo, abs(self.vx) * 0.3
        elif nx > hi:
            nx, self.vx = hi, -abs(self.vx) * 0.3
        if ny < top + h:                     # flung against the top of the screen
            ny, self.vy = top + h, max(self.vy, 0.0)
        landing = world.landing(nx, self.y, ny) if self.vy > 0 else None
        self.x = nx
        if landing is None and ny >= world.ground.y:
            landing = world.ground
        if landing is not None:
            self._land(landing, now)
        else:
            self.y = ny

    def _land(self, surface: Surface, now: float) -> None:
        hard = self.air_style == "drop" and self.vy > HARD_LANDING * self.scale
        self.y = float(surface.y)
        self.surface_key = surface.key
        self.ride_ref = surface.wall_left if surface.kind == "window" else None
        self.vx = self.vy = 0.0
        if hard:
            self.set_expression("annoyed", now, hold=4.0)
        elif self.air_style == "drop":
            self.expression_until = min(self.expression_until, now + 1.5)
        self._play(HARD_LAND_STEPS if hard else SOFT_LAND_STEPS, now, "land",
                   lambda t: self._idle(t, 2.0, 5.0))

    # ----------------- Climbing and jumping -----------------
    def _climb(self, dt: float, now: float, world: World) -> None:
        plan = self.plan or {}
        segments = world.segments(plan.get("key", ""))
        if not segments:
            self._drop(now)
            return
        top = segments[0]
        left_side = plan.get("side") == "left"
        self.x = top.wall_left if left_side else top.wall_right
        self.facing = 1 if left_side else -1
        if self.y > top.bottom + self.height * 0.3:      # the window moved up and away
            self._drop(now)
            return
        self.y -= CLIMB_SPEED * self.scale * dt
        if self.y > top.y:
            return
        h = self.height
        inside = top.wall_left + h * 0.3 if left_side else top.wall_right - h * 0.3
        seg = world.find(top.key, inside)
        self.y = float(top.y)
        if seg is None:                  # the corner is covered: she lets go
            self.x = inside
            self._drop(now)
            return
        self.x = inside
        self.surface_key = seg.key
        self.ride_ref = seg.wall_left
        self.plan = None
        self._play([("climb", 10, 0.22), ("climb", 11, 0.3)], now, "arrive",
                   lambda t: self._idle(t, 2.0, 5.0))

    def _launch(self, to_x: float, to_y: float, now: float) -> None:
        """Crouch, then jump in an arc landing at (to_x, to_y)."""
        g = GRAVITY * self.scale
        apex = min(self.y, to_y) - self.height * 0.3
        vy0 = -math.sqrt(2 * g * max(1.0, self.y - apex))
        t_up = -vy0 / g
        t_down = math.sqrt(2 * max(1.0, to_y - apex) / g)
        vx = (to_x - self.x) / (t_up + t_down)
        self.facing = 1 if vx >= 0 else -1

        def go(t: float) -> None:
            self.vx, self.vy = vx, vy0
            self.air_style = "jump"
            self.surface_key = ""
            self._set_mode("air", t)

        self._play(seq("jump", [1, 2], 1 / TURN_STEP), now, "crouch", go)

    def _climb_options(self, world: World, here: Surface) -> List[dict]:
        h = self.height
        lo, hi = self._walk_range(here)
        options = []
        for top in world.windows():
            if top.key == here.key or top.y > self.y - h * 0.9 or top.bottom < self.y - h * 0.25:
                continue
            for side, wall, corner in (("left", top.wall_left, top.left <= top.wall_left + h * 0.2),
                                       ("right", top.wall_right, top.right >= top.wall_right - h * 0.2)):
                approach = wall - h * 0.18 if side == "left" else wall + h * 0.18
                if corner and lo <= approach <= hi:
                    options.append({"kind": "climb", "key": top.key, "side": side, "x": approach})
        return options

    def _jump_options(self, world: World, here: Surface) -> List[Tuple[float, float]]:
        h = self.height
        options = []
        for top in world.windows():
            rise = self.y - top.y
            if top.key == here.key or not (h * 0.12 < rise <= h * 1.0):
                continue
            lo, hi = top.left + h * 0.2, top.right - h * 0.2
            if lo > hi:
                continue
            land = min(max(self.x, lo), hi)
            if abs(land - self.x) <= h * 2.2:
                options.append((land, top.y))
        return options

    # ----------------- Walking, sitting, scripts -----------------
    def _walk_range(self, surface: Surface) -> Tuple[float, float]:
        margin = self.height * (0.12 if surface.kind == "window" else 0.26)
        lo, hi = surface.left + margin, surface.right - margin
        if hi < lo:
            lo = hi = (surface.left + surface.right) / 2
        return lo, hi

    def _here(self, world: World) -> Surface:
        if self.surface_key != "ground":
            found = world.find(self.surface_key, self.x, self.height * 0.15)
            if found:
                return found
        return world.ground

    def _start_walk(self, target: float, now: float, plan: Optional[dict] = None) -> None:
        self.target_x = target
        self.plan = plan
        direction = 1 if target >= self.x else -1
        self.facing = direction
        self._play(seq("turn", TURN_TO[direction], 1 / TURN_STEP), now, "turn",
                   lambda t: self._set_mode("walk", t))

    def _walk(self, dt: float, now: float, world: World, walk: bool) -> None:
        if self.target_x is None or (not walk and self.plan is None):
            self._stop_walking(now, world)
            return
        lo, hi = self._walk_range(self._here(world))
        target = min(max(self.target_x, lo), hi)
        step = WALK_SPEED * self.scale * dt
        if self.plan and self.plan.get("kind") == "door":
            step *= HURRY
        dx = target - self.x
        if abs(dx) <= step:
            self.x = target
            self._stop_walking(now, world)
            return
        self.facing = 1 if dx > 0 else -1
        self.x += step * self.facing
        self.walk_phase += dt * WALK_FPS

    def _stop_walking(self, now: float, world: World) -> None:
        plan, self.plan = self.plan, None
        self.target_x = None
        h = self.height
        if plan and plan["kind"] == "climb" and world.segments(plan["key"]):
            self.facing = 1 if plan["side"] == "left" else -1

            def climb(t: float) -> None:
                self.plan = plan
                self.surface_key = ""
                self.ride_ref = None
                self._set_mode("climb", t)

            self._play([("climb", 0, 0.2), ("climb", 1, 0.3)], now, "turn", climb)
            return
        if plan and plan["kind"] == "door":
            self._open_door("door_in", plan["dir"], now)
            return
        if plan and plan["kind"] == "hop":
            self._launch(self.x + plan["dir"] * h * 0.8, self.y + h * 4, now)
            return
        if plan and plan["kind"] == "peek":
            left, _, right, _ = world.area
            at_left = plan["side"] == "left"
            self.x = left if at_left else right
            self.facing = 1 if at_left else -1

            def come_out(t: float) -> None:
                self.x = left + h * 0.35 if at_left else right - h * 0.35
                self._idle(t, 0.5, 1.5)

            self._play(PEEK_STEPS, now, "peek", come_out)
            return
        back = list(reversed(TURN_TO[self.facing]))
        self._play(seq("turn", back, 1 / TURN_STEP), now, "turn",
                   lambda t: self._idle(t, 3.0, 9.0))

    # ----------------- The Biblioteca's door -----------------
    @property
    def is_away(self) -> bool:
        return self.mode == "away"

    def go_away(self, now: float) -> None:
        """Walk to the nearest end of where she stands and go through a little door."""
        if self.mode in ("away", "door_in"):
            return
        self.leaving = True

    def vanish(self, now: float) -> None:
        """Gone at once (nobody could see her go)."""
        self._clear()
        self.away_spot = (self.x, self.surface_key or "ground", self.facing)
        self.leaving = False
        self.hidden = True
        self.door = None
        self._set_mode("away", now)

    def come_back(self, now: float, world: World) -> None:
        """Out of the little door where she left; or, still going, she changes her mind."""
        if self.mode == "away":
            x, key, side = self.away_spot or (world.ground.right - 1.3 * self.height, "ground", 1)
            surface = world.find(key, x, self.height * 0.15) if key not in ("", "ground") else None
            surface = surface or world.ground
            lo, hi = self._walk_range(surface)
            x = min(max(x, lo), hi)
            self.height = float(world.height)
            self.surface_key = surface.key
            self.ride_ref = None
            self.x, self.y = x, float(surface.y)
            self.placed = True
            self._open_door("door_out", side, now)
            return
        if self.leaving or self.mode == "door_in":
            self.leaving = False
            self.hidden = False
            self.door = None
            self._idle(now, 1.0, 3.0)

    def _head_for_door(self, dt: float, now: float, world: World) -> None:
        if self.mode == "walk" and self.plan and self.plan.get("kind") == "door":
            self._walk(dt, now, world, True)
            return
        if self.script and self.mode in ("turn", "stand_up"):
            self._run_script(now)
            return
        if self.mode in ("sit", "sleep", "sit_down"):
            self._clear()
            self._play(seq("stand_up", range(6), 8.0), now, "stand_up",
                       lambda t: self._set_mode("idle", t))
            return
        lo, hi = self._walk_range(self._here(world))
        side = -1 if self.x - lo <= hi - self.x else 1
        self._clear()
        self._start_walk(lo if side < 0 else hi, now, {"kind": "door", "dir": side})

    def _open_door(self, mode: str, side: int, now: float) -> None:
        self._clear()
        self.leaving = False
        self.facing = side if mode == "door_in" else -side
        gap = DOOR_GAP * self.height
        self._door_x = self.x + side * gap
        self._door_from = self.x if mode == "door_in" else self._door_x
        self.away_spot = (self.x, self.surface_key or "ground", side)
        self.hidden = mode == "door_out"
        if mode == "door_out":
            self.x = self._door_x
        self.door = (self._door_x, self.y, 0)
        self._set_mode(mode, now)

    def _door_step(self, now: float) -> None:
        t = now - self.mode_t0
        opening = 3 * DOOR_STEP
        spot = self.away_spot[0] if self.away_spot else self.x
        start, end = (self._door_from, self._door_x) if self.mode == "door_in" else (self._door_x, spot)
        if t < opening:
            self.door = (self._door_x, self.y, min(2, int(t / DOOR_STEP)))
            return
        if t < opening + PASS_SECONDS:
            self.hidden = False
            p = (t - opening) / PASS_SECONDS
            self.x = start + (end - start) * p
            self.walk_phase = t * WALK_FPS
            self.door = (self._door_x, self.y, 2)
            return
        self.x = end
        closing = t - opening - PASS_SECONDS
        if self.mode == "door_in":
            self.hidden = True
        if closing < opening:
            self.door = (self._door_x, self.y, 2 - min(2, int(closing / DOOR_STEP)))
            return
        self.door = None
        if self.mode == "door_in":
            self._set_mode("away", now)
        else:
            self.hidden = False
            self.facing = 1 if spot >= self._door_x else -1
            self._idle(now, 1.5, 4.0)

    def _stand_up(self, now: float) -> None:
        self._play(seq("stand_up", range(6), 8.0), now, "stand_up",
                   lambda t: self._idle(t, 2.0, 5.0))

    def _doze_off(self, now: float) -> None:
        if self.mode in ("sleep", "held", "air", "climb"):
            return
        if self.mode == "sit":
            self._set_mode("sleep", now)
            return
        self._clear()

        def sit(t: float) -> None:
            self._play(seq("sit_down", range(6), 8.0), t, "sit_down",
                       lambda t2: self._set_mode("sleep", t2))

        self._play(seq("doze", range(6), 2.0), now, "act", sit)

    def _play_gesture(self, now: float) -> None:
        steps = gesture_steps(self.gesture or "")
        self.gesture = None
        if steps:
            self._play(steps, now, "act", lambda t: self._idle(t, 2.0, 5.0))
            self.model_act = True

    def _decide(self, now: float, world: World, walk: bool, climb: bool) -> None:
        rng = self.rng
        h = self.height
        here = self._here(world)
        on_window = here.kind == "window"
        lo, hi = self._walk_range(here)
        climbs = self._climb_options(world, here) if walk and climb else []
        jumps = self._jump_options(world, here) if walk and climb else []
        options: List[Tuple[str, float]] = [("rest", 10), ("read", 8), ("tea", 6), ("glance", 6)]
        options.append(("edge", 16) if on_window else ("sit", 12))
        if walk and hi > lo:
            options.append(("walk", 40))
        if climbs:
            options.append(("climb", 4 if on_window else 9))
        if jumps:
            options.append(("jump", 7))
        if walk and climb and on_window:
            options.append(("hop", 10))
        if walk and not on_window:
            options.append(("peek", 3))
        total = sum(w for _, w in options)
        roll = rng.uniform(0, total)
        choice = options[-1][0]
        for name, weight in options:
            roll -= weight
            if roll <= 0:
                choice = name
                break

        if choice == "walk":
            distance = rng.uniform(0.45, 3.0) * h
            direction = rng.choice((-1, 1))
            target = self.x + direction * distance
            if target < lo or target > hi:
                target = self.x - direction * distance
            self._start_walk(min(max(target, lo), hi), now)
        elif choice == "climb":
            plan = rng.choice(climbs)
            self._start_walk(plan["x"], now, plan)
        elif choice == "jump":
            land_x, land_y = rng.choice(jumps)
            self._launch(land_x, land_y, now)
        elif choice == "hop":
            to_right = rng.random() < 0.5
            self._start_walk(hi if to_right else lo, now, {"kind": "hop", "dir": 1 if to_right else -1})
        elif choice == "peek":
            left, _, right, _ = world.area
            at_left = self.x - left < right - self.x
            target = left + h * 0.3 if at_left else right - h * 0.3
            self._start_walk(target, now, {"kind": "peek", "side": "left" if at_left else "right"})
        elif choice == "sit":
            self._play(seq("sit_down", range(6), 8.0), now, "sit_down",
                       lambda t: self._sit(t))
        elif choice == "edge":
            self._set_mode("edge", now)
            self.until = now + rng.uniform(15.0, 40.0)
        elif choice == "read":
            steps = seq("read", range(12), 2.4) * rng.randint(2, 3) + seq("close_book", range(6), 4.0)
            self._play(steps, now, "act", lambda t: self._idle(t, 2.0, 6.0))
        elif choice == "tea":
            steps = seq("tea", range(12), 4.0) + [("tea", 0, 1.5)]
            self._play(steps, now, "act", lambda t: self._idle(t, 2.0, 6.0))
        elif choice == "glance":
            self._play(seq("glance", range(6), 3.0), now, "act", lambda t: self._idle(t, 2.0, 6.0))
        else:
            self.until = now + rng.uniform(4.0, 12.0)

    def _sit(self, now: float) -> None:
        self._set_mode("sit", now)
        self.until = now + self.rng.uniform(20.0, 60.0)

    def _idle(self, now: float, low: float, high: float) -> None:
        self._clear()
        self._set_mode("idle", now)
        self.until = now + self.rng.uniform(low, high)

    def _clear(self) -> None:
        self.script = []
        self.after = None
        self.model_act = False
        self.plan = None
        self.target_x = None

    def _set_mode(self, mode: str, now: float) -> None:
        self.mode = mode
        self.mode_t0 = now

    def _play(self, steps: List[Step], now: float, mode: str,
              after: Optional[Callable[[float], None]] = None) -> None:
        self.script = list(steps)
        self.script_i = 0
        self.script_t = now
        self.after = after
        self.model_act = False
        self._set_mode(mode, now)

    def _run_script(self, now: float) -> None:
        while self.script:
            _, _, seconds = self.script[self.script_i]
            if now - self.script_t < seconds:
                return
            self.script_t += seconds
            self.script_i += 1
            if self.script_i >= len(self.script):
                after = self.after
                self.script, self.after, self.model_act = [], None, False
                if after:
                    after(now)
                else:
                    self._idle(now, 2.0, 5.0)
                return

    def _expire(self, now: float) -> None:
        if self.expression != "neutral" and now >= self.expression_until:
            self.expression = "neutral"

    # ----------------- Output -----------------
    def blinking(self, now: float) -> bool:
        if now >= self.next_blink:
            self.blink_until = now + BLINK_LENGTH
            self.next_blink = now + self.rng.uniform(*BLINK_EVERY)
        return now < self.blink_until

    def look(self, now: float) -> Look:
        """The frame to draw now."""
        facing = self.facing
        if self.script:
            anim, frame, _ = self.script[min(self.script_i, len(self.script) - 1)]
            return Look(anim, frame, facing)
        mode = self.mode
        t = now - self.mode_t0
        if mode == "walk":
            return Look("walk", int(self.walk_phase) % WALK_FRAMES, facing)
        if mode == "held":
            frame = int(t * 8) if t < 0.5 else 4 + int((t - 0.5) * 8) % 8
            return Look("held", min(frame, 11), facing)
        if mode == "air":
            if self.air_style == "jump":
                v = self.vy / max(1.0, self.scale)
                frame = 3 if v < -500 else 4 if v < -150 else 5 if v < 250 else 6
                return Look("jump", frame, facing)
            return Look("fall", int(t * 8) % 3, facing)
        if mode == "climb":
            return Look("climb", 2 + int(t * 6) % 8, facing)
        if mode in ("door_in", "door_out") and self.door and self.door[2] == 2 and not self.hidden:
            return Look("walk", int(self.walk_phase) % WALK_FRAMES, facing)
        if mode == "sleep":
            return Look("sitting", 3, facing, "zzz", int(now * 3) % 9)
        if mode == "sit":
            return Look("sitting", 3 if self.blinking(now) else 0, facing)
        if mode == "edge":
            return Look("edge", int(now * 3) % 12, facing)
        return self._face(now)

    def _face(self, now: float) -> Look:
        state = self.app_state
        expression = self.expression if now < self.expression_until else "neutral"
        blink = self.blinking(now)
        if now < self.talk_until or state == "falando":
            frames = (1, 2, 3, 4, 1, 4)
            return Look("talk", frames[int(now / TALK_STEP) % len(frames)], self.facing)
        if expression != "neutral":
            if expression == "annoyed" and now - self.expression_t0 < 1.6:
                return Look("moods", 1, self.facing)
            anim, frame = EXPRESSION_FRAMES[expression]
            if expression == "sleepy":
                frame = int(now * 1.5) % 6
            elif blink and anim == "blink":
                frame = 3
            return Look(anim, frame, self.facing)
        if state == "pensando":
            frames = (2, 2, 3, 3, 4, 2)
            return Look("think", frames[int(now / 0.8) % len(frames)], self.facing)
        if state == "ouvindo":
            return Look("blink", 3 if blink else 1, self.facing)
        if state == "erro":
            return Look("moods", 3, self.facing)
        return Look("blink", 3 if blink else 0, self.facing)

    def is_resting(self) -> bool:
        return self.mode in ("idle", "sit", "sleep", "edge")

    def on_window(self) -> Optional[str]:
        """The key of the window she stands on or is climbing, if any."""
        if self.mode == "climb" and self.plan:
            return self.plan.get("key")
        if self.surface_key.startswith("w"):
            return self.surface_key
        return None


def wobble(now: float) -> float:
    """Small horizontal shake used for the error state (px at the reference height)."""
    return math.sin(now * 40) * 1.5
