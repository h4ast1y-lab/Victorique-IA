"""
In-process bridge between the HTTP API (the chat window) and the desktop
mascot. The server and the mascot run in the same process (run.py), so this
is just a guarded reference; with no mascot attached every call is a no-op
and the chat page shows its own balloon, as before.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional


class MascotBus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._mascot: Any = None

    def attach(self, mascot: Any) -> None:
        with self._lock:
            self._mascot = mascot

    def detach(self, mascot: Any = None) -> None:
        with self._lock:
            if mascot is None or self._mascot is mascot:
                self._mascot = None

    @property
    def mascot(self) -> Any:
        with self._lock:
            return self._mascot

    @property
    def active(self) -> bool:
        """A mascot is running and enabled (it shows the balloons)."""
        mascot = self.mascot
        return bool(mascot and mascot.enabled)

    @property
    def visible(self) -> bool:
        mascot = self.mascot
        return bool(mascot and mascot.enabled and mascot.on_screen)

    def signal(self, state: Optional[str] = None, expression: Optional[str] = None,
               gesture: Optional[str] = None) -> bool:
        mascot = self.mascot
        if not mascot:
            return False
        if state:
            mascot.post("state", state)
        if expression or gesture:
            mascot.post("avatar", {"expression": expression, "gesture": gesture})
        return True

    def say(self, event: Dict[str, Any]) -> bool:
        """A "vida própria" line for her balloon. False when she is not there."""
        if not self.active:
            return False
        self.mascot.post("say", event)
        return True

    def reply(self, text: str) -> bool:
        if not self.active:
            return False
        self.mascot.post("reply", text)
        return True

    def command(self, action: str) -> bool:
        mascot = self.mascot
        if not mascot:
            return False
        mascot.post("command", action)
        return True

    def open_conversation(self, conversation_id: str) -> bool:
        """The mini chat asks to continue a conversation in the main window."""
        mascot = self.mascot
        if not mascot:
            return False
        mascot.post("open_conversation", conversation_id)
        return True

    def status(self) -> Dict[str, Any]:
        mascot = self.mascot
        if not mascot:
            return {"running": False, "active": False, "visible": False, "state": None}
        return {"running": True, "active": bool(mascot.enabled), "visible": self.visible,
                "state": mascot.brain.app_state, "mode": mascot.brain.mode}


mascot_bus = MascotBus()
