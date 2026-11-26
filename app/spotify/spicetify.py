"""
Installs the Spicetify bridge: writes victorique.js (with this app's port and
token) into Spicetify's Extensions folder, enables it and reapplies Spicetify
(Spotify restarts). Needs the Spicetify CLI (https://spicetify.app).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

EXTENSION = "victorique.js"
TEMPLATE = Path(__file__).with_name(EXTENSION)
TIMEOUT = 180


class SpicetifyError(RuntimeError):
    pass


def render(port: int, token: str) -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    return text.replace("__PORT__", str(int(port))).replace("__TOKEN__", json.dumps(token))


def find_cli() -> Optional[str]:
    found = shutil.which("spicetify")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA")
    if local:
        exe = Path(local) / "spicetify" / "spicetify.exe"
        if exe.is_file():
            return str(exe)
    return None


Runner = Callable[..., Any]


def _run(runner: Runner, args: List[str]) -> str:
    try:
        done = runner(args, capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        raise SpicetifyError(f"Falha ao rodar {' '.join(args[1:])}: {exc}") from exc
    if done.returncode != 0:
        detail = (done.stderr or done.stdout or "").strip().splitlines()[-3:]
        raise SpicetifyError(f"«spicetify {' '.join(args[1:])}» falhou: {' '.join(detail)}")
    return done.stdout or ""


def extensions_dir(cli: str, runner: Runner = subprocess.run) -> Path:
    """Spicetify keeps extensions next to its config file (`spicetify -c` prints it)."""
    try:
        lines = [ln.strip() for ln in _run(runner, [cli, "-c"]).splitlines() if ln.strip()]
        config = Path(lines[-1]) if lines else None
        if config and config.suffix.lower() == ".ini":
            return config.parent / "Extensions"
    except SpicetifyError:
        pass
    appdata = os.environ.get("APPDATA") or str(Path.home())
    return Path(appdata) / "spicetify" / "Extensions"


def install(port: int, token: str, *, apply: bool = True, runner: Runner = subprocess.run,
            cli: Optional[str] = None) -> Dict[str, Any]:
    cli = cli or find_cli()
    if not cli:
        raise SpicetifyError("Não achei o Spicetify. Instale-o (https://spicetify.app) e tente de novo.")
    folder = extensions_dir(cli, runner)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / EXTENSION
    target.write_text(render(port, token), encoding="utf-8")
    _run(runner, [cli, "config", "extensions", EXTENSION])
    if apply:
        try:
            _run(runner, [cli, "apply"])
        except SpicetifyError as exc:
            raise SpicetifyError(f"{exc} Se for a primeira vez, rode «spicetify backup apply».") from exc
    return {"ok": True, "path": str(target),
            "message": "Ponte instalada. O Spotify reinicia e ela passa a ver abas e capas."}
