import os
import re
import tempfile
from pathlib import Path
from typing import List, Optional
from app.config import settings, BASE_DIR, DATA_DIR, BACKUPS_DIR, DB_PATH

# Windows device names are reserved in every folder, with or without extension.
_RESERVED_NAME = re.compile(r"^(con|prn|aux|nul|com[0-9¹²³]|lpt[0-9¹²³]|conin\$|conout\$)$", re.I)
_DRIVE = re.compile(r"^[a-zA-Z]:$")


def check_windows_path_syntax(raw: str, for_write: bool = False) -> None:
    r"""
    Refuses path forms that bypass ordinary folder rules on Windows:
      * device namespaces (\\?\, \\.\) and UNC/network paths (\\server\share):
        opening one can send the user's Windows credentials to another machine;
      * reserved device names (CON, NUL, COM1, LPT1...) in any component;
      * alternate data streams (file.txt:hidden), i.e. a colon after the drive;
      * for writes, components ending in a dot or space, which Windows strips
        silently, so the file created is not the one that was validated.
    """
    text = str(raw).strip()
    if "\x00" in text:
        raise PermissionError("Acesso Negado: caminho com caractere nulo.")
    if text.startswith(("\\\\", "//", "\\/", "/\\")):
        raise PermissionError(
            "Acesso Negado: caminhos de rede (\\\\servidor\\pasta) e de dispositivo não são permitidos."
        )
    parts = [p for p in re.split(r"[\\/]+", text) if p]
    for index, part in enumerate(parts):
        if index == 0 and _DRIVE.match(part):
            continue
        if ":" in part:
            raise PermissionError(
                f"Acesso Negado: '{part}' usa um fluxo alternativo (':'), que não é permitido."
            )
        if part in (".", ".."):
            continue
        # Windows ignores the extension and spaces before it: "nul.txt", "aux .log".
        if _RESERVED_NAME.match(part.split(".", 1)[0].rstrip(" ")):
            raise PermissionError(
                f"Acesso Negado: '{part}' é um nome reservado de dispositivo do Windows."
            )
        if for_write and part[-1] in ". ":
            raise PermissionError(
                f"Acesso Negado: o nome '{part}' termina com ponto ou espaço, que o Windows descarta."
            )


def ensure_not_hardlinked(path: Path) -> None:
    """An existing file with more than one hard link shares its content with
    another path, possibly outside the authorized folders: never edit it."""
    try:
        links = os.stat(path).st_nlink if path.is_file() else 1
    except OSError:
        return
    if links > 1:
        raise PermissionError(
            f"Acesso Negado: '{path}' tem mais de um vínculo físico (hard link); "
            "editá-lo alteraria também outro caminho."
        )


def _system_dirs() -> List[Path]:
    r"""Windows system folders the assistant never writes to (C:\Windows, Program Files, AppData...)."""
    names = ("SystemRoot", "windir", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432",
             "ProgramData", "APPDATA", "LOCALAPPDATA")
    found = []
    for name in names:
        value = os.environ.get(name)
        if value:
            found.append(Path(value))
    if os.name == "nt":
        found += [Path("C:/Windows"), Path("C:/Program Files"), Path("C:/Program Files (x86)"),
                  Path("C:/ProgramData")]
    unique = []
    for path in found:
        try:
            resolved = path.expanduser().resolve()
        except Exception:
            continue
        if resolved not in unique:
            unique.append(resolved)
    return unique

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
        self.system_dirs = _system_dirs()
        # Temp files live under AppData\Local\Temp; they stay writable.
        self.temp_dir = Path(tempfile.gettempdir()).resolve()

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
        return self.is_system_path(resolved)

    def is_system_path(self, target: Path) -> bool:
        """True inside Windows, Program Files, ProgramData or AppData (temp excluded)."""
        if self._is_within(target, self.temp_dir):
            return False
        return any(self._is_within(target, d) for d in self.system_dirs)

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
        check_windows_path_syntax(str(target_path), for_write=for_write)

        resolved = Path(str(target_path)).expanduser().resolve()
        if not self.is_safe_path(str(resolved)):
            raise PermissionError(
                f"Acesso Negado: o caminho '{target_path}' não está na lista de diretórios autorizados."
            )
        if for_write and self.is_protected(str(resolved)):
            raise PermissionError(
                f"Acesso Negado: '{resolved}' é um caminho protegido (sistema do Windows ou código, banco e backups do aplicativo)."
            )
        if must_exist and not resolved.exists():
            raise FileNotFoundError(f"Arquivo ou diretório não encontrado: '{target_path}'")
        return resolved


path_guard = PathGuard()
