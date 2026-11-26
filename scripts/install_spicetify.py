"""
Installs the Victorique bridge into Spotify through Spicetify.

    .venv\\Scripts\\python.exe scripts\\install_spicetify.py [--no-apply] [--remove]

Same as Configurações → Na área de trabalho → «Instalar a ponte do Spicetify»
(or «Remover a ponte» with --remove). --no-apply skips «spicetify apply», so
Spotify is not restarted (the change shows the next time Spicetify applies).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.spotify.bridge import bridge  # noqa: E402
from app.spotify.spicetify import SpicetifyError, install, uninstall  # noqa: E402


def main() -> int:
    apply = "--no-apply" not in sys.argv
    try:
        if "--remove" in sys.argv:
            result = uninstall(apply=apply)
        else:
            result = install(settings.port, bridge.token(), apply=apply)
    except SpicetifyError as exc:
        print(f"Erro: {exc}")
        return 1
    print(result["message"])
    if result.get("path"):
        print(f"Arquivo: {result['path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
