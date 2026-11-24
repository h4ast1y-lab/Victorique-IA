"""
Starts the desktop mascot next to the pywebview chat window (run.py).

The bridge lets the mascot open the chat, accept a proposed Caso there,
open and hide the small "conversa rápida" window (/ui/mini.html), hand a
conversation from it to the chat window and quit the app. Closing the chat window only hides it while she is on the
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
MINI_TITLE = "Victorique · conversa rápida"
MINI_SIZE = (380, 540)   # logical pixels (desktop.MINI_SIZE)


def _app_url() -> str:
    from app.config import settings
    return f"http://{settings.host}:{settings.port}"


class ChatWindowBridge:
    def __init__(self, window: Any):
        self.window = window
        self.quitting = False
        self.hidden = False
        self.mini: Optional[Any] = None
        self.mini_hidden = False
        self._mini_lock = threading.Lock()

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

    # ----------------- Conversa rápida (mini chat) -----------------
    def toggle_mini_chat(self, x: Optional[int] = None, y: Optional[int] = None) -> None:
        """One click on her: opens the small chat beside her, or hides it."""
        def run() -> None:
            with self._mini_lock:
                w = self.mini
                if w is None:
                    self._create_mini(x, y)
                elif self.mini_hidden:
                    try:
                        if x is not None and y is not None:
                            w.move(x, y)
                        w.show()
                    except Exception as exc:
                        logger.debug("mini show: %s", exc)
                    self.mini_hidden = False
                else:
                    self._hide_mini(w)
        self._later(run)

    def hide_mini_chat(self) -> None:
        def run() -> None:
            with self._mini_lock:
                if self.mini is not None and not self.mini_hidden:
                    self._hide_mini(self.mini)
        self._later(run)

    def _hide_mini(self, w: Any) -> None:
        try:
            w.hide()
        except Exception as exc:
            logger.debug("mini hide: %s", exc)
        self.mini_hidden = True

    def _create_mini(self, x: Optional[int], y: Optional[int]) -> None:
        import webview
        w = webview.create_window(
            MINI_TITLE, url=f"{_app_url()}/ui/mini.html",
            width=MINI_SIZE[0], height=MINI_SIZE[1], x=x, y=y,
            min_size=(320, 400), on_top=True, text_select=True,
            background_color="#262624",
        )
        self.mini = w
        self.mini_hidden = False

        def on_closing():
            if self.quitting:
                return None
            self.mini_hidden = True
            self._later(w.hide)
            return False  # only hidden: the next click brings it back as it was

        w.events.closing += on_closing

    def open_conversation(self, conversation_id: str) -> None:
        """From the mini chat: shows that conversation in the chat window."""
        self.open_chat()
        payload = json.dumps(str(conversation_id))
        script = f"window.victoriqueDesktop && window.victoriqueDesktop.openConversation({payload})"
        self._later(lambda: self.window.evaluate_js(script))
        self.hide_mini_chat()

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
