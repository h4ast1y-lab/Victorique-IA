"""Escolha de modo persistida e sessão do Claude Code por conversa."""
import pytest

from app.memory.conversation_store import conversation_store

ALL_BACKENDS = {"llama-cpp", "llama-cpp-server", "ollama", "claude-code"}


@pytest.fixture
def restore_backend(client):
    before = client.get("/api/settings").json()["default_backend"]
    yield
    client.post("/api/settings", json={"default_backend": before})


def test_backend_choice_is_persisted(client, restore_backend):
    assert client.post("/api/settings", json={"default_backend": "claude-code"}).status_code == 200
    body = client.get("/api/settings").json()
    assert body["default_backend"] == "claude-code"
    assert ALL_BACKENDS <= set(body["available_backends"])


def test_invalid_backend_rejected(client):
    assert client.post("/api/settings", json={"default_backend": "gpt"}).status_code == 400


def test_chat_uses_persisted_backend(client, restore_backend, monkeypatch):
    seen = {}

    async def fake_chat_stream(**kwargs):
        seen.update(kwargs)
        yield 'data: {"type": "done"}\n\n'

    monkeypatch.setattr("app.main.assistant_engine.chat_stream", fake_chat_stream)
    client.post("/api/settings", json={"default_backend": "claude-code"})
    with client.stream("POST", "/api/chat", json={"message": "oi"}) as response:
        response.read()
    assert seen["backend"] == "claude-code"


def test_claude_session_roundtrip():
    conv = conversation_store.create_conversation(title="Sessão")
    assert conversation_store.get_claude_session(conv["id"]) is None
    conversation_store.set_claude_session(conv["id"], "s1")
    assert conversation_store.get_claude_session(conv["id"]) == "s1"
    conversation_store.set_claude_session(conv["id"], None)
    assert conversation_store.get_claude_session(conv["id"]) is None
    conversation_store.delete_conversation(conv["id"])


def test_claude_status_endpoint(client):
    body = client.get("/api/claude-code/status").json()
    assert set(body) == {"sdk_installed", "cli_path", "workspace", "model", "last_error"}
    assert body["sdk_installed"] is True
