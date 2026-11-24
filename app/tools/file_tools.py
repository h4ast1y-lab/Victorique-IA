from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from app.security.path_guard import ensure_not_hardlinked, path_guard

MAX_READ_BYTES = 5 * 1024 * 1024  # 5 MB safety cap for raw text files
MAX_DOC_BYTES = 50 * 1024 * 1024  # 50 MB safety cap for paged documents (PDF/EPUB/Office)
DEFAULT_PAGES_PER_READ = 3
# Office files (Word, Excel, PowerPoint, CSV) are paged by app/tools/office.py.
_OFFICE_EXTS = {".docx", ".xlsx", ".xlsm", ".xls", ".pptx", ".csv", ".tsv"}
_PAGED_EXTS = {".pdf", ".epub"} | _OFFICE_EXTS


def list_directory(path: str = ".") -> Dict[str, Any]:
    resolved = path_guard.validate_and_resolve(path, must_exist=True)
    if not resolved.is_dir():
        raise NotADirectoryError(f"'{path}' não é um diretório.")

    items = []
    for entry in resolved.iterdir():
        try:
            stat = entry.stat()
            items.append({
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size_bytes": stat.st_size if entry.is_file() else 0,
                "path": str(entry)
            })
        except Exception:
            continue

    return {
        "directory": str(resolved),
        "total_items": len(items),
        "items": items[:100]  # Cap list to prevent payload bloat
    }


def _search_paged_text(
    pages: List[Tuple[int, str]], query: str, max_chars: int
) -> Tuple[str, int]:
    """Busca ``query`` nas páginas e retorna trechos compactos com número de página."""
    needle = query.strip().lower()
    if not needle:
        return "", 0
    snippets: List[str] = []
    matches = 0
    used = 0
    for page_num, text in pages:
        lower = text.lower()
        pos = lower.find(needle)
        if pos == -1:
            continue
        matches += 1
        start = max(0, pos - 180)
        end = min(len(text), pos + len(needle) + 260)
        excerpt = text[start:end].replace("\n", " ").strip()
        if start > 0:
            excerpt = "..." + excerpt
        if end < len(text):
            excerpt = excerpt + "..."
        block = f"[Página {page_num}] {excerpt}"
        if used + len(block) + 2 > max_chars:
            break
        snippets.append(block)
        used += len(block) + 2
        if len(snippets) >= 10:
            break
    return "\n\n".join(snippets), matches


def _extract_pdf_pages(
    resolved: Path,
    start_page: Optional[int],
    end_page: Optional[int],
    query: Optional[str],
    max_chars: int,
) -> Dict[str, Any]:
    from pypdf import PdfReader
    from app.config import settings
    from app.rag.document_loader import ocr_engine

    reader = PdfReader(str(resolved))
    total_pages = len(reader.pages)
    if total_pages == 0:
        return {
            "file_path": str(resolved),
            "format": "pdf",
            "total_pages": 0,
            "content": "",
            "truncated": False,
        }

    if query and query.strip():
        pages = [
            (idx + 1, (page.extract_text() or "").strip())
            for idx, page in enumerate(reader.pages)
        ]
        content, matches = _search_paged_text(pages, query, max_chars)
        return {
            "file_path": str(resolved),
            "format": "pdf",
            "total_pages": total_pages,
            "query": query,
            "matches": matches,
            "content": content or f"Nenhuma ocorrência de '{query}' encontrada no texto extraível.",
            "truncated": matches > 10 or len(content) >= max_chars,
        }

    sp = max(1, min(int(start_page or 1), total_pages))
    ep = max(sp, min(int(end_page or (sp + DEFAULT_PAGES_PER_READ - 1)), total_pages))

    extracted: List[Tuple[int, str]] = []
    needs_ocr: List[int] = []
    for idx in range(sp - 1, ep):
        txt = (reader.pages[idx].extract_text() or "").strip()
        extracted.append((idx + 1, txt))
        if len(txt) < max(1, int(settings.ocr_min_chars)):
            needs_ocr.append(idx)

    ocr_results: Dict[int, str] = {}
    if needs_ocr and settings.ocr_enabled:
        try:
            ocr_results = ocr_engine.ocr_pages(resolved, needs_ocr)
        except Exception:
            ocr_results = {}

    parts: List[str] = []
    for page_num, txt in extracted:
        candidate = ocr_results.get(page_num - 1, txt).strip()
        if candidate:
            parts.append(f"--- Página {page_num}/{total_pages} ---\n{candidate}")

    joined = "\n\n".join(parts)
    truncated = len(joined) > max_chars or ep < total_pages
    return {
        "file_path": str(resolved),
        "format": "pdf",
        "total_pages": total_pages,
        "start_page": sp,
        "end_page": ep,
        "content": joined[:max_chars],
        "truncated": truncated,
        "hint": "Use start_page/end_page para ler outras páginas ou query para buscar termos.",
    }


