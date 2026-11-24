"""Turno do modo Claude Code com um cliente falso do SDK (sem rede, sem cota)."""
import asyncio
import json

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ResultError,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from app.claude_code import backend as backend_mod
from app.claude_code.backend import ClaudeCodeBackend
from app.claude_code.victorique_tools import VICTORIQUE_TOOL_NAMES
from app.config import settings
from app.core.assistant import CANCELLED_MARKER
from app.memory.conversation_store import conversation_store

WAIT = object()  # the fake stream blocks here until interrupt()


def delta(kind, text):
    key = "text" if kind == "text_delta" else "thinking"
    return StreamEvent(
        uuid="u", session_id="s",
        event={"type": "content_block_delta", "index": 0, "delta": {"type": kind, key: text}},
    )


def result(session="s1", is_error=False, text=None):
    return ResultMessage(
        subtype="error_during_execution" if is_error else "success",
        duration_ms=1, duration_api_ms=1, is_error=is_error, num_turns=1,
        session_id=session, result=text,
    )


class FakeClient:
    def __init__(self, options, script, log):
        self.options = options
        self.script = script
        self.log = log
        self.released = asyncio.Event()

    async def connect(self, prompt=None):
        self.log.append("connect")

    async def query(self, prompt, session_id="default"):
        self.log.append(("query", prompt))

    async def receive_response(self):
        for item in self.script:
            if isinstance(item, Exception):
                raise item
            if item is WAIT:
                await self.released.wait()
                yield result("s-int")
                return
            yield item

    async def interrupt(self):
        self.log.append("interrupt")
        self.released.set()

    async def disconnect(self):
        self.log.append("disconnect")


class Harness:
    def __init__(self, *scripts, fail_on_resume=False):
        self.scripts = list(scripts)
        self.options = []
        self.log = []
        self.fail_on_resume = fail_on_resume

    def factory(self, options):
        self.options.append(options)
        if self.fail_on_resume and options.resume:
            raise ResultError("No conversation found with session ID")
        return FakeClient(options, self.scripts.pop(0), self.log)


def _conv():
    return conversation_store.create_conversation()["id"]


async def collect(gen):
    return [json.loads(chunk[len("data: "):]) async for chunk in gen]


def _assistant_messages(conv_id):
    return [m for m in conversation_store.get_messages(conv_id) if m["role"] == "assistant"]


@pytest.mark.asyncio
async def test_text_and_reasoning_deltas_map_to_events():
    h = Harness([
        delta("thinking_delta", "hmm"),
        delta("text_delta", "Olá"),
        AssistantMessage(content=[TextBlock(text="Olá")], model="m"),
        result(),
    ])
    conv = _conv()
    events = await collect(ClaudeCodeBackend(h.factory).run_turn(conv, "oi", None, None))
    tokens = [e["content"] for e in events if e["type"] == "token"]
    assert tokens == ["Olá"]
    assert [e["content"] for e in events if e["type"] == "reasoning"] == ["hmm"]
    done = events[-1]
    assert done["type"] == "done" and done["content"] == "Olá"
    assert ("query", "oi") in h.log and "disconnect" in h.log


@pytest.mark.asyncio
async def test_text_block_used_when_no_deltas_arrive():
    h = Harness([AssistantMessage(content=[TextBlock(text="Sem deltas")], model="m"), result()])
    events = await collect(ClaudeCodeBackend(h.factory).run_turn(_conv(), "oi", None, None))
    assert events[-1]["content"] == "Sem deltas"


