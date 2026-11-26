"""
Reads the track playing in Spotify, best source first: the Spicetify bridge,
Windows' media controls (SMTC, only if the optional `winrt` packages are
installed) and the Spotify window title. Only Spotify is looked at.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Callable, List, Optional, Tuple

from app.spotify.bridge import Bridge, bridge as default_bridge
from app.spotify.track import Track, from_window_title, make

logger = logging.getLogger(__name__)

PLAYING = 4     # GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING
_smtc_missing = False


def _smtc_manager():
    for module in ("winrt.windows.media.control", "winsdk.windows.media.control"):
        try:
            mod = __import__(module, fromlist=["GlobalSystemMediaTransportControlsSessionManager"])
            return mod.GlobalSystemMediaTransportControlsSessionManager
        except ImportError:
            continue
    return None


async def _smtc_read(manager) -> Optional[Track]:
    sessions = (await manager.request_async()).get_sessions()
    for session in sessions:
        if "spotify" not in str(session.source_app_user_model_id or "").lower():
            continue
        props = await session.try_get_media_properties_async()
        info = session.get_playback_info()
        playing = int(info.playback_status) == PLAYING
        return make(props.title, props.artist, props.album_title, playing, "smtc")
    return None


def smtc_track() -> Optional[Track]:
    """From Windows' media controls; None without them or without Spotify there.
    Runs its own event loop: call it from a worker thread."""
    global _smtc_missing
    if os.name != "nt" or _smtc_missing:
        return None
    manager = _smtc_manager()
    if manager is None:
        _smtc_missing = True
        return None
    try:
        return asyncio.run(_smtc_read(manager))
    except Exception as exc:
        logger.debug("SMTC: %s", exc)
        return None


def _spotify_windows() -> List[Tuple[int, str]]:
    if os.name != "nt":
        return []
    from app.mascot import win32
    return win32.app_windows("spotify.exe")


def title_track(windows: Callable[[], List[Tuple[int, str]]] = _spotify_windows) -> Optional[Track]:
    try:
        found = windows()
    except Exception:
        return None
    for _hwnd, title in found:
        track = from_window_title(title)
        if track:
            return track
    return None


def current(bridge: Optional[Bridge] = None,
            readers: Optional[List[Callable[[], Optional[Track]]]] = None) -> Optional[Track]:
    """The track playing in Spotify, or None (closed, paused with no source that
    says so, an ad)."""
    track = (bridge or default_bridge).track()
    if track is not None:
        return track
    for read in readers if readers is not None else (smtc_track, title_track):
        track = read()
        if track is not None:
            return track
    return None