def _read_paged_document(
    resolved: Path,
    ext: str,
    start_page: Optional[int],
    end_page: Optional[int],
    query: Optional[str],
    max_chars: int,
) -> Dict[str, Any]:
    if ext == ".pdf":
        return _extract_pdf_pages(resolved, start_page, end_page, query, max_chars)

    if ext in _OFFICE_EXTS:
        from app.tools import office

        pages, unit = office.document_pages(resolved)
    else:
        from app.rag.document_loader import document_loader

        pages = [(int(p["page"]), p["text"]) for p in document_loader._load_epub(resolved)]
        unit = "Seção"
    total_pages = len(pages)

    if query and query.strip():
        content, matches = _search_paged_text(pages, query, max_chars)
        return {
            "file_path": str(resolved),
            "format": ext.lstrip("."),
            "total_pages": total_pages,
            "query": query,
            "matches": matches,
            "content": (content or f"Nenhuma ocorrência de '{query}' encontrada.").replace(
                "[Página ", f"[{unit} "),
            "truncated": matches > 10 or len(content) >= max_chars,
        }

    if total_pages == 0:
        return {
            "file_path": str(resolved),
            "format": ext.lstrip("."),
            "total_pages": 0,
            "content": "",
            "truncated": False,
        }

    sp = max(1, min(int(start_page or 1), total_pages))
    ep = max(sp, min(int(end_page or (sp + DEFAULT_PAGES_PER_READ - 1)), total_pages))
    parts = [
        f"--- {unit} {p_num}/{total_pages} ---\n{p_txt}"
        for p_num, p_txt in pages[sp - 1 : ep]
    ]
    joined = "\n\n".join(parts)
    truncated = len(joined) > max_chars or ep < total_pages
    hint = f"Use start_page/end_page para ler outras partes ({unit.lower()}s) ou query para buscar termos."
    if ext == ".docx":
        hint += " Os marcadores [¶n] numeram os parágrafos para edit_word."
    elif ext in (".xlsx", ".xlsm", ".xls", ".csv", ".tsv"):
        hint += " Colunas em letras e linhas numeradas, como no Excel, para edit_spreadsheet."
    return {
        "file_path": str(resolved),
        "format": ext.lstrip("."),
        "total_pages": total_pages,
        "start_page": sp,
        "end_page": ep,
        "content": joined[:max_chars],
        "truncated": truncated,
        "hint": hint,
    }


