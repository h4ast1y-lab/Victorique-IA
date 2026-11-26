"""
Sem console (pythonw.exe), sys.stdout e sys.stderr são None. O run.py precisa
dar um destino a eles antes de subir o uvicorn, senão a thread do servidor
morre calada e a janela fica esperando o backend para sempre.
"""
import sys

import httpx
import pytest
from uvicorn.logging import DefaultFormatter

import run


def test_without_a_console_the_backend_logger_still_starts(monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    run.configure_console()

    assert sys.stdout is not None and sys.stderr is not None
    print("Iniciando Victorique (Desktop)")   # não pode quebrar
    DefaultFormatter(fmt="%(levelprefix)s %(message)s")   # chama sys.stdout.isatty()


def test_a_real_console_is_left_alone(monkeypatch):
    before = sys.stdout
    run.configure_console()
    assert sys.stdout is before


@pytest.mark.parametrize("replacement", [set(), {"222"}], ids=["serve", "tray-respawn"])
def test_restart_ollama_waits_for_new_listener(monkeypatch, replacement):
    from app.models import windows_ports

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:14123")
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.setattr(run, "ollama_executable", lambda: "ollama.exe")
    snapshots = iter([{"111"}, {"111"}, replacement])
    calls = []

    def listeners(port, host):
        assert (port, host) == (14123, "127.0.0.1")
        return next(snapshots)

    def spawn(args, **kwargs):
        assert args == ["ollama.exe", "serve"]
        assert kwargs["env"]["OLLAMA_HOST"] == "127.0.0.1:14123"
        calls.append("serve")

    def version(client, url):
        assert url == "http://127.0.0.1:14123/api/version"
        calls.append("ready")
        return httpx.Response(200, json={"version": "test"})

    monkeypatch.setattr(windows_ports, "listening_pids", listeners)
    monkeypatch.setattr(windows_ports, "stop_server_process",
                        lambda pid, name, tree: calls.append((pid, name, tree)))
    monkeypatch.setattr(run.subprocess, "Popen", spawn)
    monkeypatch.setattr(httpx.Client, "get", version)
    monkeypatch.setattr(run.time, "sleep", lambda _: None)
    run.restart_local_ollama()
    assert calls == [("111", "ollama", True), *(["serve"] if not replacement else []), "ready"]
