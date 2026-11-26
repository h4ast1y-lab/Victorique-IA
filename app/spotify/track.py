"""The track playing in Spotify, wherever it was read from."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

# What the Spotify window is called when nothing plays (paused, ad, home).
IDLE_TITLES = {"spotify", "spotify free", "spotify premium", "advertisement", "anúncio"}
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def clean(value: Any, limit: int) -> str:
    """One line of plain text, without control characters, cut to `limit`."""
    text = _CONTROL.sub(" ", str(value or ""))
    return " ".join(text.split())[:limit]


@dataclass(frozen=True)
class Track:
    title: str
    artist: str = ""
    album: str = ""
    playing: bool = True
    source: str = ""        # spicetify, smtc, janela

    @property
    def key(self) -> str:
        return f"{self.title.lower()}|{self.artist.lower()}"

    def facts(self) -> Dict[str, str]:
        """What the "vida própria" may see: names only."""
        out = {"musica": self.title, "artista": self.artist}
        if self.album:
            out["album"] = self.album
        return out

    def public(self) -> Dict[str, Any]:
        return {"title": self.title, "artist": self.artist, "album": self.album,
                "playing": self.playing, "source": self.source}


def make(title: Any, artist: Any = "", album: Any = "", playing: bool = True,
         source: str = "") -> Optional[Track]:
    title = clean(title, 200)
    if not title:
        return None
    return Track(title, clean(artist, 300), clean(album, 200), bool(playing), source)


def from_window_title(title: str) -> Optional[Track]:
    """Spotify's window title is "Artist - Song" while a track plays and
    "Spotify Premium" (or similar) when paused."""
    text = clean(title, 600)
    if not text or text.lower() in IDLE_TITLES or " - " not in text:
        return None
    artist, song = text.split(" - ", 1)
    return make(song, artist, source="janela")
