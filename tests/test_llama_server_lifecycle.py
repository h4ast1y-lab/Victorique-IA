"""
Ciclo de vida do llama-server: subir em segundo plano sem travar o app,
nunca abrir dois processos, gravar a saída num log para diagnóstico e,
a cada vez que a IA local é ligada, trocar um servidor antigo por um novo.
"""
import os
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
    # Never touch real processes on the machine running the tests.
    monkeypatch.setattr(client, "_kill_orphan_on_port", lambda: False)
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
    from app.models.llama_cpp_server_client import llama_cpp_server
    from app.models.ollama_client import ollama_client

    async def offline():
        return False

    monkeypatch.setattr(ollama_client, "is_alive", offline)
    monkeypatch.setattr(llama_cpp_server, "_available", True)
    # Switching modes turns the local server on/off; nothing real here.
    monkeypatch.setattr(llama_cpp_server, "start_in_background", lambda **kw: None)
    monkeypatch.setattr(llama_cpp_server, "stop", lambda: None)
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


def test_set_n_ctx_restarts_running_server(fake_server, monkeypatch):
    client, spawned = fake_server
    orig_is_alive = client.is_alive
    monkeypatch.setattr(client, "is_alive", lambda: client._proc is not None and orig_is_alive())
    assert client.start(wait_seconds=5) is True
    assert len(spawned) == 1
    assert "--ctx-size" in client.build_args()
    idx = client.build_args().index("--ctx-size")
    assert client.build_args()[idx + 1] == str(client.n_ctx)

    # Same value does not restart
    assert client.set_n_ctx(client.n_ctx) is False
    assert len(spawned) == 1

    # New value stops and restarts in background with the new --ctx-size
    assert client.set_n_ctx(16384) is True
    assert client.n_ctx == 16384
    assert client.start(wait_seconds=5) is True
    assert len(spawned) == 2
    idx2 = client.build_args().index("--ctx-size")
    assert client.build_args()[idx2 + 1] == "16384"
    client.stop()


def test_start_always_replaces_a_leftover_server(fake_server, monkeypatch):
    """A server left on the port by an earlier run is never reused, even with
    the same settings: it may still be busy with old requests."""
    client, spawned = fake_server
    orphan_alive = {"v": True}
    monkeypatch.setattr(client, "is_alive", lambda: orphan_alive["v"] or client._proc is not None)

    def fake_kill_orphan():
        orphan_alive["v"] = False
        return True

    monkeypatch.setattr(client, "_kill_orphan_on_port", fake_kill_orphan)

    assert client.start(wait_seconds=5) is True
    assert orphan_alive["v"] is False
    assert len(spawned) == 1
    client.stop()


def test_leftover_that_cannot_be_closed_is_used_instead_of_failing(fake_server, monkeypatch):
    client, spawned = fake_server
    monkeypatch.setattr(client, "is_alive", lambda: True)  # someone answers on the port
    monkeypatch.setattr(client, "_kill_orphan_on_port", lambda: False)
    assert client.start(wait_seconds=5) is True
    assert client.available is True
    assert spawned == []


def test_leftover_is_kept_when_no_new_server_can_be_started(fake_server, monkeypatch):
    """Without the exe (or the model) there is nothing to replace it with."""
    client, spawned = fake_server
    client.server_exe.unlink()
    kills = []
    monkeypatch.setattr(client, "is_alive", lambda: True)
    monkeypatch.setattr(client, "_kill_orphan_on_port", lambda: kills.append(1) or True)
    assert client.start(wait_seconds=5) is True
    assert kills == []
    assert spawned == []


def test_own_server_that_died_is_started_again(fake_server, monkeypatch):
    client, spawned = fake_server
    orig_is_alive = client.is_alive
    # Only a running process answers on the port.
    monkeypatch.setattr(client, "is_alive", lambda: (
        client._proc is not None and client._proc.poll() is None and orig_is_alive()))
    assert client.start(wait_seconds=5) is True
    spawned[0].poll = lambda: 1  # crashed after loading
    client._available = False
    assert client.start(wait_seconds=5) is True
    assert len(spawned) == 2
    client.stop()


