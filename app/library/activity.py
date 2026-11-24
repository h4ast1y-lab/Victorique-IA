"""
O que a Victorique faz com os arquivos, para a Biblioteca encenar: ler,
listar, mover, renomear, mandar para a Reserva, desfazer e escrever.

Alimentado pelo organizador (todo mover/renomear/Reserva/desfazer passa por
ele), pelas ferramentas locais do registro e pelas ferramentas do Claude Code
e do Codex. Fica só na memória: as últimas 200 ações, numeradas.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, Optional, Tuple

logger = logging.getLogger(__name__)

KINDS = ("read", "list", "move", "rename", "reserve", "undo", "write")
KEEP = 200

# Built-in tools of the agents (Claude Code; Codex maps its items to these too).
AGENT_TOOLS = {
    "Read": "read", "NotebookRead": "read",
    "Write": "write", "Edit": "write", "MultiEdit": "write", "NotebookEdit": "write",
    "Glob": "list", "Grep": "list", "LS": "list",
}
# Tools of the app's own registry (organizer tools are recorded by the organizer).
REGISTRY_TOOLS = {"read_file": "read", "list_directory": "list", "search_files": "list", "write_file": "write"}

_lock = threading.Lock()
_events: Deque[Dict[str, Any]] = deque(maxlen=KEEP)
_seq = 0


def _section(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    try:
        from app.library import sections
        return sections.section_for(path)
    except Exception:
        return None


def record(kind: str, src: Optional[str], dst: Optional[str] = None, actor: str = "victorique") -> None:
    """Never raises: the library is a show, not part of the operation."""
    global _seq
    if kind not in KINDS or not src:
        return
    try:
        event = {
            "kind": kind, "actor": actor, "at": time.time(),
            "src": str(src), "dst": str(dst) if dst else None,
            "name": Path(str(dst or src)).name,
            "src_section": _section(str(src)), "dst_section": _section(str(dst)) if dst else None,
        }
        with _lock:
            _seq += 1
            event["seq"] = _seq
            _events.append(event)
    except Exception:
        logger.debug("Biblioteca: atividade não registrada", exc_info=True)


def record_moves(kind: str, moves: Iterable[Tuple[Any, Any]], actor: str = "victorique") -> None:
    for src, dst in moves:
        record(kind, str(src), str(dst), actor)


def record_tool(tool: str, arguments: Dict[str, Any], actor: str = "victorique") -> None:
    """An agent or registry tool that succeeded: reads, listings and writes."""
    kind = AGENT_TOOLS.get(tool) or REGISTRY_TOOLS.get(tool)
    if not kind or not isinstance(arguments, dict):
        return
    path = (arguments.get("file_path") or arguments.get("notebook_path") or arguments.get("path")
            or arguments.get("directory"))
    record(kind, path, actor=actor)


def since(seq: int = 0) -> Dict[str, Any]:
    with _lock:
        events = [e for e in _events if e["seq"] > seq]
        last = _seq
    return {"events": events, "last": last}


def clear() -> None:
    """Tests only."""
    global _seq
    with _lock:
        _events.clear()
        _seq = 0
