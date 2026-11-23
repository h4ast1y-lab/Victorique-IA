"""
Organização segura de arquivos (a "Biblioteca"): mover, renomear e descartar.

Regras:
  * nada é apagado: descartes vão para ``_Quarentena`` (a Reserva), dentro da
    própria pasta autorizada de onde o arquivo saiu;
  * um lote é validado por inteiro antes de mover qualquer coisa; se um
    movimento falha no meio, os anteriores são revertidos;
  * cada lote fica registrado em ``data/operations.json`` e pode ser desfeito.
"""
import json
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import DATA_DIR
from app.security.path_guard import path_guard

RESERVE_DIR_NAME = "_Quarentena"
LOG_PATH = DATA_DIR / "operations.json"
MAX_LOG_BATCHES = 300
MAX_MOVES_PER_BATCH = 500

_lock = threading.Lock()

Move = Tuple[Path, Path]


# ----------------- Log -----------------
def _read_log() -> List[Dict[str, Any]]:
    try:
        return json.loads(LOG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return []


def _write_log(batches: List[Dict[str, Any]]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = LOG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(batches[-MAX_LOG_BATCHES:], ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(LOG_PATH)


def list_batches(limit: int = 50) -> List[Dict[str, Any]]:
    """Most recent first."""
    return list(reversed(_read_log()))[: max(1, limit)]


# ----------------- Validation -----------------
def _validate(moves: List[Move]) -> None:
    if not moves:
        raise ValueError("O plano está vazio.")
    if len(moves) > MAX_MOVES_PER_BATCH:
        raise ValueError(f"Plano grande demais (máximo {MAX_MOVES_PER_BATCH} itens por lote).")
    seen_dst = set()
    for src, dst in moves:
        path_guard.validate_and_resolve(str(src), must_exist=True, for_write=True)
        path_guard.validate_and_resolve(str(dst), must_exist=False, for_write=True)
        if src == dst:
            raise ValueError(f"Origem e destino iguais: {src}")
        if dst.exists():
            raise FileExistsError(f"O destino já existe, nada foi movido: {dst}")
        if src.is_dir() and (dst == src or src in dst.parents):
            raise ValueError(f"Não dá para mover uma pasta para dentro dela mesma: {src}")
        key = str(dst).lower()
        if key in seen_dst:
            raise ValueError(f"Dois itens iriam para o mesmo destino: {dst}")
        seen_dst.add(key)


def _resolve_pair(src: str, dst: str) -> Move:
    if not src or not dst:
        raise ValueError("Cada item do plano precisa de origem e destino.")
    return Path(src).expanduser().resolve(), Path(dst).expanduser().resolve()


# ----------------- Execution -----------------
def _apply(moves: List[Move]) -> None:
    """Moves everything or nothing (reverts the done part on failure)."""
    done: List[Move] = []
    try:
        for src, dst in moves:
            # Re-check right before touching the disk.
            path_guard.validate_and_resolve(str(src), must_exist=True, for_write=True)
            path_guard.validate_and_resolve(str(dst), must_exist=False, for_write=True)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            done.append((src, dst))
    except Exception:
        for src, dst in reversed(done):
            try:
                shutil.move(str(dst), str(src))
            except Exception:
                pass  # reported by the raise below; the log still lists the batch
        raise


def _record(kind: str, description: str, moves: List[Move]) -> Dict[str, Any]:
    batch = {
        "id": uuid.uuid4().hex[:12],
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "kind": kind,
        "description": description,
        "status": "done",
        "ops": [{"src": str(s), "dst": str(d)} for s, d in moves],
    }
    batches = _read_log()
    batches.append(batch)
    _write_log(batches)
    return batch


def _run(kind: str, description: str, moves: List[Move]) -> Dict[str, Any]:
    with _lock:
        _validate(moves)
        _apply(moves)
        batch = _record(kind, description, moves)
    return {
        "status": "done",
        "batch_id": batch["id"],
        "moved": len(moves),
        "ops": batch["ops"],
        "note": "Registrado no histórico; pode ser desfeito pelo Organizador.",
    }


def reserve_root_for(path: Path) -> Path:
    """The authorized folder that holds ``path`` (deepest match), else its parent."""
    best: Optional[Path] = None
    for root in path_guard.authorized_dirs:
        if path == root or root in path.parents:
            if best is None or len(root.parts) > len(best.parts):
                best = root
    return best or path.parent


def _reserve_destination(path: Path, stamp: str) -> Path:
    root = reserve_root_for(path)
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = Path(path.name)
    return root / RESERVE_DIR_NAME / stamp / relative


# ----------------- Public tools -----------------
def move_files(moves: List[Dict[str, str]], descricao: str = "") -> Dict[str, Any]:
    """Plano de movimentos [{"origem": ..., "destino": ...}], executado em lote."""
    if not isinstance(moves, list):
        raise ValueError("'moves' deve ser uma lista de {origem, destino}.")
    pairs = [_resolve_pair(m.get("origem") or m.get("src"), m.get("destino") or m.get("dst"))
             for m in moves if isinstance(m, dict)]
    return _run("move", descricao or f"Mover {len(pairs)} item(ns)", pairs)


def rename_file(path: str, new_name: str) -> Dict[str, Any]:
    new_name = (new_name or "").strip()
    if not new_name or any(sep in new_name for sep in ("/", "\\")) or new_name in (".", ".."):
        raise ValueError("Informe só o novo nome, sem pastas.")
    src = Path(path).expanduser().resolve()
    return _run("rename", f"Renomear {src.name} para {new_name}", [(src, src.with_name(new_name))])


def send_to_reserve(paths: List[str], descricao: str = "") -> Dict[str, Any]:
    """Descarta itens movendo-os para a Reserva (_Quarentena). Nunca apaga."""
    if isinstance(paths, str):
        paths = [paths]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    moves = []
    for raw in paths:
        src = Path(raw).expanduser().resolve()
        if RESERVE_DIR_NAME in src.parts:
            raise ValueError(f"'{src}' já está na Reserva.")
        moves.append((src, _reserve_destination(src, stamp)))
    return _run("reserve", descricao or f"Enviar {len(moves)} item(ns) para a Reserva", moves)


def _prune_empty_dirs(emptied: List[Path]) -> None:
    """Removes folders a batch created and that ended up empty after an undo.
    rmdir refuses non-empty folders, so nothing with content can be lost."""
    for path in emptied:
        root = reserve_root_for(path)
        folder = path.parent
        while folder != root and root in folder.parents:
            try:
                path_guard.validate_and_resolve(str(folder), must_exist=True, for_write=True)
                folder.rmdir()
            except (OSError, PermissionError):
                break
            folder = folder.parent


def undo(batch_id: Optional[str] = None) -> Dict[str, Any]:
    """Desfaz um lote (o último ainda ativo, se nenhum for indicado)."""
    with _lock:
        batches = _read_log()
        active = [b for b in batches if b.get("status") == "done"]
        if not active:
            raise ValueError("Não há operação para desfazer.")
        batch = next((b for b in active if b["id"] == batch_id), None) if batch_id else active[-1]
        if batch is None:
            raise ValueError("Esse lote não existe ou já foi desfeito.")
        reverse = [(Path(op["dst"]), Path(op["src"])) for op in reversed(batch["ops"])]
        _validate(reverse)
        _apply(reverse)
        _prune_empty_dirs([src for src, _ in reverse])
        batch["status"] = "undone"
        batch["undone_at"] = datetime.now().isoformat(timespec="seconds")
        _write_log(batches)
    return {"status": "undone", "batch_id": batch["id"], "restored": len(reverse)}
