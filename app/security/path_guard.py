import os
from pathlib import Path
from typing import List, Optional
from app.config import settings, BASE_DIR, DATA_DIR, BACKUPS_DIR, DB_PATH

class PathGuard:
    """
    Validates filesystem access requested by the model/tools.

    Rules:
      * reads/writes are only allowed inside explicitly authorized directories;
      * symlinks and junctions are resolved before validation;
      * writes and deletions are refused for application code, the database,
        backups and the whole data directory, so the assistant cannot modify
        its own permissions or destroy user data.
    """

    def __init__(self, authorized_directories: Optional[List[str]] = None):
        self.authorized_dirs = [
            Path(p).expanduser().resolve()
            for p in (authorized_directories or settings.authorized_directories)
        ]
        self.protected_write_paths = self._default_protected_paths()

    def _default_protected_paths(self) -> List[Path]:
        protected = [
            DATA_DIR,
            BACKUPS_DIR,
            DB_PATH,
            BASE_DIR,
        ]
        return [p.expanduser().resolve() for p in protected]

    def add_authorized_directory(self, path: str):
        resolved = Path(path).expanduser().resolve()
        if resolved not in self.authorized_dirs:
            self.authorized_dirs.append(resolved)

    def add_protected_path(self, path: str):
        resolved = Path(path).expanduser().resolve()
        if resolved not in self.protected_write_paths:
            self.protected_write_paths.append(resolved)

    @staticmethod
    def _is_within(path: Path, directory: Path) -> bool:
        try:
            path.relative_to(directory)
            return True
        except ValueError:
            return False

    def is_safe_path(self, target_path: str) -> bool:
        r"""
        True when the resolved target is inside an authorized directory.
        When allow_all_directories is enabled (opt-in), allows free navigation
        across any absolute path on the computer (C:\, D:\, etc.). The turbo
        mode only skips approvals; it never widens the directory scope.
        """
        try:
            resolved_target = Path(target_path).expanduser().resolve()
            if not resolved_target.is_absolute():
                return False
            if getattr(settings, "allow_all_directories", False):
                return True
            for allowed in self.authorized_dirs:
                if self._is_within(resolved_target, allowed):
                    return True
            return False
        except Exception:
            return False

    def is_protected(self, target_path: str) -> bool:
        try:
            resolved = Path(target_path).expanduser().resolve()
        except Exception:
            return True
        for protected in self.protected_write_paths:
            if self._is_within(resolved, protected):
                return True
        return False

    def validate_and_resolve(
        self,
        target_path: str,
        must_exist: bool = False,
        for_write: bool = False,
    ) -> Path:
        """
        Resolves a path and raises PermissionError when out of bounds.
        Validation is repeated immediately before every operation.
        """
        if target_path is None or str(target_path).strip() == "":
            raise PermissionError("Caminho vazio não é permitido.")

        resolved = Path(str(target_path)).expanduser().resolve()
        if not self.is_safe_path(str(resolved)):
            raise PermissionError(
                f"Acesso Negado: o caminho '{target_path}' não está na lista de diretórios autorizados."
            )
        if for_write and self.is_protected(str(resolved)):
            raise PermissionError(
                f"Acesso Negado: '{resolved}' é um caminho protegido (código do aplicativo, banco ou backups)."
            )
        if must_exist and not resolved.exists():
            raise FileNotFoundError(f"Arquivo ou diretório não encontrado: '{target_path}'")
        return resolved


path_guard = PathGuard()