@pytest.mark.asyncio
async def test_tool_use_and_result_events_and_trace():
    h = Harness([
        AssistantMessage(
            content=[ToolUseBlock(id="t1", name="Read", input={"file_path": "x"})], model="m"
        ),
        UserMessage(content=[ToolResultBlock(tool_use_id="t1", content="abc", is_error=False)]),
        delta("text_delta", "Li."),
        result(),
    ])
    conv = _conv()
    events = await collect(ClaudeCodeBackend(h.factory).run_turn(conv, "leia", None, None))
    call = next(e for e in events if e["type"] == "tool_call")
    assert call["tool"] == "Read" and call["arguments"] == {"file_path": "x"}
    res = next(e for e in events if e["type"] == "tool_result")
    assert res["tool"] == "Read" and res["status"] == "success"
    saved = _assistant_messages(conv)[-1]
    assert saved["tool_trace"][0]["tool"] == "Read"
    assert saved["tool_trace"][0]["status"] == "success"


@pytest.mark.asyncio
async def test_session_id_saved_and_resumed():
    h = Harness([delta("text_delta", "1"), result("s1")], [delta("text_delta", "2"), result("s1")])
    backend = ClaudeCodeBackend(h.factory)
    conv = _conv()
    await collect(backend.run_turn(conv, "a", None, None))
    assert conversation_store.get_claude_session(conv) == "s1"
    assert h.options[0].resume is None
    await collect(backend.run_turn(conv, "b", None, None))
    assert h.options[1].resume == "s1"


@pytest.mark.asyncio
async def test_resume_failure_starts_new_session():
    h = Harness([delta("text_delta", "novo"), result("s-new")], fail_on_resume=True)
    conv = _conv()
    conversation_store.set_claude_session(conv, "s-old")
    events = await collect(ClaudeCodeBackend(h.factory).run_turn(conv, "oi", None, None))
    assert [o.resume for o in h.options] == ["s-old", None]
    assert any(e["type"] == "notice" for e in events)
    assert events[-1]["content"] == "novo"
    assert conversation_store.get_claude_session(conv) == "s-new"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["result_message", "raised"])
async def test_missing_login_or_sdk_gives_clear_error(failure):
    text = "Invalid API key · Please run /login"
    script = (
        [result(is_error=True, text=text)] if failure == "result_message"
        else [ResultError(text)]
    )
    backend = ClaudeCodeBackend(Harness(script).factory)
    events = await collect(backend.run_turn(_conv(), "oi", None, None))
    error = next(e for e in events if e["type"] == "error")
    assert "login" in error["message"]
    assert "Claude Code" in error["message"]
    assert backend.last_error
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_cancel_interrupts_and_saves_partial(monkeypatch):
    cancelled = []

    class SpyBridge(backend_mod.PermissionBridge):
        def cancel_pending(self):
            cancelled.append(True)
            super().cancel_pending()

    monkeypatch.setattr(backend_mod, "PermissionBridge", SpyBridge)
    h = Harness([delta("text_delta", "Parcial"), WAIT])
    conv = _conv()
    gen = ClaudeCodeBackend(h.factory).run_turn(conv, "oi", None, None)
    async for chunk in gen:
        if json.loads(chunk[len("data: "):])["type"] == "token":
            break
    await gen.aclose()
    for _ in range(50):
        if "disconnect" in h.log:
            break
        await asyncio.sleep(0.02)
    assert "interrupt" in h.log
    assert "disconnect" in h.log
    assert cancelled == [True]
    saved = _assistant_messages(conv)[-1]["content"]
    assert saved.startswith("Parcial") and saved.endswith(CANCELLED_MARKER)


@pytest.mark.asyncio
async def test_options_are_locked_down():
    h = Harness([result()])
    await collect(ClaudeCodeBackend(h.factory).run_turn(_conv(), "oi", None, None))
    opts = h.options[0]
    assert opts.setting_sources == []
    assert opts.include_partial_messages is True
    assert opts.permission_mode == "default"
    assert opts.system_prompt["preset"] == "claude_code"
    assert "Victorique" in opts.system_prompt["append"]
    assert set(VICTORIQUE_TOOL_NAMES) <= set(opts.allowed_tools)
    assert "victorique" in opts.mcp_servers
    assert opts.can_use_tool is not None


