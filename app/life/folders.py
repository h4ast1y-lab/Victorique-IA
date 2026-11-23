"""
"Pasta bagunçada": a shallow look at the authorized folders.

Only names and counts are read (never file contents): for each authorized
folder and its direct subfolders, how many files sit loose at the top level
and of how many kinds. Hidden, system and app folders are skipped.
"""
import os
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

MIN_FILES = 25
MIN_KINDS = 5
MAX_SUBFOLDERS = 40
MAX_ENTRIES = 3000
_SKIP_FILES = {"desktop.ini", "thumbs.db"}


def _skip_dir(name: str) -> bool:
    return name.startswith((".", "_", "$")) or name.lower() in {"node_modules", "__pycache__"}


def loose_files(folder: Path) -> Dict[str, Any]:
    files = 0
    kinds: Counter = Counter()
    try:
        with os.scandir(folder) as entries:
            for index, entry in enumerate(entries):
                if index >= MAX_ENTRIES:
                    break
                name = entry.name
                if name.startswith(".") or name.lower() in _SKIP_FILES:
                    continue
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                files += 1
                ext = os.path.splitext(name)[1].lower().lstrip(".")
                kinds[ext or "sem extensão"] += 1
    except OSError:
        pass
    return {"n": files, "kinds": kinds}


def candidate_folders(roots: Iterable[Path], is_protected) -> List[Path]:
    found: List[Path] = []
    for root in roots:
        if not root.is_dir() or is_protected(str(root)):
            continue
        found.append(root)
        try:
            subdirs = sorted(
                (e for e in os.scandir(root) if not _skip_dir(e.name) and e.is_dir(follow_symlinks=False)),
                key=lambda e: e.name.lower(),
            )[:MAX_SUBFOLDERS]
        except OSError:
            continue
        found.extend(Path(e.path) for e in subdirs if not is_protected(e.path))
    return found


def messy_folders(roots: Iterable[Path], is_protected=lambda p: False,
                  min_files: int = MIN_FILES, min_kinds: int = MIN_KINDS) -> List[Dict[str, Any]]:
    """Messiest first: [{"path", "pasta", "n", "tipos"}]. "path" stays in the app;
    only the folder name and counts are ever shown to the model."""
    messy = []
    for folder in candidate_folders(roots, is_protected):
        info = loose_files(folder)
        if info["n"] >= min_files and len(info["kinds"]) >= min_kinds:
            messy.append({
                "path": str(folder),
                "pasta": folder.name or str(folder),
                "n": info["n"],
                "tipos": [k for k, _ in info["kinds"].most_common(4)],
            })
    return sorted(messy, key=lambda f: f["n"], reverse=True)
