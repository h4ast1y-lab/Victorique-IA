"""Ponte entre o callback de permissão do Claude Code e a barra de autorização."""
import asyncio

import pytest
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

from app.claude_code.permissions import PermissionBridge, describe_target
from app.config import BASE_DIR
from app.memory.database import get_connection
from app.security.permissions import security_manager


async def _ask(bridge, tool, data):
    task = asyncio.create_task(bridge.can_use_tool(tool, data, None))
    for _ in range(50):
        await asyncio.sleep(0.01)
        if bridge.emitted:
            break
    return task


class Recorder(PermissionBridge):
    def __init__(self, **kwargs):
        self.emitted = []
        super().__init__(emit=self.emitted.append, conversation_id="c1", **kwargs)


@pytest.mark.asyncio
async def test_approval_allows(tmp_path):
    bridge = Recorder()
    target = str(tmp_path / "a.txt")
    task = await _ask(bridge, "Write", {"file_path": target, "content": "x"})
    event = bridge.emitted[0]
    assert event["type"] == "authorization_required"
    assert event["tool_name"] == "Write"
    assert event["resource"] == target
    security_manager.resolve_action_detailed(event["action_id"], True)
    result = await task
    assert isinstance(result, PermissionResultAllow)


@pytest.mark.asyncio
async def test_rejection_denies(tmp_path):
    bridge = Recorder()
    task = await _ask(bridge, "Bash", {"command": "dir"})
    security_manager.resolve_action_detailed(bridge.emitted[0]["action_id"], False)
    result = await task
    assert isinstance(result, PermissionResultDeny)
    assert result.message


@pytest.mark.asyncio
async def test_timeout_denies():
    bridge = Recorder(ttl=0.2)
    result = await bridge.can_use_tool("Bash", {"command": "dir"}, None)
    assert isinstance(result, PermissionResultDeny)
    pending_ids = {a["id"] for a in security_manager.list_pending_actions()}
    assert bridge.emitted[0]["action_id"] not in pending_ids


@pytest.mark.asyncio
async def test_protected_path_denied_without_asking():
    bridge = Recorder()
    result = await bridge.can_use_tool(
        "Edit", {"file_path": str(BASE_DIR / "app" / "main.py")}, None
    )
    assert isinstance(result, PermissionResultDeny)
    assert bridge.emitted == []


@pytest.mark.asyncio
async def test_cancel_pending_denies():
    bridge = Recorder()
    task = await _ask(bridge, "Bash", {"command": "dir"})
    bridge.cancel_pending()
    result = await task
    assert isinstance(result, PermissionResultDeny)


def test_describe_target():
    assert describe_target("Write", {"file_path": "C:/x.txt"}) == "C:/x.txt"
    assert describe_target("Bash", {"command": "dir"}) == "dir"
    assert describe_target("WebFetch", {"url": "https://a.b"}) == "https://a.b"
    assert len(describe_target("Outro", {"k": "v" * 500})) <= 200


def test_authorize_endpoint_does_not_run_registry_for_claude(client, monkeypatch):
    async def must_not_run(action):
        raise AssertionError("registry must not run Claude Code actions")

    monkeypatch.setattr("app.main.tool_registry.execute_approved_action", must_not_run)

    async def create():
        return security_manager.create_waiting_request(
            action_type="Write", resource="C:/x.txt", description="teste", payload={}
        )

    action_id, _future = asyncio.run(create())
    response = client.post("/api/security/authorize", json={"action_id": action_id, "approved": True})
    assert response.json() == {"status": "approved"}


@pytest.mark.asyncio
async def test_decisions_are_audited(tmp_path):
    bridge = Recorder()
    task = await _ask(bridge, "Write", {"file_path": str(tmp_path / "audit.txt")})
    security_manager.resolve_action_detailed(bridge.emitted[0]["action_id"], True)
    await task
    with get_connection() as conn:
        row = conn.execute(
            "SELECT authorized FROM audit_logs WHERE action_type = 'Write' AND resource = ? "
            "ORDER BY id DESC LIMIT 1",
            (str(tmp_path / "audit.txt"),),
        ).fetchone()
    assert row["authorized"] == 1


@pytest.mark.asyncio
async def test_turbo_auto_approves_writes_but_not_protected(tmp_path, monkeypatch):
    """Turbo = acceptEdits semantics, but the protected-path guard still applies."""
    from app.config import settings
    monkeypatch.setattr(settings, "turbo_mode", True)
    bridge = Recorder()
    result = await bridge.can_use_tool("Write", {"file_path": str(tmp_path / "t.txt")}, None)
    assert isinstance(result, PermissionResultAllow)
    assert bridge.emitted == []
    protected = await bridge.can_use_tool(
        "Write", {"file_path": str(BASE_DIR / "app" / "main.py")}, None
    )
    assert isinstance(protected, PermissionResultDeny)
    # Commands still ask, like acceptEdits.
    task = await _ask(bridge, "Bash", {"command": "dir"})
    assert bridge.emitted and bridge.emitted[0]["tool_name"] == "Bash"
    bridge.cancel_pending()
    await task
