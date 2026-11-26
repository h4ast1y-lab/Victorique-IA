"""
Installs the Spicetify bridge: writes victorique.js (with this app's port and
token) into Spicetify's Extensions folder, enables it and reapplies Spicetify
(Spotify restarts). Needs the Spicetify CLI (https://spicetify.app).

Also says how things stand (state): whether the CLI is there, the bridge is
installed and current (same port and token as this app), Spotify is the
Microsoft Store build (Spicetify may need reapplying after it closes or
updates) and Spicetify still points at a Spotify folder that no longer exists
(the Store build moves to a new folder on every update).
"""
from __future__ import annotations

import configparser
import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

EXTENSION = "victorique.js"
TEMPLATE = Path(__file__).with_name(EXTENSION)
TIMEOUT = 180
QUICK_TIMEOUT = 20
STORE_PACKAGE = "SpotifyAB.SpotifyMusic"
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_config_cache: Dict[str, Path] = {}
_lock = threading.Lock()


class SpicetifyError(RuntimeError):
    def __init__(self, message: str, output: str = ""):
        super().__init__(message)
        self.output = output          # everything the CLI printed, without colours


def needs_backup(output: str) -> bool:
    """`apply` refused because Spotify updated and is back to its stock files:
    Spicetify itself then says to run «spicetify backup apply»."""
    text = output.lower()
    return "backup apply" in text and ("stock state" in text or "mismatch" in text)


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


def plain(text: str) -> str:
    """Spicetify's output without its colour codes."""
    return _ANSI.sub("", text or "")


def _lines(text: str) -> List[str]:
    """Spicetify's output as lines (its spinners redraw with carriage returns)."""
    return [ln.strip() for ln in re.split(r"[\r\n]+", plain(text)) if ln.strip()]


def _run(runner: Runner, args: List[str], timeout: float = TIMEOUT, answer: Optional[str] = None) -> str:
    """Runs the CLI; `answer` is typed into its prompts ("y" to Spicetify's
    "continue anyway?" for the Microsoft Store build)."""
    kwargs: Dict[str, Any] = dict(capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=timeout)
    if answer is not None:
        kwargs["input"] = answer + "\n"
    else:
        kwargs["stdin"] = subprocess.DEVNULL     # a prompt gets "no", never hangs
    if os.name == "nt":
        # The app runs under pythonw: without this every call flashes a console.
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        done = runner(args, **kwargs)
    except subprocess.TimeoutExpired as exc:
        raise SpicetifyError(f"«spicetify {' '.join(args[1:])}» demorou demais e foi interrompido.") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise SpicetifyError(f"Falha ao rodar spicetify {' '.join(args[1:])}: {exc}") from exc
    out = plain(done.stdout or "")
    if done.returncode != 0:
        everything = f"{done.stdout or ''}\n{done.stderr or ''}"
        detail = " ".join(_lines(done.stderr or "")[-3:] or _lines(out)[-3:])
        raise SpicetifyError(f"«spicetify {' '.join(args[1:])}» falhou: {detail}", plain(everything))
    return out


def config_path(cli: str, runner: Runner = subprocess.run) -> Optional[Path]:
    """config-xpui.ini (`spicetify -c` prints it); the real CLI is asked once."""
    cache = runner is subprocess.run
    if cache:
        with _lock:
            cached = _config_cache.get(cli)
        if cached is not None:
            return cached
    try:
        lines = [ln.strip() for ln in _run(runner, [cli, "-c"], QUICK_TIMEOUT).splitlines() if ln.strip()]
    except SpicetifyError:
        return None
    config = Path(lines[-1]) if lines else None
    if config is None or config.suffix.lower() != ".ini":
        return None
    if cache:
        with _lock:
            _config_cache[cli] = config
    return config


def folder_for(config: Optional[Path]) -> Path:
    """Spicetify looks for extensions next to its config file first."""
    if config is not None:
        return config.parent / "Extensions"
    appdata = os.environ.get("APPDATA") or str(Path.home())
    return Path(appdata) / "spicetify" / "Extensions"


def extensions_dir(cli: str, runner: Runner = subprocess.run) -> Path:
    return folder_for(config_path(cli, runner))


def read_config(path: Optional[Path]) -> Dict[str, str]:
    """The few config-xpui.ini fields that matter here ({} when unreadable)."""
    if path is None:
        return {}
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read_string(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, configparser.Error):
        return {}
    out: Dict[str, str] = {}
    for section, key in (("Setting", "spotify_path"), ("AdditionalOptions", "extensions")):
        if parser.has_option(section, key):
            out[key] = parser.get(section, key).strip()
    return out


def listed(extensions: str) -> List[str]:
    return [e.strip() for e in (extensions or "").split("|") if e.strip()]


