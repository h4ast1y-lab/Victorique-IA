"""
Anexos do chat: imagens e documentos enviados numa mensagem.

Ficam só na conversa: em ``data/chat_files/<id>/`` (pasta protegida do app),
nunca na aba Documentos nem no índice de busca. Apagar a conversa apaga os
anexos dela; anexos enviados mas nunca usados numa mensagem somem depois de um dia.

Cada motor recebe o que sabe usar:
  * Claude Code: as imagens como blocos de imagem; documentos como caminho +
    prévia do texto (ela lê o resto com ``ler_documento``);
  * Codex: imagens com ``--image``; documentos como caminho + prévia;
  * Ollama: imagens em ``images`` (modelos com visão); documentos como prévia.
"""
from __future__ import annotations

import base64
import io
import logging
import re
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, BinaryIO, Dict, Iterable, List, Optional, Tuple

from app.config import DATA_DIR, settings
from app.memory.database import get_connection

logger = logging.getLogger(__name__)

ATTACH_DIR = DATA_DIR / "chat_files"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
DOCUMENT_EXTS = {
    ".pdf", ".docx", ".xlsx", ".xlsm", ".xls", ".pptx", ".csv", ".tsv", ".epub",
    ".txt", ".md", ".json", ".xml", ".html", ".htm", ".yaml", ".yml", ".log",
    ".py", ".js", ".ts", ".css", ".ini", ".cfg", ".toml", ".sql",
}
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_PER_MESSAGE = 10
MAX_IMAGE_SIDE = 1568            # what Claude's vision uses without downscaling again
PREVIEW_CHARS = 3500
ORPHAN_HOURS = 24
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
# The table chat_attachments is created by app/memory/database.init_db.


class AttachmentError(ValueError):
    """Bad upload or reference: becomes a 400 for the UI."""


def kind_of(filename: str) -> Optional[str]:
    ext = Path(filename or "").suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in DOCUMENT_EXTS:
        return "document"
    return None


def safe_name(filename: str) -> str:
    """A readable Windows-safe file name (accents kept, path tricks removed)."""
    name = Path(str(filename or "").replace("\\", "/")).name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(". ")
    stem, ext = Path(name).stem, Path(name).suffix.lower()
    stem = stem[:100] or "anexo"
    if stem.upper() in _RESERVED:
        stem = f"_{stem}"
    return f"{stem}{ext}"


def _mime(kind: str, ext: str, given: Optional[str]) -> str:
    if kind == "image":
        return {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
                ".gif": "image/gif", ".bmp": "image/bmp"}.get(ext, "image/png")
    return (given or "application/octet-stream")[:100]


def public(row: Dict[str, Any]) -> Dict[str, Any]:
    """What the UI and the stored message keep (no disk path)."""
    return {
        "id": row["id"],
        "name": row["name"],
        "kind": row["kind"],
        "mime": row.get("mime"),
        "size": row.get("size"),
        "url": f"/api/chat/attachments/{row['id']}",
    }


def path_of(row: Dict[str, Any]) -> Path:
    return ATTACH_DIR / row["id"] / row["stored_name"]


def save_upload(stream: BinaryIO, filename: str, content_type: Optional[str] = None) -> Dict[str, Any]:
    """Stores one uploaded file (not yet bound to a conversation)."""
    cleanup_orphans()
    original = Path(str(filename or "")).name
    if not original:
        raise AttachmentError("Nome de arquivo ausente.")
    kind = kind_of(original)
    if not kind:
        raise AttachmentError(
            f"Formato '{Path(original).suffix or original}' não pode ser anexado. "
            "Envie imagens (PNG, JPG, WEBP, GIF) ou documentos (PDF, Word, Excel, PowerPoint, textos)."
        )
    limit = MAX_IMAGE_BYTES if kind == "image" else settings.max_upload_mb * 1024 * 1024
    att_id = uuid.uuid4().hex
    stored = safe_name(original)
    folder = ATTACH_DIR / att_id
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / stored
    written = 0
    try:
        with open(target, "wb") as out:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > limit:
                    raise AttachmentError(f"Arquivo maior que o limite de {limit // (1024 * 1024)} MB.")
                out.write(chunk)
        if written == 0:
            raise AttachmentError("O arquivo está vazio.")
        if kind == "image":
            _check_image(target)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise

    row = {
        "id": att_id, "name": original[:200], "stored_name": stored, "kind": kind,
        "mime": _mime(kind, target.suffix.lower(), content_type), "size": written,
    }
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO chat_attachments (id, conversation_id, name, stored_name, kind, mime, size, created_at) "
            "VALUES (?, NULL, ?, ?, ?, ?, ?, ?)",
            (att_id, row["name"], stored, kind, row["mime"], written, datetime.now().isoformat()),
        )
    return public(row)


def _check_image(path: Path) -> None:
    from PIL import Image

    try:
        with Image.open(path) as img:
            img.verify()
    except Exception as exc:
        raise AttachmentError("A imagem está corrompida ou não é uma imagem de verdade.") from exc


def get(att_id: str) -> Optional[Dict[str, Any]]:
    if not re.fullmatch(r"[0-9a-f]{32}", str(att_id or "")):
        return None
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM chat_attachments WHERE id = ?", (att_id,)).fetchone()
    return dict(row) if row else None


