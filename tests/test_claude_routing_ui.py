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


def test_auth_bar_shows_during_claude_turn():
    """Claude waits for approval mid-stream, so the bar must open while generating."""
    js = (UI / "js" / "app.js").read_text(encoding="utf-8")
    handler = js.split("data.type === 'authorization_required'", 1)[1].split("} else if", 1)[0]
    assert "checkPendingAuthorizations(true)" in handler
    assert "if (isGenerating && !force) return;" in js


def test_resolving_claude_request_adds_no_misleading_bubble():
    js = (UI / "js" / "app.js").read_text(encoding="utf-8")
    resolve = js.split("async function resolveAuth", 1)[1].split("\nfunction ", 1)[0]
    assert "kind === 'claude_code'" in resolve


def test_pending_list_exposes_kind():
    import asyncio
    from app.security.permissions import security_manager

    async def create():
        return security_manager.create_waiting_request(
            action_type="Write", resource="C:/k.txt", description="t", payload={}
        )

    action_id, _ = asyncio.run(create())
    item = next(a for a in security_manager.list_pending_actions() if a["id"] == action_id)
    assert item["kind"] == "claude_code"
    security_manager.cancel_action(action_id, "teste")
