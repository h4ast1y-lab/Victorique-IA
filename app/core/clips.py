"""
Clipes do retrato: vídeos ou imagens fornecidos pelo usuário, um conjunto por
estado (``data/clips/<estado>/``). Nada é baixado da internet; sem clipe, a
interface usa o retrato estático.
"""
import os
from pathlib import Path
from typing import Dict, List, Optional

from app.config import DATA_DIR

CLIPS_DIR = Path(os.environ.get("ASSISTANT_CLIPS_DIR") or DATA_DIR / "clips").expanduser().resolve()

# "acordada" is the calm state between messages; the others follow the spec.
STATES = ("acordada", "dormindo", "ouvindo", "pensando", "falando", "erro")
VIDEO_EXT = {".mp4", ".webm", ".ogv", ".m4v"}
IMAGE_EXT = {".gif", ".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_EXT = VIDEO_EXT | IMAGE_EXT
MAX_PER_STATE = 50


def ensure_dirs() -> None:
    """Creates the empty state folders so the user knows where clips go."""
    try:
        for state in STATES:
            (CLIPS_DIR / state).mkdir(parents=True, exist_ok=True)
    except OSError:
        pass  # read-only location: the UI simply falls back to the static portrait


def list_clips() -> Dict[str, List[Dict[str, str]]]:
    found: Dict[str, List[Dict[str, str]]] = {}
    for state in STATES:
        folder = CLIPS_DIR / state
        items = []
        if folder.is_dir():
            for entry in sorted(folder.iterdir()):
                ext = entry.suffix.lower()
                if entry.is_file() and ext in ALLOWED_EXT:
                    items.append({"name": entry.name, "kind": "video" if ext in VIDEO_EXT else "image"})
                if len(items) >= MAX_PER_STATE:
                    break
        found[state] = items
    return found


def clip_path(state: str, name: str) -> Optional[Path]:
    """The file for ``state``/``name``, or None when anything looks off."""
    if state not in STATES or not name or name != Path(name).name:
        return None
    if Path(name).suffix.lower() not in ALLOWED_EXT:
        return None
    folder = (CLIPS_DIR / state).resolve()
    target = (folder / name).resolve()
    if target.parent != folder or not target.is_file():
        return None
    return target
