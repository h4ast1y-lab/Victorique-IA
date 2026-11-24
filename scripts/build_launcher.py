"""
Gera ``Victorique.exe`` (launcher com o ícone da Victorique) na pasta do projeto.

Uso, na pasta do projeto:
    .venv\Scripts\python.exe -m pip install pyinstaller
    .venv\Scripts\python.exe scripts\build_launcher.py

O .exe só chama ``run.py`` com o Python do ``.venv`` (veja
scripts/victorique_launcher.py), então fica pequeno e não precisa ser gerado
de novo quando o código muda. O ícone sai da foto padrão
(app/ui/img/victorique-avatar.webp).
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller não está instalado. Rode:")
        print(r"  .venv\Scripts\python.exe -m pip install pyinstaller")
        return 1

    from app.core import avatar_photo

    icon = avatar_photo.make_ico(avatar_photo.DEFAULT_PATH, avatar_photo.DEFAULT_ICO)
    print(f"[OK] Ícone: {icon}")

    with tempfile.TemporaryDirectory(prefix="victorique-build-") as tmp:
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--onefile", "--noconsole", "--clean", "--noconfirm",
            "--name", "Victorique",
            "--icon", str(icon),
            "--distpath", str(ROOT),
            "--workpath", str(Path(tmp) / "build"),
            "--specpath", tmp,
            str(ROOT / "scripts" / "victorique_launcher.py"),
        ]
        result = subprocess.run(cmd, cwd=tmp)
        if result.returncode != 0:
            print("Falha ao gerar o executável.")
            return result.returncode
    exe = ROOT / "Victorique.exe"
    print(f"[OK] Gerado: {exe}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
