"""
Installs the Victorique bridge into Spotify through Spicetify.

    .venv\\Scripts\\python.exe scripts\\install_spicetify.py [--no-apply]

Same as Configurações → Na área de trabalho → «Instalar a ponte do Spicetify».
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.spotify.bridge import bridge  # noqa: E402
from app.spotify.spicetify import SpicetifyError, install  # noqa: E402


def main() -> int:
    try:
        result = install(settings.port, bridge.token(), apply="--no-apply" not in sys.argv)
    except SpicetifyError as exc:
        print(f"Erro: {exc}")
        return 1
    print(result["message"])
    print(f"Arquivo: {result['path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
