from pathlib import Path
from typing import Dict, Any
from app.security.path_guard import path_guard

MAX_READ_BYTES = 5 * 1024 * 1024  # 5 MB safety cap before reading into memory


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


def read_file(path: str, max_chars: int = 15000) -> Dict[str, Any]:
    resolved = path_guard.validate_and_resolve(path, must_exist=True)
    if not resolved.is_file():
        raise IsADirectoryError(f"'{path}' é um diretório, não um arquivo.")

    size = resolved.stat().st_size
    if size > MAX_READ_BYTES:
        raise ValueError(
            f"Arquivo grande demais para leitura direta ({size} bytes; limite {MAX_READ_BYTES})."
        )

    max_chars = max(100, min(int(max_chars), 100000))
    text = resolved.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > max_chars
    return {
        "file_path": str(resolved),
        "content": text[:max_chars],
        "truncated": truncated,
        "total_chars": len(text)
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
