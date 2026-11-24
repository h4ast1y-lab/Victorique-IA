"""
Seções da Biblioteca: cada uma é uma pasta importante do computador, e cada
arquivo dela é um livro na estante.

As seções ficam em DATA_DIR/library.json. Por padrão aparecem Downloads,
Documentos, Área de Trabalho, Imagens, Músicas e Vídeos (só as que existem;
não quando ASSISTANT_AUTHORIZED_DIRS restringe as pastas ou com
ASSISTANT_LIBRARY_DEFAULTS=0). O usuário vincula outras pastas.

Cada seção vira um diretório autorizado do path_guard: ela pode ler e listar
lá; escrever, mover e excluir continuam pedindo aprovação como antes.
Recusadas: raízes de disco, a pasta do usuário inteira (e as acima dela),
pastas do sistema e as do próprio aplicativo.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import BASE_DIR, DATA_DIR
from app.security.path_guard import path_guard

logger = logging.getLogger(__name__)

MAX_BOOKS = 120
MAX_SECTIONS = 24
NAME_LIMIT = 40
SKIP_NAMES = {"desktop.ini", "thumbs.db", ".ds_store"}

# id, nome na estante, KNOWNFOLDERID do Windows, nome da pasta na home
_DEFAULTS: Tuple[Tuple[str, str, str, str], ...] = (
    ("downloads", "Downloads", "{374DE290-123F-4565-9164-39C4925E467B}", "Downloads"),
    ("documentos", "Documentos", "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}", "Documents"),
    ("desktop", "Área de Trabalho", "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}", "Desktop"),
    ("imagens", "Imagens", "{33E28130-4E1E-4676-835A-98395C3BC3BB}", "Pictures"),
    ("musicas", "Músicas", "{4BD8D571-6D19-48D3-BE97-422220080E43}", "Music"),
    ("videos", "Vídeos", "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}", "Videos"),
)

_lock = threading.RLock()
_authorized: List[Path] = []   # what this module added to path_guard


def _store_path() -> Path:
    return DATA_DIR / "library.json"


def _defaults_enabled() -> bool:
    if os.environ.get("ASSISTANT_LIBRARY_DEFAULTS", "1").lower() in ("0", "false", "no"):
        return False
    # An explicit folder list is a deliberate restriction: start empty.
    return not os.environ.get("ASSISTANT_AUTHORIZED_DIRS")


def _known_folder(guid: str) -> Optional[Path]:
    """The real location of a Windows known folder (follows OneDrive redirection)."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                        ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

        u = uuid.UUID(guid)
        g = GUID(u.time_low, u.time_mid, u.time_hi_version,
                 (ctypes.c_ubyte * 8).from_buffer_copy(u.bytes[8:]))
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(out)) != 0:
            return None
        try:
            return Path(out.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(out)
    except Exception:
        return None


def default_folders() -> List[Tuple[str, str, Path]]:
    """(id, name, path) of the default sections that exist on this computer."""
    found = []
    for ident, name, guid, fallback in _DEFAULTS:
        path = _known_folder(guid) or (Path.home() / fallback)
        if path.is_dir():
            found.append((ident, name, path))
    return found


# ----------------- Storage -----------------
def _load() -> Dict[str, Any]:
    try:
        data = json.loads(_store_path().read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("sections"), list):
            return data
    except FileNotFoundError:
        pass
    except Exception:
        logger.warning("library.json ilegível; recomeçando as seções.")
    return {"sections": [], "seeded": False}


def _save(data: Dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _seeded(data: Dict[str, Any]) -> Dict[str, Any]:
    """Adds the default sections the first time (once; hiding one is remembered)."""
    if data.get("seeded"):
        return data
    data["seeded"] = True
    if _defaults_enabled():
        known = {s["id"] for s in data["sections"]}
        for ident, name, path in default_folders():
            if ident not in known:
                data["sections"].append({"id": ident, "name": name, "path": str(path), "kind": "default"})
    _save(data)
    return data


def _public(section: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": section["id"], "name": section["name"], "path": section["path"],
        "kind": section.get("kind", "linked"), "exists": Path(section["path"]).is_dir(),
    }


def list_sections() -> List[Dict[str, Any]]:
    with _lock:
        data = _seeded(_load())
        return [_public(s) for s in data["sections"] if not s.get("hidden")]


def get_section(section_id: str) -> Optional[Dict[str, Any]]:
    return next((s for s in list_sections() if s["id"] == section_id), None)


# ----------------- Linking -----------------
def _within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def refusal(path: Path) -> Optional[str]:
    """Why this folder cannot be a section, or None when it can."""
    if path.parent == path or str(path) == path.anchor:
        return "Uma unidade inteira é grande demais para uma estante. Escolha uma pasta dentro dela."
    home = Path.home().resolve()
    if _within(home, path):
        return "A sua pasta de usuário inteira é grande demais. Escolha uma pasta dentro dela, como Downloads."
    if path_guard.is_system_path(path):
        return "Pastas do Windows, de programas e do AppData ficam de fora da Biblioteca."
    for own in (BASE_DIR.resolve(), DATA_DIR.resolve()):
        if _within(path, own):
            return "As pastas do próprio aplicativo ficam de fora da Biblioteca."
    return None


def link(raw_path: str, name: Optional[str] = None) -> Dict[str, Any]:
    """Adds a folder as a new section. ValueError with a message for the user."""
    text = str(raw_path or "").strip().strip('"')
    if not text:
        raise ValueError("Informe a pasta.")
    try:
        path = Path(text).expanduser().resolve()
    except Exception:
        raise ValueError("Caminho inválido.") from None
    if not path.is_absolute() or not path.is_dir():
        raise ValueError("Essa pasta não existe.")
    reason = refusal(path)
    if reason:
        raise ValueError(reason)
    label = (name or "").strip()[:NAME_LIMIT] or path.name[:NAME_LIMIT] or str(path)
    with _lock:
        data = _seeded(_load())
        for section in data["sections"]:
            if Path(section["path"]).resolve() == path:
                if section.get("hidden"):
                    section["hidden"] = False
                    section["name"] = label
                    _save(data)
                    apply_authorization()
                    return _public(section)
                raise ValueError(f"Essa pasta já é a seção \"{section['name']}\".")
        if sum(1 for s in data["sections"] if not s.get("hidden")) >= MAX_SECTIONS:
            raise ValueError(f"A Biblioteca já tem {MAX_SECTIONS} seções. Desvincule uma antes.")
        section = {"id": "s-" + uuid.uuid4().hex[:10], "name": label, "path": str(path), "kind": "linked"}
        data["sections"].append(section)
        _save(data)
    apply_authorization()
    return _public(section)


def unlink(section_id: str) -> None:
    """Linked sections are removed; default ones are hidden (they would come back otherwise)."""
    with _lock:
        data = _seeded(_load())
        section = next((s for s in data["sections"] if s["id"] == section_id and not s.get("hidden")), None)
        if section is None:
            raise KeyError(section_id)
        if section.get("kind") == "default":
            section["hidden"] = True
        else:
            data["sections"].remove(section)
        _save(data)
    apply_authorization()


def apply_authorization() -> None:
    """Keeps path_guard's authorized folders in step with the visible sections."""
    with _lock:
        wanted = []
        for section in list_sections():
            path = Path(section["path"])
            if section["exists"] and refusal(path.resolve()) is None:
                wanted.append(path.resolve())
        for old in list(_authorized):
            if old not in wanted:
                path_guard.remove_authorized_directory(str(old))
                _authorized.remove(old)
        for path in wanted:
            if path not in _authorized:
                if path not in path_guard.authorized_dirs:
                    path_guard.add_authorized_directory(str(path))
                    _authorized.append(path)


# ----------------- Books -----------------
def books(section_id: str, limit: int = MAX_BOOKS) -> Dict[str, Any]:
    """The newest files on the shelf (metadata only, never the content)."""
    section = get_section(section_id)
    if section is None:
        raise KeyError(section_id)
    root = Path(section["path"])
    files = []
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                name = entry.name
                if name.startswith(".") or name.lower() in SKIP_NAMES:
                    continue
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                if getattr(info, "st_file_attributes", 0) & 0x6:  # hidden or system
                    continue
                files.append({
                    "name": name, "path": entry.path, "ext": Path(name).suffix.lower().lstrip(".")[:10],
                    "size": info.st_size, "modified": info.st_mtime,
                })
    except OSError as exc:
        return {"section": section, "files": [], "total": 0, "error": str(exc)}
    files.sort(key=lambda f: f["modified"], reverse=True)
    return {"section": section, "files": files[:max(1, int(limit))], "total": len(files)}


def section_for(raw_path: Optional[str]) -> Optional[str]:
    """Id of the (most specific) section holding this path."""
    if not raw_path:
        return None
    try:
        path = Path(str(raw_path)).expanduser().resolve()
    except Exception:
        return None
    best, depth = None, -1
    for section in list_sections():
        root = Path(section["path"]).resolve()
        if _within(path, root) and len(root.parts) > depth:
            best, depth = section["id"], len(root.parts)
    return best