def test_own_running_server_is_reused(fake_server):
    client, spawned = fake_server
    assert client.start(wait_seconds=5) is True
    assert client.start(wait_seconds=5) is True
    assert len(spawned) == 1
    client.stop()


def test_stop_while_loading_cancels_the_start(fake_server, monkeypatch):
    client, spawned = fake_server
    monkeypatch.setattr(client, "is_alive", lambda: False)  # model still loading
    results = []
    thread = threading.Thread(target=lambda: results.append(client.start(wait_seconds=5)))
    thread.start()
    for _ in range(100):
        if client._proc is not None:
            break
        time.sleep(0.01)
    assert len(spawned) == 1
    client.stop()
    thread.join(timeout=5)
    assert results == [False]
    assert client.available is False
    assert client._init_error is None  # a deliberate stop is not a crash
    assert client.status()["starting"] is False


# --- Closing the leftover server (netstat / tasklist / taskkill) ---------------

windows_only = pytest.mark.skipif(os.name != "nt", reason="usa netstat/tasklist/taskkill")


class FakeWindowsTools:
    """Answers netstat/tasklist/taskkill like Windows does."""

    def __init__(self, port, listeners, names, frees_port=True):
        self.port = port
        self.listeners = dict(listeners)  # pid -> netstat line
        self.names = names  # pid -> image name
        self.frees_port = frees_port
        self.killed = []

    def run(self, args, **kwargs):
        from types import SimpleNamespace
        if args[0] == "netstat":
            return SimpleNamespace(stdout="\n".join(self.listeners.values()))
        if args[0] == "tasklist":
            pid = args[2].split()[-1]
            name = self.names.get(pid)
            return SimpleNamespace(stdout=f'"{name}","{pid}","Console","1","5.000 K"' if name else "")
        if args[0] == "taskkill":
            pid = args[2]
            self.killed.append(pid)
            if self.frees_port:
                self.listeners.pop(pid, None)
            return SimpleNamespace(stdout="")
        raise AssertionError(args)


@windows_only
def test_kill_orphan_closes_only_llama_server_on_our_port(tmp_path, monkeypatch):
    client = LlamaCppServerClient(server_exe=tmp_path / "llama-server.exe",
                                  model_path=tmp_path / "m.gguf", port=8899)
    tools = FakeWindowsTools(
        8899,
        {
            # State word translated (pt-BR "OUVINDO"): recognised by the remote ":0".
            "111": "  TCP    127.0.0.1:8899         0.0.0.0:0              OUVINDO         111",
            "222": "  TCP    0.0.0.0:18899          0.0.0.0:0              LISTENING       222",
            "333": "  TCP    [::]:8899              [::]:0                 LISTENING       333",
            "444": "  TCP    127.0.0.1:8899         127.0.0.1:50123        ESTABLISHED     444",
            "555": "  UDP    0.0.0.0:8899           *:*                                    555",
        },
        {"111": "llama-server.exe", "222": "llama-server.exe", "333": "outro.exe",
         "444": "llama-server.exe", "555": "llama-server.exe"},
    )
    monkeypatch.setattr(mod.subprocess, "run", tools.run)
    assert client._kill_orphan_on_port() is True
    assert tools.killed == ["111"]


@windows_only
def test_kill_orphan_reports_a_port_that_stays_busy(tmp_path, monkeypatch):
    client = LlamaCppServerClient(server_exe=tmp_path / "llama-server.exe",
                                  model_path=tmp_path / "m.gguf", port=8899)
    tools = FakeWindowsTools(
        8899,
        {"111": "  TCP    127.0.0.1:8899   0.0.0.0:0   LISTENING   111"},
        {"111": "llama-server.exe"},
        frees_port=False,
    )
    monkeypatch.setattr(mod.subprocess, "run", tools.run)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    assert client._kill_orphan_on_port() is False
    assert tools.killed == ["111"]


