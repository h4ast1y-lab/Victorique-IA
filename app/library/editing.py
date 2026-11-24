"""The user edits books by hand in the Biblioteca: move, rename, send to the Reserva.

No approval bar (it is the user's own action, like the Organizer's Desfazer), but
everything goes through the organizer, so each edit is a batch with Desfazer, and
each one is written to the audit log.
"""
import os
from pathlib import Path
from typing import Any, Dict, Tuple

from app.library import sections
from app.tools import organizer

ACTOR = "usuario"


class BookNotFound(LookupError):
    pass


def _same(a: Path, b: Path) -> bool:
    return os.path.normcase(str(a)) == os.path.normcase(str(b))


def _book(raw_path: str) -> Tuple[Dict[str, Any], Path]:
    """The section whose folder directly holds this file, and the file."""
    gone = BookNotFound("Esse livro não está mais nessa estante.")
    if not raw_path or not str(raw_path).strip():
        raise gone
    try:
        file = Path(str(raw_path)).expanduser().resolve()
    except (OSError, ValueError):
        raise gone
    for section in sections.list_sections():
        try:
            folder = Path(section["path"]).resolve()
        except (OSError, ValueError):
            continue
        if _same(file.parent, folder):
            if not file.is_file():
                raise gone
            return section, file
    raise gone


def _audit(action: str, resource: str, details: str) -> None:
    try:
        from app.security.permissions import ActionCategory, security_manager
        security_manager.log_action(action, ActionCategory.FREE, resource, True, details)
    except Exception:
        pass


def move_book(path: str, section_id: str) -> Dict[str, Any]:
    section, file = _book(path)
    target = sections.get_section(section_id or "")
    if target is None:
        raise ValueError("Essa estante não existe.")
    if target["id"] == section["id"]:
        raise ValueError("O livro já está nessa estante.")
    dst = Path(target["path"]) / file.name
    description = f"Biblioteca: {file.name} para {target['name']}"
    result = organizer.move_files([{"origem": str(file), "destino": str(dst)}], description, actor=ACTOR)
    _audit("library_move", str(file), description)
    return result


def rename_book(path: str, new_name: str) -> Dict[str, Any]:
    _section, file = _book(path)
    new_name = (new_name or "").strip()
    if new_name == file.name:
        raise ValueError("Esse já é o nome do livro.")
    description = f"Biblioteca: {file.name} para {new_name}"
    result = organizer.rename_file(str(file), new_name, description, actor=ACTOR)
    _audit("library_rename", str(file), description)
    return result


def reserve_book(path: str) -> Dict[str, Any]:
    _section, file = _book(path)
    description = f"Biblioteca: {file.name} para a Reserva"
    result = organizer.send_to_reserve([str(file)], description, actor=ACTOR)
    _audit("library_reserve", str(file), description)
    return result
