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
from app.spotify.track import IDLE_TITLES, Track, from_window_title, make

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
        if str(props.title or "").strip().lower() in IDLE_TITLES:
            return None             # an ad ("Advertisement", "Spotify")
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


# What Windows' media controls can do to Spotify without the Spicetify bridge.
SMTC_ACTIONS = {
    "pause": "try_pause_async",
    "resume": "try_play_async",
    "toggle": "try_toggle_play_pause_async",
    "next": "try_skip_next_async",
    "previous": "try_skip_previous_async",
}


async def _smtc_control(manager, method: str) -> bool:
    sessions = (await manager.request_async()).get_sessions()
    for session in sessions:
        if "spotify" in str(session.source_app_user_model_id or "").lower():
            return bool(await getattr(session, method)())
    return False


def smtc_control(action: str) -> Optional[bool]:
    """Pause, resume, toggle, next or previous through Windows' media controls.
    None when they are unavailable (no winrt, not Windows); False when Spotify
    is not there or refused. Runs its own event loop: call it from a worker thread."""
    method = SMTC_ACTIONS.get(action)
    if method is None:
        raise ValueError(f"ação desconhecida: {action}")
    if os.name != "nt" or _smtc_missing:
        return None
    manager = _smtc_manager()
    if manager is None:
        return None
    try:
        return asyncio.run(_smtc_control(manager, method))
    except Exception as exc:
        logger.debug("SMTC (%s): %s", action, exc)
        return False


def spotify_windows() -> List[Tuple[int, str]]:
    """(hwnd, title) of Spotify's visible windows; [] when it is closed."""
    if os.name != "nt":
        return []
    from app.mascot import win32
    return win32.app_windows("spotify.exe")


def title_track(windows: Optional[Callable[[], List[Tuple[int, str]]]] = None) -> Optional[Track]:
    windows = windows or spotify_windows
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