def read_file(
    path: str,
    max_chars: int = 6000,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
    query: Optional[str] = None,
) -> Dict[str, Any]:
    resolved = path_guard.validate_and_resolve(path, must_exist=True)
    if not resolved.is_file():
        raise IsADirectoryError(f"'{path}' é um diretório, não um arquivo.")

    ext = resolved.suffix.lower()
    size = resolved.stat().st_size
    max_chars = max(100, min(int(max_chars), 100000))

    from app.tools.office import unsupported_hint

    hint = unsupported_hint(ext)
    if hint:
        raise ValueError(hint)

    if ext in _PAGED_EXTS:
        if size > MAX_DOC_BYTES:
            raise ValueError(
                f"Documento grande demais ({size} bytes; limite {MAX_DOC_BYTES})."
            )
        return _read_paged_document(resolved, ext, start_page, end_page, query, max_chars)

    if size > MAX_READ_BYTES:
        raise ValueError(
            f"Arquivo grande demais para leitura direta ({size} bytes; limite {MAX_READ_BYTES})."
        )

    text = resolved.read_text(encoding="utf-8", errors="replace")
    if query and query.strip():
        needle = query.strip().lower()
        hits = [
            f"L{i}: {line}"
            for i, line in enumerate(text.splitlines(), 1)
            if needle in line.lower()
        ]
        joined = "\n".join(hits)
        return {
            "file_path": str(resolved),
            "query": query,
            "matches": len(hits),
            "content": joined[:max_chars] or f"Nenhuma ocorrência de '{query}' encontrada.",
            "truncated": len(joined) > max_chars,
            "total_chars": len(text),
        }

    truncated = len(text) > max_chars
    return {
        "file_path": str(resolved),
        "content": text[:max_chars],
        "truncated": truncated,
        "total_chars": len(text),
    }


def search_files(path: str = ".", pattern: str = "*") -> Dict[str, Any]:
    resolved = path_guard.validate_and_resolve(path, must_exist=True)
    if not resolved.is_dir():
        raise NotADirectoryError(f"'{path}' não é um diretório.")

    # Recurse without following symlinks/junctions that could leave the whitelist.
    results = []
    try:
        iterator = resolved.rglob(pattern, recurse_symlinks=False)
    except TypeError:  # older Python versions
        iterator = resolved.rglob(pattern)

    for item in iterator:
        if path_guard.is_safe_path(str(item)) and not path_guard.is_protected(str(item)):
            results.append({
                "name": item.name,
                "is_dir": item.is_dir(),
                "path": str(item)
            })
            if len(results) >= 50:
                break

    return {
        "searched_directory": str(resolved),
        "pattern": pattern,
        "matches_count": len(results),
        "results": results
    }


def write_file(path: str, content: str, overwrite: bool = True) -> Dict[str, Any]:
    resolved = path_guard.validate_and_resolve(path, must_exist=False, for_write=True)
    existed = resolved.exists()
    if existed and resolved.is_dir():
        raise IsADirectoryError(f"'{path}' é um diretório; não pode ser sobrescrito como arquivo.")
    if existed and not overwrite:
        raise FileExistsError(f"O arquivo '{path}' já existe e 'overwrite' é falso.")
    if existed:
        ensure_not_hardlinked(resolved)

    resolved.parent.mkdir(parents=True, exist_ok=True)
    # Re-validate immediately before writing (parent may have been swapped).
    path_guard.validate_and_resolve(str(resolved), must_exist=False, for_write=True)
    resolved.write_text(content, encoding="utf-8")
    return {
        "file_path": str(resolved),
        "status": "success",
        "overwritten": existed,
        "bytes_written": len(content.encode("utf-8"))
    }


def create_directory(path: str) -> Dict[str, Any]:
    resolved = path_guard.validate_and_resolve(path, must_exist=False, for_write=True)
    if resolved.exists() and not resolved.is_dir():
        raise FileExistsError(f"'{path}' já existe e não é um diretório.")
    resolved.mkdir(parents=True, exist_ok=True)
    return {
        "directory": str(resolved),
        "status": "created"
    }


def delete_file(path: str, recursive: bool = False) -> Dict[str, Any]:
    """Never erases: the item goes to the Reserva (_Quarentena) and can be restored."""
    from app.tools import organizer  # lazy: organizer imports config/path_guard

    resolved = path_guard.validate_and_resolve(path, must_exist=True, for_write=True)
    if resolved.is_dir() and not recursive and any(resolved.iterdir()):
        raise PermissionError(
            "A pasta não está vazia. Para enviá-la inteira à Reserva, envie 'recursive': true."
        )
    result = organizer.send_to_reserve([str(resolved)], f"Descartar {resolved.name}")
    return {
        "original_path": str(resolved),
        "reserve_path": result["ops"][0]["dst"],
        "status": "moved_to_reserve",
        "batch_id": result["batch_id"],
        "note": "Nada foi apagado: o item está na Reserva (_Quarentena) e pode ser restaurado com Desfazer.",
    }
