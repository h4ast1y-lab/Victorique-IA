"""
What the Spicetify extension (victorique.js) reports from inside Spotify:
the size of its page, where its panels, tabs and covers are (CSS pixels of
the page) and the track playing.

The extension proves it was installed by this app with a random token kept
in data/spotify_bridge.json and written into it at install time. Anything
else that posts here (another page, another program) is ignored. A report
older than STALE seconds no longer counts: Spotify closed, minimized or the
extension stopped.
"""
from __future__ import annotations

import hmac
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from app.spotify.track import Track, clean, make

logger = logging.getLogger(__name__)

STALE = 6.0
MAX_BYTES = 64 * 1024
MAX_ELEMENTS = 48
KINDS = {"panel", "player", "tab", "card", "row"}
# Where Spotify's own page lives (the origin of the extension's requests).
SPOTIFY_ORIGINS = {"https://xpui.app.spotify.com"}


@dataclass(frozen=True)
class Element:
    id: str
    kind: str
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class View:
    width: float
    height: float
    elements: Tuple[Element, ...]


def token_path() -> Path:
    from app.config import DATA_DIR
    return DATA_DIR / "spotify_bridge.json"


def _number(value: Any, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("número inválido")
    number = float(value)
    if not low <= number <= high:
        raise ValueError("número fora da faixa")
    return number


def parse_view(data: Any) -> Optional[View]:
    if not isinstance(data, dict):
        return None
    view = data.get("view")
    if not isinstance(view, dict):
        return None
    width = _number(view.get("w"), 100, 20000)
    height = _number(view.get("h"), 100, 20000)
    elements = []
    seen = set()
    raw = data.get("elements")
    for item in (raw if isinstance(raw, list) else [])[:MAX_ELEMENTS]:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        ident = clean(item.get("id"), 40).replace("/", "_")
        if kind not in KINDS or not ident or (kind, ident) in seen:
            continue
        try:
            el = Element(ident, kind, _number(item.get("x"), -width, 2 * width),
                         _number(item.get("y"), -height, 2 * height),
                         _number(item.get("w"), 1, 2 * width), _number(item.get("h"), 1, 2 * height))
        except ValueError:
            continue
        seen.add((kind, ident))
        elements.append(el)
    return View(width, height, tuple(elements))


def parse_track(data: Any) -> Optional[Track]:
    if not isinstance(data, dict) or not isinstance(data.get("track"), dict):
        return None
    t = data["track"]
    return make(t.get("title"), t.get("artist"), t.get("album"), bool(data.get("playing")), "spicetify")


class Bridge:
    def __init__(self, path: Optional[Path] = None, clock: Callable[[], float] = time.monotonic):
        self._path = path
        self.clock = clock
        self._lock = threading.Lock()
        self._token: Optional[str] = None
        self._view: Optional[View] = None
        self._track: Optional[Track] = None
        self._at = 0.0
        self.reports = 0

    @property
    def path(self) -> Path:
        return self._path or token_path()

    def token(self) -> str:
        """The shared secret, created the first time."""
        with self._lock:
            if self._token:
                return self._token
            try:
                saved = json.loads(self.path.read_text(encoding="utf-8")).get("token")
            except (OSError, ValueError, AttributeError):
                saved = None
            if not isinstance(saved, str) or len(saved) < 32:
                saved = secrets.token_urlsafe(32)
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps({"token": saved}), encoding="utf-8")
            self._token = saved
            return saved

    def check(self, token: Any) -> bool:
        # As bytes: compare_digest raises TypeError on non-ASCII text, and a
        # stranger's token must be refused, not crash the endpoint.
        if not isinstance(token, str) or not token:
            return False
        return hmac.compare_digest(token.encode("utf-8"), self.token().encode("utf-8"))

    def receive(self, data: Any) -> None:
        """A report from the extension (already authenticated). ValueError if malformed."""
        if not isinstance(data, dict):
            raise ValueError("relatório inválido")
        view = parse_view(data)
        track = parse_track(data)
        with self._lock:
            self._view = view
            self._track = track
            self._at = self.clock()
            self.reports += 1

    def receive_text(self, text: str) -> bool:
        """Raw JSON from the extension: checks size, token and shape. True when kept."""
        if not text or len(text) > MAX_BYTES:
            return False
        try:
            data = json.loads(text)
        except ValueError:
            return False
        if not isinstance(data, dict) or not self.check(data.get("token")):
            return False
        try:
            self.receive(data)
        except ValueError:
            return False
        return True

    def disconnected(self) -> None:
        with self._lock:
            self._at = 0.0

    def _fresh(self) -> bool:
        return bool(self._at) and self.clock() - self._at <= STALE

    def view(self) -> Optional[View]:
        with self._lock:
            return self._view if self._fresh() else None

    def track(self) -> Optional[Track]:
        with self._lock:
            return self._track if self._fresh() else None

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._fresh()

    def status(self, detail: bool = False) -> Dict[str, Any]:
        with self._lock:
            fresh = self._fresh()
            elements = self._view.elements if fresh and self._view else ()
            kinds: Dict[str, int] = {}
            for el in elements:
                kinds[el.kind] = kinds.get(el.kind, 0) + 1
            out: Dict[str, Any] = {"connected": fresh, "elements": len(elements), "kinds": kinds,
                                   "reports": self.reports}
            if detail and fresh and self._view:
                out["view"] = {"w": self._view.width, "h": self._view.height}
                out["items"] = [{"id": e.id, "kind": e.kind, "x": e.x, "y": e.y, "w": e.w, "h": e.h}
                                for e in elements]
            return out


bridge = Bridge()
