import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from app.config import BACKUPS_DIR, DB_PATH

BACKUP_SUFFIX = ".db"


def _safe_backup_name(name: str) -> str:
    if not name:
        raise ValueError("Nome de backup vazio.")
    base = Path(name).name
    if base != name or not base.lower().endswith(BACKUP_SUFFIX):
        raise ValueError("Nome de backup inválido.")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", base):
        raise ValueError("Nome de backup contém caracteres inválidos.")
    return base


def _integrity_ok(path: Path) -> bool:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()
        return bool(result and result[0] == "ok")
    finally:
        conn.close()


def create_backup(label: str = "manual") -> Dict[str, Any]:
    """
    Creates a consistent SQLite snapshot using the online backup API.
    The live database is only read; nothing is deleted.
    """
    safe_label = re.sub(r"[^A-Za-z0-9_-]", "", label or "manual")[:24] or "manual"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"assistant-{stamp}-{safe_label}{BACKUP_SUFFIX}"
    dest = BACKUPS_DIR / name
    if dest.exists():
        name = f"assistant-{stamp}-{safe_label}-{datetime.now().strftime('%f')}{BACKUP_SUFFIX}"
        dest = BACKUPS_DIR / name

    src = sqlite3.connect(str(DB_PATH))
    dst = sqlite3.connect(str(dest))
    try:
        with dst:
            src.backup(dst)
    finally:
        dst.close()
        src.close()

    if not _integrity_ok(dest):
        dest.unlink(missing_ok=True)
        raise RuntimeError("O backup criado falhou na verificação de integridade e foi descartado.")

    return {
        "status": "created",
        "name": name,
        "path": str(dest),
        "size_bytes": dest.stat().st_size,
        "created_at": datetime.fromtimestamp(dest.stat().st_mtime).isoformat(timespec="seconds"),
    }


def list_backups() -> List[Dict[str, Any]]:
    items = []
    for p in sorted(BACKUPS_DIR.glob(f"*{BACKUP_SUFFIX}"), key=lambda x: x.stat().st_mtime, reverse=True):
        if not p.is_file():
            continue
        stat = p.stat()
        items.append({
            "name": p.name,
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        })
    return items


def backup_path(name: str) -> Path:
    safe = _safe_backup_name(name)
    p = (BACKUPS_DIR / safe).resolve()
    if p.parent != BACKUPS_DIR.resolve():
        raise ValueError("Backup fora do diretório permitido.")
    if not p.is_file():
        raise FileNotFoundError("Backup não encontrado.")
    return p


def restore_backup(name: str, confirm: bool = False) -> Dict[str, Any]:
    """
    Restores a backup over the live database. Requires explicit confirmation.
    A pre-restore snapshot is created automatically as a safety net.
    """
    if not confirm:
        raise PermissionError("Restauração exige confirmação explícita (confirm=true).")

    source = backup_path(name)
    if not _integrity_ok(source):
        raise RuntimeError("O arquivo de backup está corrompido; restauração cancelada.")

    pre_restore = create_backup(label="pre-restore")

    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(str(DB_PATH))
    try:
        with dst:
            src.backup(dst)
        dst.execute("PRAGMA journal_mode=WAL;")
        dst.execute("PRAGMA foreign_keys=ON;")
    finally:
        dst.close()
        src.close()

    if not _integrity_ok(DB_PATH):
        raise RuntimeError(
            f"Falha após restauração. Use o backup de segurança '{pre_restore['name']}'."
        )

    return {
        "status": "restored",
        "restored_from": source.name,
        "pre_restore_backup": pre_restore["name"],
    }
