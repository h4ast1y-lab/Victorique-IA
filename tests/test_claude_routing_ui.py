"""O engine entrega turnos do modo claude-code ao backend do Claude Code; a UI troca de modo."""
from pathlib import Path

import pytest

from app.claude_code.backend import claude_code_backend
from app.core.assistant import assistant_engine
from app.memory.conversation_store import conversation_store

UI = Path(__file__).resolve().parent.parent / "app" / "ui"


@pytest.mark.asyncio
async def test_engine_routes_claude_code(monkeypatch):
    calls = []

    async def fake_run_turn(conversation_id, user_message, project_id, personality_id):
        calls.append((conversation_id, user_message, project_id, personality_id))
        yield 'data: {"type": "token", "content": "Oi"}\n\n'
        yield 'data: {"type": "done", "content": "Oi"}\n\n'

    monkeypatch.setattr(claude_code_backend, "run_turn", fake_run_turn)
    conv = conversation_store.create_conversation()["id"]
    chunks = [
        c async for c in assistant_engine.chat_stream(
            conversation_id=conv, user_message="olá", backend="claude-code", personality_id="victorique"
        )
    ]
    assert chunks == [
        'data: {"type": "token", "content": "Oi"}\n\n',
        'data: {"type": "done", "content": "Oi"}\n\n',
    ]
    assert calls == [(conv, "olá", None, "victorique")]
    users = [m for m in conversation_store.get_messages(conv) if m["role"] == "user"]
    assert [m["content"] for m in users] == ["olá"]


def test_ui_has_mode_selector_and_badge():
    html = (UI / "index.html").read_text(encoding="utf-8")
    js = (UI / "js" / "app.js").read_text(encoding="utf-8")
    assert 'id="modeSelect"' in html
    assert 'value="claude-code"' in html
    assert 'id="claudeBadge"' in html
    assert "default_backend" in js