def store_spotify() -> bool:
    """Spotify from the Microsoft Store is installed (and the website build is not)."""
    local = os.environ.get("LOCALAPPDATA")
    appdata = os.environ.get("APPDATA")
    if appdata and (Path(appdata) / "Spotify" / "Spotify.exe").is_file():
        return False
    if not local:
        return False
    packages = Path(local) / "Packages"
    try:
        return any(packages.glob(f"{STORE_PACKAGE}_*"))
    except OSError:
        return False


def state(port: int, token: str, *, cli: Optional[str] = None,
          runner: Runner = subprocess.run) -> Dict[str, Any]:
    """How the bridge stands, for Settings. Never raises."""
    cli = cli or find_cli()
    out: Dict[str, Any] = {"spicetify": bool(cli), "installed": False, "current": False,
                           "store": store_spotify(), "stale_path": False}
    if not cli:
        return out
    try:
        config = config_path(cli, runner)
        fields = read_config(config)
        spotify_path = fields.get("spotify_path", "")
        out["stale_path"] = bool(spotify_path) and not Path(spotify_path).exists()
        out["store"] = out["store"] or STORE_PACKAGE.lower() in spotify_path.lower()
        target = folder_for(config) / EXTENSION
        on_disk = target.read_text(encoding="utf-8") if target.is_file() else None
        out["installed"] = on_disk is not None and EXTENSION in listed(fields.get("extensions", ""))
        out["current"] = out["installed"] and on_disk == render(port, token)
    except Exception:  # a broken config must not break Settings
        pass
    return out


def _hint(config: Optional[Path]) -> str:
    fields = read_config(config)
    spotify_path = fields.get("spotify_path", "")
    if spotify_path and not Path(spotify_path).exists():
        return (" O Spicetify ainda aponta para uma pasta do Spotify que não existe mais (o Spotify "
                "atualizou). Num terminal, rode «spicetify restore backup apply»; se ele reclamar do "
                "caminho, ajuste com «spicetify config spotify_path <pasta nova>».")
    return " Se for a primeira vez ou o Spotify acabou de atualizar, rode «spicetify backup apply» num terminal."


def install(port: int, token: str, *, apply: bool = True, runner: Runner = subprocess.run,
            cli: Optional[str] = None) -> Dict[str, Any]:
    cli = cli or find_cli()
    if not cli:
        raise SpicetifyError("Não achei o Spicetify. Instale-o (https://spicetify.app) e tente de novo.")
    config = config_path(cli, runner)
    folder = folder_for(config)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / EXTENSION
    target.write_text(render(port, token), encoding="utf-8")
    if EXTENSION not in listed(read_config(config).get("extensions", "")):
        _run(runner, [cli, "config", "extensions", EXTENSION], QUICK_TIMEOUT)
    rebacked = False
    if apply:
        try:
            _run(runner, [cli, "apply"])
        except SpicetifyError as exc:
            if not needs_backup(exc.output):
                raise SpicetifyError(f"{exc}{_hint(config)}") from exc
            # Spotify updated and is back to stock: what Spicetify asks for (and
            # what «spicetify auto» does). "y" answers its Microsoft Store warning.
            try:
                _run(runner, [cli, "backup", "apply"], answer="y")
            except SpicetifyError as again:
                raise SpicetifyError(f"{again}{_hint(config)}") from again
            rebacked = True
    message = "Ponte instalada. O Spotify reinicia e ela passa a ver abas e capas."
    if rebacked:
        message += " O Spotify tinha atualizado, então o Spicetify refez o backup dele antes."
    if store_spotify():
        message += (" Seu Spotify é o da Microsoft Store: aberto pelo menu Iniciar, ele vem sem a "
                    "ponte. Use «Reaplicar» (ou o comando «spicetify auto») para abri-lo com ela.")
    return {"ok": True, "path": str(target), "message": message, "rebacked": rebacked}


def uninstall(*, apply: bool = True, runner: Runner = subprocess.run,
              cli: Optional[str] = None) -> Dict[str, Any]:
    """Takes the bridge out of Spotify (Spotify restarts)."""
    cli = cli or find_cli()
    if not cli:
        raise SpicetifyError("Não achei o Spicetify, então não há ponte para remover.")
    config = config_path(cli, runner)
    target = folder_for(config) / EXTENSION
    if EXTENSION in listed(read_config(config).get("extensions", "")):
        _run(runner, [cli, "config", "extensions", f"{EXTENSION}-"], QUICK_TIMEOUT)
    try:
        target.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise SpicetifyError(f"Não consegui apagar {target}: {exc}") from exc
    if apply:
        try:
            _run(runner, [cli, "apply"])
        except SpicetifyError as exc:
            # A stock Spotify (it updated) has no bridge to take out anymore.
            if not needs_backup(exc.output):
                raise SpicetifyError(f"{exc}{_hint(config)}") from exc
    return {"ok": True, "message": "Ponte removida do Spotify."}
