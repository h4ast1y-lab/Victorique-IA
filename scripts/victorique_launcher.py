"""
Victorique.exe: abre o app sem janela de console.

Este arquivo vira o executável (scripts/build_launcher.py). Ele não embute o
app: só roda ``run.py`` com o ``pythonw.exe`` do ``.venv`` do projeto, então o
.exe precisa ficar na pasta do projeto (ao lado de ``run.py``). Atualizar o
código não exige gerar o .exe de novo.

A saída do app vai para ``data/victorique.log``.
"""
import os
import subprocess
import sys
from pathlib import Path


def _project_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _find_pythonw(root: Path) -> Path | None:
    # A pasta do projeto ou uma acima (worktrees do git ficam dentro dele).
    for folder in (root, *root.parents):
        candidate = folder / ".venv" / "Scripts" / "pythonw.exe"
        if candidate.is_file():
            return candidate
    return None


def _error(message: str) -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "Victorique", 0x10)
    except Exception:
        print(message, file=sys.stderr)


def main() -> int:
    root = _project_dir()
    run_py = root / "run.py"
    pythonw = _find_pythonw(root)
    if not run_py.is_file():
        _error(f"Não achei run.py em:\n{root}\n\nDeixe o Victorique.exe na pasta do projeto.")
        return 1
    if pythonw is None:
        _error(f"Não achei .venv\\Scripts\\pythonw.exe em:\n{root}\n\nConsulte o README para preparar o ambiente.")
        return 1

    log_dir = root / "data"
    log_dir.mkdir(exist_ok=True)
    log = open(log_dir / "victorique.log", "a", encoding="utf-8")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    subprocess.Popen(
        [str(pythonw), str(run_py), *sys.argv[1:]],
        cwd=str(root),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
