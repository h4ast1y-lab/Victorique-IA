"""
What the miniature Victorique does from moment to moment (pure logic).

Positions are in physical screen pixels: ``x`` is her centre, ``y`` the line
her soles rest on. The window code feeds a :class:`Floor` (the work area of
the monitor she is on: she walks on top of the taskbar) and draws whatever
:meth:`Brain.look` returns. No Windows calls here, so it is easy to test with
a fake clock and a seeded random generator.

Timings for blinks, idle gestures and how long a model-chosen expression
lingers follow the Victorique-IA-2 avatar engine.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Optional, Tuple

from app.core.avatar_protocol import EXPRESSIONS, GESTURE_DURATIONS
from app.mascot.sprite import WALK_FRAMES, Look

APP_STATES = ("acordada", "dormindo", "ouvindo", "pensando", "falando", "erro")
BUSY_STATES = ("ouvindo", "pensando", "falando", "erro")

EXPRESSION_HOLD = 22.0          # seconds a model-chosen expression lingers
BLINK_EVERY = (3.2, 7.3)
BLINK_LENGTH = 0.13
IDLE_GESTURE_EVERY = (15.0, 25.0)
PAGE_TURN_EVERY = (6.0, 11.0)
IDLE_GESTURES = ("pipe", "tea", "hair-adjust", "deduction")
GRAVITY = 2600.0                # px/s^2 at 1x; scaled by Brain.scale
HARD_LANDING = 900.0            # px/s at 1x
WALK_FPS = 7.5                  # walk cycle frames per second
TALK_STEP = 0.14


@dataclass
class Floor:
    left: int
    right: int
    y: int


class Brain:
    def __init__(self, rng: Optional[random.Random] = None, scale: float = 1.0):
        self.rng = rng or random.Random()
        self.scale = scale          # physical px per logical px (DPI x size)
        self.x = 0.0
        self.y = 0.0
        self.facing = 1
        self.mode = "idle"          # idle, walk, sit, sleep, held, fall, land
        self.mode_until = 0.0
        self.target_x: Optional[float] = None
        self.vy = 0.0
        self.walk_phase = 0.0
        self.app_state = "acordada"
        self.expression = "neutral"
        self.expression_until = 0.0
        self.gesture: Optional[str] = None
        self.gesture_until = 0.0
        self.next_gesture = 0.0
        self.blink_until = 0.0
        self.next_blink = 0.0
        self.talk_until = 0.0
        self.placed = False
        self.now = 0.0

    # ----------------- Inputs -----------------
    def place(self, floor: Floor, now: float, x: Optional[float] = None) -> None:
        self.x = float(x if x is not None else floor.right - 160 * self.scale)
        self.y = float(floor.y)
        self.mode = "idle"
        self.mode_until = now + self.rng.uniform(2.0, 5.0)
        self.next_blink = now + self.rng.uniform(*BLINK_EVERY)
        self.next_gesture = now + self.rng.uniform(*IDLE_GESTURE_EVERY)
        self.placed = True

    def set_app_state(self, state: str) -> None:
        if state in APP_STATES:
            self.app_state = state

    def set_expression(self, expression: str, now: float, hold: float = EXPRESSION_HOLD) -> None:
        if expression in EXPRESSIONS:
            self.expression = expression
            self.expression_until = now + hold

    def set_gesture(self, gesture: str, now: float) -> None:
        duration = GESTURE_DURATIONS.get(gesture)
        if duration:
            self.gesture = gesture
            self.gesture_until = now + duration / 1000.0

    def talk(self, seconds: float, now: float) -> None:
        self.talk_until = max(self.talk_until, now + max(0.5, min(8.0, seconds)))

    def grab(self, now: float) -> None:
        self.mode = "held"
        self.target_x = None
        self.vy = 0.0
        self.set_expression("surprised", now, hold=0.8)

    def drag_to(self, x: float, y: float) -> None:
        if self.mode == "held":
            self.x, self.y = float(x), float(y)

    def release(self, now: float) -> None:
        if self.mode == "held":
            self.mode = "fall"
            self.vy = 0.0
            self.set_expression("annoyed", now, hold=4.0)

    def poke(self, now: float) -> None:
        """A click on her: a flustered or annoyed look and a hand to the hair."""
        self.set_expression(self.rng.choice(("embarrassed", "annoyed")), now, hold=4.0)
        self.set_gesture("hair-adjust", now)
        if self.mode in ("walk", "sleep", "sit"):
            self.mode = "idle"
            self.mode_until = now + self.rng.uniform(4.0, 8.0)

    # ----------------- Simulation -----------------
    def step(self, dt: float, now: float, floor: Floor, half_width: float, *,
             walk: bool = True, speed: float = 34.0, busy: bool = False) -> None:
        """Advances `dt` seconds. `busy` = a balloon is open (she stays put)."""
        self.now = now
        if not self.placed:
            self.place(floor, now)
        dt = max(0.0, min(dt, 0.25))
        lo = floor.left + half_width
        hi = floor.right - half_width
        if hi < lo:
            lo = hi = (floor.left + floor.right) / 2

        if self.mode == "held":
            return
        if self.mode == "fall":
            self.vy += GRAVITY * self.scale * dt
            self.y += self.vy * dt
            self.x = min(max(self.x, lo), hi)
            if self.y >= floor.y:
                hard = self.vy > HARD_LANDING * self.scale
                self.y = float(floor.y)
                self.vy = 0.0
                self.mode = "land"
                self.mode_until = now + 0.28
                if not hard:
                    self.expression_until = min(self.expression_until, now + 1.5)
            return
        # The floor may move (taskbar resized, another monitor): stay on it.
        if self.y < floor.y - 2:
            self.mode = "fall"
            self.vy = 0.0
            return
        self.y = float(floor.y)
        self.x = min(max(self.x, lo), hi)

        if self.mode == "land":
            if now < self.mode_until:
                return
            self.mode = "idle"
            self.mode_until = now + self.rng.uniform(2.0, 5.0)

        self._expire(now)
        state = self.app_state
        if busy or state in BUSY_STATES:
            if self.mode in ("walk", "sit", "sleep"):
                self.mode = "idle"
            self.mode_until = max(self.mode_until, now + 3.0)
            if state == "falando" or busy:
                self._face_middle(floor)
            return
        if state == "dormindo":
            if self.mode != "sleep":
                self.mode = "sleep"
                self.target_x = None
            return
        if self.mode == "sleep":  # woke up
            self.mode = "idle"
            self.mode_until = now + self.rng.uniform(3.0, 6.0)
            self.set_expression("sleepy", now, hold=4.0)

        if self.mode == "walk":
            if not walk or self.target_x is None:
                self.mode = "idle"
                self.mode_until = now + self.rng.uniform(2.0, 5.0)
                return
            self.target_x = min(max(self.target_x, lo), hi)
            step = speed * self.scale * dt
            dx = self.target_x - self.x
            self.facing = 1 if dx > 0 else -1
            if abs(dx) <= step:
                self.x = self.target_x
                self.target_x = None
                self.mode = "idle"
                self.mode_until = now + self.rng.uniform(3.0, 10.0)
            else:
                self.x += step * self.facing
                self.walk_phase += dt * WALK_FPS
            return

        if self.mode == "sit":
            if now >= self.mode_until:
                self.mode = "idle"
                self.mode_until = now + self.rng.uniform(3.0, 8.0)
            elif now >= self.next_gesture:
                self.set_gesture("page-turn", now)
                self.next_gesture = now + self.rng.uniform(*PAGE_TURN_EVERY)
            return

        # Idle: an occasional small gesture, then decide what to do next.
        if self.gesture is None and now >= self.next_gesture:
            self.set_gesture(self.rng.choice(IDLE_GESTURES), now)
            self.next_gesture = now + self.rng.uniform(*IDLE_GESTURE_EVERY)
        if now < self.mode_until or self.gesture:
            return
        roll = self.rng.random()
        if walk and roll < 0.55 and hi > lo:
            span = hi - lo
            distance = self.rng.uniform(60, 420) * self.scale
            direction = self.rng.choice((-1, 1))
            target = self.x + direction * min(distance, span)
            if target < lo or target > hi:
                target = self.x - direction * min(distance, span)
            self.target_x = min(max(target, lo), hi)
            self.mode = "walk"
        elif roll < 0.78:
            self.mode = "sit"
            self.mode_until = now + self.rng.uniform(20.0, 60.0)
            self.next_gesture = now + self.rng.uniform(*PAGE_TURN_EVERY)
        else:
            self.mode_until = now + self.rng.uniform(4.0, 12.0)

    def _expire(self, now: float) -> None:
        if self.expression != "neutral" and now >= self.expression_until:
            self.expression = "neutral"
        if self.gesture and now >= self.gesture_until:
            self.gesture = None

    def _face_middle(self, floor: Floor) -> None:
        middle = (floor.left + floor.right) / 2
        self.facing = 1 if self.x < middle else -1

    # ----------------- Output -----------------
    def blinking(self, now: float) -> bool:
        if now >= self.next_blink:
            self.blink_until = now + BLINK_LENGTH
            self.next_blink = now + self.rng.uniform(*BLINK_EVERY)
        return now < self.blink_until

    def look(self, now: float) -> Tuple[Look, int]:
        """The sprite to draw now and which way she faces (1 right, -1 left)."""
        mode = self.mode
        state = self.app_state
        self._expire(now)
        expression = self.expression
        prop = self.gesture
        tilt = 0.0
        if mode == "walk":
            pose, frame = "walk", int(self.walk_phase) % WALK_FRAMES
        elif mode in ("sit", "sleep", "held", "fall", "land"):
            pose, frame = mode, int(now / 1.7) % 2
        else:
            pose, frame = "stand", int(now / 1.7) % 2
        if mode == "sleep":
            prop = "zzz"
        elif mode == "sit":
            prop = "page-turn" if prop == "page-turn" else None
        elif mode in ("held", "fall"):
            prop = None
        elif prop is None and state == "pensando":
            prop = "pipe"
        if expression == "neutral":
            if state == "pensando":
                expression = "focused"
            elif state == "erro":
                expression = "concerned"
        if state == "ouvindo" and mode not in ("held", "fall"):
            tilt = -4.0
        mouth = None
        talking = now < self.talk_until or (state == "falando" and mode not in ("sleep", "held", "fall"))
        if talking and mode != "sleep":
            step = int(now / TALK_STEP) % 4
            mouth = ("talk1", None, "talk2", None)[step]
        eyes = "closed" if mode == "sleep" else ("blink" if self.blinking(now) else "open")
        if prop == "zzz":
            prop_frame = int(now * 3) % 9
        elif prop == "deduction" or expression == "deduction":
            prop_frame = int(now * 5) % 8
        else:
            prop_frame = int(now * 6) % 6
        gaze = 0.5 if mode == "walk" else 0.0
        return Look(pose=pose, frame=frame, expression=expression, eyes=eyes, mouth=mouth,
                    prop=prop, prop_frame=prop_frame, gaze=gaze, tilt=tilt), self.facing

    def is_resting(self) -> bool:
        return self.mode in ("idle", "sit", "sleep", "land")


def wobble(now: float) -> float:
    """Small horizontal shake used for the error state (px at 1x)."""
    return math.sin(now * 40) * 1.5
