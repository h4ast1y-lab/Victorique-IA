"""Where Victorique is: on the desktop or in the Biblioteca. One of her, never two.

The server owns this state (not the page, which may be closed, nor the mascot,
which may be off). The desktop mascot gets orders through the mascot bus and
reports when she went through her little door; the hall page reports when its
tab opens or closes and when she left through the hall's door.

States: desktop -> entrando -> biblioteca -> saindo -> desktop.
"""
import threading
import time
from typing import Any, Callable, Dict, List, Optional

DOOR_TIMEOUT = 6.0     # the hall's door: if the page never reports, she is out anyway
ENTER_TIMEOUT = 30.0   # the desktop mascot walking to her door (it reports when through)
AWAY_IDLE = 30.0       # out of sight (tab closed): back home after this long without work
HALL_IDLE = 300.0      # tab open and nothing to do: back home after this long

DESKTOP, ENTERING, LIBRARY, LEAVING = "desktop", "entrando", "biblioteca", "saindo"

ENTER = "enter-library"
ENTER_ANNOUNCE = "enter-library-announce"
RETURN = "return-from-library"


class Presence:
    def __init__(self, clock: Callable[[], float] = time.monotonic, bus: Any = None):
        self.clock = clock
        self._bus = bus
        self._lock = threading.Lock()
        self.state = DESKTOP
        self.reason: Optional[str] = None
        self.since = clock()
        self.hall_open = False
        self.last_work = 0.0

    @property
    def bus(self) -> Any:
        if self._bus is None:
            from app.mascot.bus import mascot_bus
            return mascot_bus
        return self._bus

    # ----------------- Internals (call with the lock held) -----------------
    def _set(self, state: str, reason: Optional[str] = None) -> None:
        self.state = state
        if reason is not None or state == DESKTOP:
            self.reason = reason
        self.since = self.clock()

    def _snap(self) -> Dict[str, Any]:
        return {"state": self.state, "reason": self.reason, "hall_open": self.hall_open,
                "out_of_sight": self.state != DESKTOP and not self.hall_open, "since": self.since}

    def _expire(self, out: List[str]) -> None:
        """Door timeouts and the automatic return home."""
        now = self.clock()
        if self.state == ENTERING and now - self.since >= ENTER_TIMEOUT:
            self._set(LIBRARY)
        elif self.state == LEAVING and now - self.since >= DOOR_TIMEOUT:
            self._go_home(out)
        if self.state == LIBRARY:
            quiet = now - max(self.since, self.last_work)
            if not self.hall_open and quiet >= AWAY_IDLE:
                self._go_home(out)
            elif self.hall_open and quiet >= HALL_IDLE:
                self._set(LEAVING, "aba")

    def _go_home(self, out: List[str]) -> None:
        self._set(DESKTOP)
        out.append(RETURN)

    def _enter(self, reason: str, announce: bool, out: List[str]) -> Optional[str]:
        """Returns the command to send; the caller decides the state after sending it."""
        if self.state == LEAVING:
            self._set(LIBRARY, reason)
            return None
        if self.state != DESKTOP:
            return None
        return ENTER_ANNOUNCE if announce else ENTER

    def _leave(self, reason: str, out: List[str]) -> None:
        if self.state == ENTERING:
            self._go_home(out)
        elif self.state == LIBRARY:
            if self.hall_open:
                self._set(LEAVING, reason)
            else:
                self._go_home(out)
        elif self.state == LEAVING and not self.hall_open:
            self._go_home(out)          # nobody is watching the hall's door any more

    def _send(self, commands: List[str]) -> bool:
        delivered = False
        for action in commands:
            try:
                delivered = bool(self.bus.command(action)) or delivered
            except Exception:
                pass
        return delivered

    def _arrive(self, command: str, reason: str) -> None:
        """Sends the enter command; she walks there only when someone can see her go."""
        delivered = self._send([command])
        try:
            visible = bool(self.bus.visible)
        except Exception:
            visible = False
        with self._lock:
            if self.state == DESKTOP:
                self._set(ENTERING if delivered and visible else LIBRARY, reason)

    # ----------------- Public API -----------------
    def snapshot(self) -> Dict[str, Any]:
        out: List[str] = []
        with self._lock:
            self._expire(out)
            snap = self._snap()
        self._send(out)
        return snap

    tick = snapshot

    def enter(self, reason: str, announce: bool = False) -> Dict[str, Any]:
        out: List[str] = []
        with self._lock:
            self._expire(out)
            command = self._enter(reason, announce, out)
        self._send(out)
        if command:
            self._arrive(command, reason)
        return self.snapshot()

    def leave(self, reason: str) -> Dict[str, Any]:
        out: List[str] = []
        with self._lock:
            self._expire(out)
            self._leave(reason, out)
        self._send(out)
        return self.snapshot()

    def mascot_left(self) -> None:
        """The desktop mascot went through her door."""
        with self._lock:
            if self.state == ENTERING:
                self._set(LIBRARY)

    def left_hall(self) -> None:
        """The hall page saw her go out through the hall's door."""
        out: List[str] = []
        with self._lock:
            if self.state == LEAVING:
                self._go_home(out)
        self._send(out)

    def note_work(self) -> None:
        """She is doing something to the books (any actor)."""
        with self._lock:
            self.last_work = self.clock()
            home = self.state == DESKTOP
            announce = not self.hall_open
        if home:
            self.enter("trabalho", announce=announce)

    def set_hall_open(self, is_open: bool) -> Dict[str, Any]:
        with self._lock:
            self.hall_open = bool(is_open)
        if is_open:
            return self.enter("aba")
        return self.leave("aba")


presence = Presence()
