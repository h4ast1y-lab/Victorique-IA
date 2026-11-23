"""
Ciclo de vida do llama-server: subir em segundo plano sem travar o app,
nunca abrir dois processos e gravar a saída num log para diagnóstico.
"""
import threading
import time

import pytest

from app.models import llama_cpp_server_client as mod
from app.models.llama_cpp_server_client import LlamaCppServerClient


class FakeProc:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.returncode = None

    def poll(self):
        return None

    def terminate(self):
        self.returncode = 0

    def wait(self, timeout=None):
        return 0


@pytest.fixture
def fake_server(tmp_path, monkeypatch):
    exe = tmp_path / "llama-server.exe"
    model = tmp_path / "model.gguf"
    exe.write_text("")
    model.write_text("")
    spawned = []
    ready_at = {"t": None}

    def fake_popen(*args, **kwargs):
        proc = FakeProc(*args, **kwargs)
        spawned.append(proc)
        ready_at["t"] = time.time() + 0.4
        return proc

    monkeypatch.setattr(mod.subprocess, "Popen", fake_popen)
    client = LlamaCppServerClient(
        server_exe=exe, model_path=model, log_path=tmp_path / "llama-server.log"
    )
    monkeypatch.setattr(
        client, "is_alive", lambda: ready_at["t"] is not None and time.time() >= ready_at["t"]
    )
    real_sleep = time.sleep
    monkeypatch.setattr(mod.time, "sleep", lambda s: real_sleep(min(s, 0.05)))
    return client, spawned


def test_start_in_background_returns_immediately_and_spawns_once(fake_server):
    client, spawned = fake_server
    t0 = time.time()
    client.start_in_background(wait_seconds=5)
    client.start_in_background(wait_seconds=5)
    assert time.time() - t0 < 0.2
    assert client.status()["starting"] is True

    # A concurrent blocking start waits for the background one instead of
    # spawning a second process.
    assert client.start(wait_seconds=5) is True
    assert len(spawned) == 1
    assert client.available is True
    assert client.status()["starting"] is False


def test_concurrent_blocking_starts_spawn_one_process(fake_server):
    client, spawned = fake_server
    results = []
    threads = [
        threading.Thread(target=lambda: results.append(client.start(wait_seconds=5)))
        for _ in range(3)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [True, True, True]
    assert len(spawned) == 1


def test_server_output_goes_to_a_log_file(fake_server, tmp_path):
    client, spawned = fake_server
    assert client.start(wait_seconds=5) is True
    stdout = spawned[0].kwargs["stdout"]
    assert getattr(stdout, "name", None) == str(tmp_path / "llama-server.log")
    assert client.status()["log_path"] == str(tmp_path / "llama-server.log")
    client.stop()


def test_health_reports_active_backend(client, monkeypatch):
    from app.config import settings
    from app.models.llama_cpp_server_client import llama_cpp_server
    from app.models.ollama_client import ollama_client

    async def offline():
        return False

    monkeypatch.setattr(ollama_client, "is_alive", offline)
    monkeypatch.setattr(llama_cpp_server, "_available", True)
    before = client.get("/api/settings").json()["default_backend"]
    client.post("/api/settings", json={"default_backend": "llama-cpp"})
    try:
        body = client.get("/api/health").json()
    finally:
        client.post("/api/settings", json={"default_backend": before})
    assert body["active_backend"] == "llama-cpp"
    assert body["status"] == "healthy"


def test_ping_answers_without_checking_backends(client, monkeypatch):
    """run.py waits on /api/ping; it must not depend on slow backend probes."""
    from app.models.ollama_client import ollama_client

    async def never_called():
        raise AssertionError("ping must not probe Ollama")

    monkeypatch.setattr(ollama_client, "is_alive", never_called)
    assert client.get("/api/ping").json() == {"status": "ok"}


def test_run_py_waits_on_ping():
    from pathlib import Path
    source = (Path(__file__).resolve().parent.parent / "run.py").read_text(encoding="utf-8")
    assert "/api/ping" in source
