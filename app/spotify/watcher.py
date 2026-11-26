"""
Watches the track playing in Spotify and, once one has really been listened
to (DWELL seconds of play, so skipped tracks do not count), offers it to the
"vida própria" as a "musica" moment. Whether she speaks, and when, is still
up to its gates and limits (silence, do not disturb, the hourly cap...).
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, Optional

from app.spotify.track import Track

logger = logging.getLogger(__name__)

DWELL = 20.0
POLL = 2.0
MAX_STEP = 5.0          # a longer gap between polls (sleep, a hang) is not listening
REMEMBER = 40           # tracks already offered, so a repeat is not offered again


class TrackTracker:
    def __init__(self) -> None:
        self.key: Optional[str] = None
        self.played = 0.0
        self.last: Optional[float] = None
        self.offered: Deque[str] = deque(maxlen=REMEMBER)

    def update(self, track: Optional[Track], now: float) -> Optional[Track]:
        """The track to comment on, once, when it has played DWELL seconds."""
        if track is None or not track.playing:
            self.last = None            # paused or gone: the clock stops
            return None
        if track.key != self.key:
            self.key, self.played, self.last = track.key, 0.0, now
            return None
        if self.last is not None:
            self.played += max(0.0, min(now - self.last, MAX_STEP))
        self.last = now
        if self.played >= DWELL and track.key not in self.offered:
            self.offered.append(track.key)
            return track
        return None


def _default_prefs() -> Dict[str, Any]:
    from app.core import preferences
    return preferences.load()


def _default_notify(category: str, facts: Dict[str, Any]) -> None:
    from app.life.service import life_service
    life_service.notify(category, facts)


def _default_reader() -> Optional[Track]:
    from app.spotify.nowplaying import current
    return current()


class SpotifyWatcher:
    def __init__(self, *, prefs_loader: Callable[[], Dict[str, Any]] = _default_prefs,
                 reader: Callable[[], Optional[Track]] = _default_reader,
                 notify: Callable[[str, Dict[str, Any]], None] = _default_notify,
                 clock: Callable[[], float] = time.monotonic, interval: float = POLL):
        self.prefs_loader = prefs_loader
        self.reader = reader
        self.notify = notify
        self.clock = clock
        self.interval = interval
        self.tracker = TrackTracker()
        self.track: Optional[Track] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def poll(self) -> Optional[Track]:
        """One look at Spotify. Returns the track offered to the vida própria, if any."""
        try:
            prefs = self.prefs_loader() or {}
        except Exception:
            prefs = {}
        if not (prefs.get("spotify_enabled", True) and prefs.get("spotify_comments", True)):
            self.track = None
            self.tracker.last = None
            return None
        try:
            self.track = self.reader()
        except Exception:
            logger.debug("Spotify: leitura falhou", exc_info=True)
            self.track = None
        offer = self.tracker.update(self.track, self.clock())
        if offer is not None:
            try:
                self.notify("musica", offer.facts())
            except Exception:
                logger.exception("Spotify: não consegui avisar a vida própria")
        return offer

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self.poll()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="spotify-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> Dict[str, Any]:
        return {"track": self.track.public() if self.track else None,
                "running": bool(self._thread and self._thread.is_alive())}


spotify_watcher = SpotifyWatcher()
