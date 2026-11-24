"""Modo Codex: `codex exec --json` traduzido para os eventos SSE da interface."""
import io
import json

import pytest

from app.codex import backend as codex
from app.config import settings
from app.library import activity
from app.memory.conversation_store import conversation_store

THREAD = "0199a213-81c0-7800-8aa1-bbab2a035a53"


class FakeStdin:
    def __init__(self):
        self.data = []
        self.closed = False

    def write(self, text):
        self.data.append(text)
        return len(text)

    def close(self):
        self.closed = True


class FakeProcess:
    """Stands in for subprocess.Popen: JSONL on stdout, text on stderr."""

    def __init__(self, events, code=0, stderr=""):
        self.stdin = FakeStdin()
        self.stdout = io.StringIO("".join(json.dumps(e) + "\n" for e in events))
        self.stderr = io.StringIO(stderr)
        self.returncode = None
        self._code = code
        self.killed = False

    def wait(self, timeout=None):
        self.returncode = self._code
        return self._code

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True

    @property
    def prompt(self):
        return "".join(self.stdin.data)


def factory_for(*processes):
    calls = []
    pending = list(processes)

    def factory(cmd, cwd):
        calls.append(cmd)
        return pending.pop(0)

    factory.calls = calls
    return factory


async def collect(gen):
    return [json.loads(chunk[len("data: "):]) async for chunk in gen]


def new_conversation(text="Leia as notas."):
    conv = conversation_store.create_conversation(title="Codex")
    conversation_store.add_message(conversation_id=conv["id"], role="user", content=text)
    return conv["id"]


def assistant_messages(conv_id):
    return [m for m in conversation_store.get_messages(conv_id) if m["role"] == "assistant"]


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "codex_workspace", str(tmp_path))
    monkeypatch.setattr(settings, "codex_model", "")
    activity.clear()
    yield tmp_path
    activity.clear()


def test_build_command_is_read_only_and_resumes():
    cmd = codex.build_command(["codex"], "C:/caso", None, "")
    assert cmd[:2] == ["codex", "exec"] and "--json" in cmd and "--skip-git-repo-check" in cmd
    assert cmd[cmd.index("--sandbox") + 1] == "read-only"
    assert cmd[cmd.index("-C") + 1] == "C:/caso"
    assert cmd[-1] == "-" and "resume" not in cmd and "-m" not in cmd
    again = codex.build_command(["node", "codex.js"], "C:/caso", THREAD, "gpt-5-codex")
    assert again[:3] == ["node", "codex.js", "exec"]
    assert again[-3:] == ["resume", THREAD, "-"]
    assert again[again.index("-m") + 1] == "gpt-5-codex"
    assert again.index("--sandbox") < again.index("resume")   # global flags before the subcommand
    joined = " ".join(again)
    assert "danger-full-access" not in joined and "bypass" not in joined and "workspace-write" not in joined


@pytest.mark.asyncio
async def test_turn_translates_jsonl_events(workspace):
    (workspace / "notas.txt").write_text("oi", encoding="utf-8")
    process = FakeProcess([
        {"type": "thread.started", "thread_id": THREAD},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "item_0", "type": "reasoning", "text": "**Lendo a pasta**"}},
        {"type": "item.started", "item": {"id": "item_1", "type": "command_execution",
                                          "command": "Get-Content notas.txt", "aggregated_output": "",
                                          "exit_code": None, "status": "in_progress"}},
        {"type": "item.completed", "item": {"id": "item_1", "type": "command_execution",
                                            "command": "Get-Content notas.txt", "aggregated_output": "oi\n",
                                            "exit_code": 0, "status": "completed"}},
        {"type": "item.completed", "item": {"id": "item_2", "type": "agent_message",
                                            "text": "[expression:neutral]Elementar. O arquivo diz oi."}},
        {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}},
    ])
    factory = factory_for(process)
    backend = codex.CodexBackend(process_factory=factory, finder=lambda: ["codex"])
    conv_id = new_conversation()

    events = await collect(backend.run_turn(conv_id, "Leia as notas.", None, None))

    kinds = [e["type"] for e in events]
    assert kinds[0] == "meta" and events[0]["backend"] == "codex" and kinds[-1] == "done"
    assert {"type": "reasoning", "content": "**Lendo a pasta**"} in events
    call = next(e for e in events if e["type"] == "tool_call")
    assert call["tool"] == "Shell" and call["arguments"]["command"] == "Get-Content notas.txt"
    assert kinds.count("tool_call") == 1                    # started + completed = one call
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["status"] == "success" and "oi" in result["result"]["result"]
    assert any(e["type"] == "avatar" for e in events)       # the hidden marker became a signal
    answer = "".join(e["content"] for e in events if e["type"] == "token")
    assert answer == "Elementar. O arquivo diz oi."
    assert events[-1]["content"] == answer
    saved = assistant_messages(conv_id)[-1]
    assert saved["content"] == answer
    assert conversation_store.get_codex_thread(conv_id) == THREAD
    assert "resume" not in factory.calls[0]
    assert "<instrucoes_do_aplicativo>" in process.prompt and "Leia as notas." in process.prompt
    assert "OpenAI" in process.prompt and process.stdin.closed
    reads = [e for e in activity.since(0)["events"] if e["kind"] == "read"]
    assert reads and reads[-1]["name"] == "notas.txt"


