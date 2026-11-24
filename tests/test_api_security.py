import json
import subprocess
from pathlib import Path

import pytest

from app.config import DATA_DIR, DB_PATH
from app.security.path_guard import path_guard


def _authorize_tmp_dir(tmp_path: Path) -> Path:
    path_guard.add_authorized_directory(str(tmp_path))
    return tmp_path


def test_client_supplied_authorized_flag_is_ignored(client, tmp_path):
    target = _authorize_tmp_dir(tmp_path) / "nunca-criado.txt"
    r = client.post(
        "/api/tools/execute",
        json={
            "tool_name": "write_file",
            "parameters": {"path": str(target), "content": "invasao"},
            "authorized": True,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "requires_authorization"
    assert "action_id" in data
    assert not target.exists(), "o flag authorized do cliente não pode executar a ação"


def test_authorization_is_single_use_and_replay_is_blocked(client, tmp_path):
    target = _authorize_tmp_dir(tmp_path) / "aprovado.txt"
    r = client.post(
        "/api/tools/execute",
        json={"tool_name": "write_file", "parameters": {"path": str(target), "content": "ok"}},
    )
    action_id = r.json()["action_id"]

    r = client.post("/api/security/authorize", json={"action_id": action_id, "approved": True})
    assert r.status_code == 200
    assert r.json()["status"] == "executed"
    assert target.read_text(encoding="utf-8") == "ok"

    replay = client.post("/api/security/authorize", json={"action_id": action_id, "approved": True})
    assert replay.status_code == 404


def test_expired_authorization_is_rejected(client, tmp_path):
    from app.security.permissions import security_manager

    target = _authorize_tmp_dir(tmp_path) / "expirado.txt"
    r = client.post(
        "/api/tools/execute",
        json={"tool_name": "write_file", "parameters": {"path": str(target), "content": "x"}},
    )
    action_id = r.json()["action_id"]
    security_manager.pending_actions[action_id]["expires_at"] = 0

    r = client.post("/api/security/authorize", json={"action_id": action_id, "approved": True})
    assert r.status_code == 404
    assert not target.exists()


def test_rejected_authorization_does_nothing(client, tmp_path):
    target = _authorize_tmp_dir(tmp_path) / "recusado.txt"
    r = client.post(
        "/api/tools/execute",
        json={"tool_name": "write_file", "parameters": {"path": str(target), "content": "x"}},
    )
    action_id = r.json()["action_id"]
    r = client.post("/api/security/authorize", json={"action_id": action_id, "approved": False})
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    assert not target.exists()


def test_protected_paths_cannot_be_written_or_deleted(client):
    for target in [DB_PATH, DATA_DIR / "qualquer.txt", Path(__file__).resolve()]:
        r = client.post(
            "/api/tools/execute",
            json={"tool_name": "write_file", "parameters": {"path": str(target), "content": "x"}},
        )
        action_id = r.json()["action_id"]
        r = client.post("/api/security/authorize", json={"action_id": action_id, "approved": True})
        payload = r.json()
        assert payload["status"] == "executed"
        assert payload["result"]["status"] == "error"
        assert "protegido" in payload["result"]["error"].lower()
    assert DB_PATH.exists()


def test_traversal_and_absolute_paths_are_blocked(client):
    for target in [
        str(DATA_DIR / ".." / ".." / "Windows" / "win.ini"),
        "C:\\Windows\\win.ini",
        "\\\\localhost\\C$\\Windows\\win.ini",
    ]:
        r = client.post(
            "/api/tools/execute",
            json={"tool_name": "read_file", "parameters": {"path": target}},
        )
        data = r.json()
        assert data["status"] == "error"
        assert "negado" in data["error"].lower()
        assert "content" not in data


def test_junction_escape_is_blocked(client, tmp_path):
    link = tmp_path / "junction-windows"
    if link.exists():
        pytest.skip("junction já existe")
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), r"C:\Windows"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        pytest.skip(f"não foi possível criar junction: {result.stderr or result.stdout}")

    assert path_guard.is_safe_path(str(link / "win.ini")) is False
    r = client.post(
        "/api/tools/execute",
        json={"tool_name": "read_file", "parameters": {"path": str(link / "win.ini")}},
    )
    data = r.json()
    assert data["status"] == "error"
    assert "negado" in data["error"].lower()


def test_cross_site_origin_and_host_are_rejected(client):
    r = client.post(
        "/api/tools/execute",
        json={"tool_name": "calculate", "parameters": {"expression": "1+1"}},
        headers={"origin": "http://evil.example"},
    )
    assert r.status_code == 403

    r = client.get("/api/health", headers={"host": "evil.example"})
    assert r.status_code == 400


def test_web_search_never_runs_without_approval(client, monkeypatch):
    calls = {"count": 0}

    class Boom:
        def __init__(self, *args, **kwargs):
            calls["count"] += 1
            raise AssertionError("nenhuma conexão externa deveria ocorrer")

    monkeypatch.setattr("app.tools.web_search.httpx.AsyncClient", Boom)

    r = client.post(
        "/api/tools/execute",
        json={"tool_name": "search_web", "parameters": {"query": "teste"}},
    )
    assert r.json()["status"] == "requires_authorization"
    assert calls["count"] == 0


def test_calculator_limits(client):
    r = client.post(
        "/api/tools/execute",
        json={"tool_name": "calculate", "parameters": {"expression": "9 ** 100000"}},
    )
    data = r.json()
    assert data["status"] == "success"
    assert data["result"]["status"] == "error"
