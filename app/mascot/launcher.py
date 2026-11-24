"""
Starts the desktop mascot next to the pywebview chat window (run.py).

The bridge lets the mascot open the chat, accept a proposed Caso there and
quit the app. Closing the chat window only hides it while she is on the
desktop (preference "mascot_keep_on_close"); "Encerrar o assistente" in her
menu quits for real.
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

CLOSE_NOTE = "Fechou a janela? Continuo aqui. Dois cliques em mim e a conversa volta."


class ChatWindowBridge:
    def __init__(self, window: Any):
        self.window = window
        self.quitting = False
        self.hidden = False

    def _later(self, fn) -> None:
        threading.Thread(target=fn, daemon=True).start()

    def open_chat(self) -> None:
        def show() -> None:
            w = self.window
            try:
                w.show()
                w.restore()
            except Exception as exc:
                logger.debug("show: %s", exc)
            self.hidden = False
            try:
                hwnd = w.native.Handle.ToInt32()
                ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception as exc:
                logger.debug("foreground: %s", exc)
        self._later(show)

    def accept_case(self, event: Optional[dict] = None) -> None:
        self.open_chat()
        payload = json.dumps(event or {}, ensure_ascii=False)
        script = f"window.victoriqueDesktop && window.victoriqueDesktop.acceptCase({payload})"
        self._later(lambda: self.window.evaluate_js(script))

    def quit(self) -> None:
        self.quitting = True

        def close_all() -> None:
            import webview
            for w in list(webview.windows):
                try:
                    w.destroy()
                except Exception as exc:
                    logger.debug("destroy: %s", exc)
        self._later(close_all)


def start(window: Any) -> Optional[Any]:
    """Starts the mascot (Windows only); None when unavailable or disabled at build."""
    if os.name != "nt" or os.environ.get("ASSISTANT_MASCOT", "1") == "0":
        return None
    try:
        from app.mascot.desktop import DesktopMascot
        bridge = ChatWindowBridge(window)
        mascot = DesktopMascot(bridge)
        mascot.start()
    except Exception:
        logger.exception("Não consegui iniciar a Victorique na área de trabalho.")
        return None

    told = {"done": False}

    def on_closing():
        if bridge.quitting or not mascot.enabled:
            return None
        if not mascot.prefs_loader().get("mascot_keep_on_close", True):
            return None
        bridge.hidden = True
        threading.Thread(target=window.hide, daemon=True).start()
        if not told["done"]:
            told["done"] = True
            mascot.post("note", CLOSE_NOTE)
        return False  # cancels the close: the window is only hidden

    window.events.closing += on_closing
    return mascot