@windows_only
def test_kill_orphan_with_nothing_on_the_port(tmp_path, monkeypatch):
    client = LlamaCppServerClient(server_exe=tmp_path / "llama-server.exe",
                                  model_path=tmp_path / "m.gguf", port=8899)
    tools = FakeWindowsTools(8899, {}, {})
    monkeypatch.setattr(mod.subprocess, "run", tools.run)
    assert client._kill_orphan_on_port() is False
    assert tools.killed == []


# --- A real leftover process ---------------------------------------------------

FAKE_SERVER = '''
import json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"data": [{"id": "fake", "pid": os.getpid()}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class Server(HTTPServer):
    allow_reuse_address = False  # binding fails while the old one listens


Server(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
'''


class ScriptServer(LlamaCppServerClient):
    """Runs a tiny HTTP server (``model_path``) in place of llama-server."""

    def build_args(self):
        return [str(self.server_exe), "-I", str(self.model_path), str(self.port)]


def _free_port():
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@windows_only
def test_turning_on_replaces_a_real_leftover_server(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    import httpx

    # The base interpreter: the venv's python.exe is a launcher whose child
    # would be the process actually listening.
    python = Path(getattr(sys, "_base_executable", sys.executable))
    script = tmp_path / "fake_llama_server.py"
    script.write_text(FAKE_SERVER, encoding="utf-8")
    port = _free_port()
    leftover = subprocess.Popen(
        [str(python), "-I", str(script), str(port)],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    client = ScriptServer(server_exe=python, model_path=script, port=port)
    url = f"http://127.0.0.1:{port}/v1/models"
    try:
        for _ in range(100):
            if client.is_alive():
                break
            time.sleep(0.1)
        assert httpx.get(url).json()["data"][0]["pid"] == leftover.pid

        assert client.start(wait_seconds=20) is True

        answering = httpx.get(url).json()["data"][0]["pid"]
        assert answering == client._proc.pid
        assert answering != leftover.pid
        assert leftover.wait(timeout=5) is not None  # the old one was closed
    finally:
        client.stop()
        if leftover.poll() is None:
            leftover.kill()
    assert client.is_alive() is False


# --- Switching modes turns the local server off and on ------------------------

def test_mode_switch_turns_local_server_on_and_off(client, monkeypatch):
    from app.config import settings
    from app.models.llama_cpp_server_client import llama_cpp_server

    calls = []
    monkeypatch.setattr(settings, "llama_cpp_auto_start", True)
    monkeypatch.setattr(llama_cpp_server, "start_in_background",
                        lambda **kw: calls.append("start"))
    monkeypatch.setattr(llama_cpp_server, "stop", lambda: calls.append("stop"))

    before = client.get("/api/settings").json()["default_backend"]
    try:
        client.post("/api/settings", json={"default_backend": "claude-code"})
        calls.clear()

        client.post("/api/settings", json={"default_backend": "llama-cpp-server"})
        assert calls == ["start"]  # entering local mode: a fresh server
        client.post("/api/settings", json={"default_backend": "llama-cpp"})
        assert calls == ["start"]  # still local: left alone
        client.post("/api/settings", json={"default_backend": "claude-code"})
        assert calls == ["start", "stop"]  # leaving: turned off
        client.post("/api/settings", json={"default_backend": "claude-code"})
        assert calls == ["start", "stop"]

        monkeypatch.setattr(settings, "llama_cpp_auto_start", False)
        client.post("/api/settings", json={"default_backend": "llama-cpp-server"})
        assert calls == ["start", "stop"]  # auto-start off: the first message starts it
    finally:
        client.post("/api/settings", json={"default_backend": before})