@pytest.mark.asyncio
async def test_turbo_keeps_default_permission_mode(monkeypatch):
    """Turbo is applied by the permission bridge; acceptEdits would skip its guard."""
    monkeypatch.setattr(settings, "turbo_mode", True)
    h = Harness([result()])
    await collect(ClaudeCodeBackend(h.factory).run_turn(_conv(), "oi", None, None))
    assert h.options[0].permission_mode == "default"


def test_add_dirs_exclude_protected_paths():
    from app.claude_code.options import build_options
    from app.config import BASE_DIR, DATA_DIR

    class B:
        async def can_use_tool(self, *a):
            return None

    opts = build_options(append_prompt="x", resume=None, bridge=B(), project_id=None)
    dirs = {str(d) for d in opts.add_dirs}
    assert str(BASE_DIR.resolve()) not in dirs
    assert str(DATA_DIR.resolve()) not in dirs


def block_start(kind="text"):
    return StreamEvent(
        uuid="u", session_id="s",
        event={"type": "content_block_start", "index": 0, "content_block": {"type": kind}},
    )


@pytest.mark.asyncio
async def test_text_blocks_after_a_tool_are_separated():
    """Live run showed 'Vou criá-lo agora.Pronto.' when text resumed after a tool."""
    h = Harness([
        block_start(), delta("text_delta", "Vou criar."),
        AssistantMessage(content=[TextBlock(text="Vou criar.")], model="m"),
        AssistantMessage(content=[ToolUseBlock(id="t1", name="Write", input={})], model="m"),
        UserMessage(content=[ToolResultBlock(tool_use_id="t1", content="ok", is_error=False)]),
        block_start(), delta("text_delta", "Pronto."),
        result(),
    ])
    events = await collect(ClaudeCodeBackend(h.factory).run_turn(_conv(), "x", None, None))
    assert events[-1]["content"] == "Vou criar.\n\nPronto."
    tokens = "".join(e["content"] for e in events if e["type"] == "token")
    assert tokens == "Vou criar.\n\nPronto."


@pytest.mark.asyncio
async def test_avatar_controls_are_structured_and_removed_from_claude_text():
    h = Harness([
        delta("text_delta", "[expression:ded"),
        delta("text_delta", "uction]\n[gesture:deduction]\nA verdade é simples."),
        result(),
    ])
    conv = _conv()
    events = await collect(ClaudeCodeBackend(h.factory).run_turn(conv, "deduza", None, None))
    assert [event for event in events if event["type"] == "avatar"] == [
        {"type": "avatar", "expression": "deduction"},
        {"type": "avatar", "gesture": "deduction"},
    ]
    assert "".join(e["content"] for e in events if e["type"] == "token") == "A verdade é simples."
    assert events[-1]["content"] == "A verdade é simples."
    assert _assistant_messages(conv)[-1]["content"] == "A verdade é simples."


@pytest.mark.asyncio
async def test_final_text_after_tool_can_select_avatar_without_leaking_marker():
    h = Harness([
        block_start(), delta("text_delta", "Vou verificar."),
        AssistantMessage(content=[TextBlock(text="Vou verificar.")], model="m"),
        AssistantMessage(content=[ToolUseBlock(id="t1", name="Read", input={})], model="m"),
        UserMessage(content=[ToolResultBlock(tool_use_id="t1", content="ok", is_error=False)]),
        block_start(),
        delta("text_delta", "[expression:focused]\n[gesture:page-turn]\nResolvido."),
        result(),
    ])
    events = await collect(ClaudeCodeBackend(h.factory).run_turn(_conv(), "x", None, None))
    assert [event for event in events if event["type"] == "avatar"] == [
        {"type": "avatar", "expression": "focused"},
        {"type": "avatar", "gesture": "page-turn"},
    ]
    assert events[-1]["content"] == "Vou verificar.\n\nResolvido."


def test_append_prompt_carries_avatar_instructions():
    from app.core.avatar_protocol import AVATAR_INSTRUCTIONS
    assert AVATAR_INSTRUCTIONS in backend_mod.build_append_prompt(None, None)