def bind(ids: Iterable[str], conversation_id: str) -> List[Dict[str, Any]]:
    """Claims uploaded files for a conversation; returns the full rows, in order."""
    ids = [str(i) for i in ids or [] if i]
    if not ids:
        return []
    if len(ids) > MAX_PER_MESSAGE:
        raise AttachmentError(f"No máximo {MAX_PER_MESSAGE} anexos por mensagem.")
    rows = []
    for att_id in dict.fromkeys(ids):
        row = get(att_id)
        if not row or not path_of(row).is_file():
            raise AttachmentError("Um dos anexos não existe mais. Anexe o arquivo de novo.")
        if row["conversation_id"] not in (None, conversation_id):
            raise AttachmentError("Esse anexo pertence a outra conversa.")
        rows.append(row)
    with get_connection() as conn:
        conn.executemany(
            "UPDATE chat_attachments SET conversation_id = ? WHERE id = ?",
            [(conversation_id, r["id"]) for r in rows],
        )
    for r in rows:
        r["conversation_id"] = conversation_id
    return rows


def discard(att_id: str) -> None:
    """An upload the user removed before sending."""
    with get_connection() as conn:
        conn.execute("DELETE FROM chat_attachments WHERE id = ? AND conversation_id IS NULL", (att_id,))
    shutil.rmtree(ATTACH_DIR / att_id, ignore_errors=True)


def delete_for_conversation(conversation_id: str) -> int:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id FROM chat_attachments WHERE conversation_id = ?", (conversation_id,)
        ).fetchall()
        conn.execute("DELETE FROM chat_attachments WHERE conversation_id = ?", (conversation_id,))
    for row in rows:
        shutil.rmtree(ATTACH_DIR / row["id"], ignore_errors=True)
    return len(rows)


def cleanup_orphans(max_age_hours: float = ORPHAN_HOURS) -> int:
    """Files uploaded but never sent (the user removed the chip or closed the app)."""
    cutoff = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
    try:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id FROM chat_attachments WHERE conversation_id IS NULL AND created_at < ?",
                (cutoff,),
            ).fetchall()
            conn.execute(
                "DELETE FROM chat_attachments WHERE conversation_id IS NULL AND created_at < ?",
                (cutoff,),
            )
    except Exception:
        logger.debug("Anexos: limpeza falhou", exc_info=True)
        return 0
    for row in rows:
        shutil.rmtree(ATTACH_DIR / row["id"], ignore_errors=True)
    return len(rows)


# ----------------------------------------------------------------- for the models
def images(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in rows or [] if r.get("kind") == "image"]


def documents(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in rows or [] if r.get("kind") == "document"]


def image_base64(row: Dict[str, Any], max_side: int = MAX_IMAGE_SIDE) -> Tuple[str, str]:
    """(media_type, base64) of the image, downscaled and re-encoded for a model."""
    from PIL import Image

    with Image.open(path_of(row)) as img:
        img.seek(0)
        has_alpha = img.mode in ("RGBA", "LA", "P") and (
            img.mode != "P" or "transparency" in img.info
        )
        img = img.convert("RGBA" if has_alpha else "RGB")
        if max(img.size) > max_side:
            img.thumbnail((max_side, max_side), Image.LANCZOS)
        buffer = io.BytesIO()
        if has_alpha:
            img.save(buffer, format="PNG", optimize=True)
            media = "image/png"
        else:
            img.save(buffer, format="JPEG", quality=90)
            media = "image/jpeg"
    return media, base64.b64encode(buffer.getvalue()).decode("ascii")


def document_preview(row: Dict[str, Any], max_chars: int = PREVIEW_CHARS) -> str:
    from app.tools.file_tools import read_file

    try:
        result = read_file(str(path_of(row)), max_chars=max_chars)
    except Exception as exc:
        return f"(não consegui extrair o texto: {exc})"
    content = (result.get("content") or "").strip()
    if not content:
        return "(sem texto extraível; pode ser um PDF escaneado ou só imagens)"
    total = result.get("total_pages")
    if result.get("truncated"):
        more = f" — documento com {total} partes; leia o resto pelo caminho" if total else " — continua"
        content += f"\n[…{more}]"
    return content


def prompt_note(rows: List[Dict[str, Any]], with_preview: bool = True,
                images_inline: bool = True) -> str:
    """Text that tells the model what came attached to the user's message."""
    if not rows:
        return ""
    lines = ["[ANEXOS DESTA MENSAGEM — ficam só no chat, não estão em Documentos]"]
    for row in rows:
        path = path_of(row)
        if row["kind"] == "image":
            seen = " (a imagem segue junto desta mensagem)" if images_inline else ""
            lines.append(f"- Imagem: {row['name']}{seen}. Arquivo: {path}")
        else:
            lines.append(f"- Documento: {row['name']}. Caminho: {path}")
            if with_preview:
                lines.append("  Prévia do conteúdo:\n" + _indent(document_preview(row)))
    lines.append(
        "Os anexos ficam na pasta de dados do app, que é protegida: para mudar um documento, "
        "edite-o e a versão nova irá para Documentos\\Victorique; o original no chat fica intacto."
    )
    return "\n".join(lines)


def history_note(attachments: List[Dict[str, Any]]) -> str:
    """Short line for older messages (names only)."""
    if not attachments:
        return ""
    names = ", ".join(f"{a.get('name')} ({'imagem' if a.get('kind') == 'image' else 'documento'})"
                      for a in attachments)
    return f"[anexos: {names}]"


def _indent(text: str) -> str:
    return "\n".join("    " + line for line in text.splitlines())