@pytest.mark.asyncio
async def test_missing_codex_gives_install_help(workspace):
    factory = factory_for()
    backend = codex.CodexBackend(process_factory=factory, finder=lambda: None)
    conv_id = new_conversation("Oi")
    events = await collect(backend.run_turn(conv_id, "Oi", None, None))
    error = next(e for e in events if e["type"] == "error")["message"]
    assert "npm install -g @openai/codex" in error and "codex login" in error
    assert events[-1]["type"] == "done" and factory.calls == []
    assert "npm install" in assistant_messages(conv_id)[-1]["content"]


@pytest.mark.asyncio
async def test_resume_failure_starts_new_thread_with_notice(workspace):
    old = "0199aaaa-0000-7000-8000-000000000001"
    failed = FakeProcess([], code=1, stderr="Error: no rollout found for thread id\n")
    fresh = FakeProcess([
        {"type": "thread.started", "thread_id": THREAD},
        {"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": "Pronto."}},
        {"type": "turn.completed", "usage": {}},
    ])
    factory = factory_for(failed, fresh)
    backend = codex.CodexBackend(process_factory=factory, finder=lambda: ["codex"])
    conv_id = new_conversation("Continue.")
    conversation_store.set_codex_thread(conv_id, old)

    events = await collect(backend.run_turn(conv_id, "Continue.", None, None))

    assert factory.calls[0][-3:] == ["resume", old, "-"]
    assert "resume" not in factory.calls[1]
    assert {"type": "notice", "message": codex.RESUME_NOTICE} in events
    assert not any(e["type"] == "error" for e in events)
    assert "".join(e["content"] for e in events if e["type"] == "token") == "Pronto."
    assert conversation_store.get_codex_thread(conv_id) == THREAD
    assert "<instrucoes_do_aplicativo>" not in failed.prompt          # resumed turns: short reminder
    assert "<instrucoes_do_aplicativo>" in fresh.prompt               # new thread: full instructions


@pytest.mark.asyncio
async def test_login_failure_suggests_codex_login(workspace):
    process = FakeProcess([
        {"type": "thread.started", "thread_id": THREAD},
        {"type": "error", "message": "unexpected status 401 Unauthorized"},
        {"type": "turn.failed", "error": {"message": "unexpected status 401 Unauthorized"}},
    ], code=1)
    backend = codex.CodexBackend(process_factory=factory_for(process), finder=lambda: ["codex"])
    conv_id = new_conversation("Oi")
    events = await collect(backend.run_turn(conv_id, "Oi", None, None))
    error = next(e for e in events if e["type"] == "error")["message"]
    assert "codex login" in error
    assert backend.last_error == error
    assert conversation_store.get_codex_thread(conv_id) is None     # a failed turn is not resumed


@pytest.mark.asyncio
async def test_deep_thinking_turns_her_thought_into_voice_reasoning(workspace):
    process = FakeProcess([
        {"type": "thread.started", "thread_id": THREAD},
        {"type": "item.completed", "item": {"id": "r", "type": "reasoning", "text": "interno"}},
        {"type": "item.completed", "item": {"id": "m", "type": "agent_message",
                                            "text": "<pensamento>Hm, simples.</pensamento>Resposta."}},
        {"type": "turn.completed", "usage": {}},
    ])
    backend = codex.CodexBackend(process_factory=factory_for(process), finder=lambda: ["codex"])
    conv_id = new_conversation("Pense.")
    events = await collect(backend.run_turn(conv_id, "Pense.", None, None, deep_thinking=True))
    voice = [e for e in events if e["type"] == "reasoning"]
    assert voice and all(e.get("voice") for e in voice)           # the model's own reasoning is hidden
    assert "".join(e["content"] for e in voice).strip() == "Hm, simples."
    assert "".join(e["content"] for e in events if e["type"] == "token") == "Resposta."
    assert "reasoning_seconds" in events[-1]
    assert assistant_messages(conv_id)[-1]["reasoning"] == "Hm, simples."
    assert "<pensamento>" in process.prompt


def test_codex_mode_is_wired_into_the_app(client, monkeypatch):
    monkeypatch.setattr(codex, "find_codex", lambda: None)
    status = client.get("/api/codex/status").json()
    assert status["installed"] is False and "npm install -g @openai/codex" in " ".join(status["install"])
    assert "codex" in client.get("/api/settings").json()["available_backends"]
    with client.stream("POST", "/api/chat", json={"message": "Oi", "backend": "codex"}) as response:
        body = "".join(response.iter_text())
    assert "npm install -g @openai/codex" in body
