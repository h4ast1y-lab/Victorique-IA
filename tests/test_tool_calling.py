import json
from pathlib import Path

import pytest

from app.core.assistant import assistant_engine
from app.memory.conversation_store import conversation_store
from app.models.ollama_client import ollama_client
from app.security.path_guard import path_guard
from app.tools.registry import tool_registry


async def _fake_context(*args, **kwargs):
    return {
        "system_prompt": "teste",
        "messages": [{"role": "user", "content": "oi"}],
        "sources": [],
    }


def _install_context(monkeypatch):
    monkeypatch.setattr(
        "app.core.assistant.context_builder.build_context", _fake_context
    )


async def _collect(conversation_id, message):
    events = []
    async for chunk in assistant_engine.chat_stream(
        conversation_id=conversation_id,
        user_message=message,
        enable_rag=False,
    ):
        events.append(json.loads(chunk.replace("data: ", "")))
    return events


@pytest.mark.asyncio
async def test_raw_json_tool_call_is_parsed_and_executed(monkeypatch):
    _install_context(monkeypatch)
    rounds = {"n": 0}

    async def fake_stream(*args, **kwargs):
        rounds["n"] += 1
        if rounds["n"] == 1:
            yield '{"name": "calculate", "arguments": {"expression": "6 * 7"}}'
        else:
            yield "O resultado é 42."

    monkeypatch.setattr(ollama_client, "chat_stream", fake_stream)

    conv = conversation_store.create_conversation(title="Tool JSON")
    events = await _collect(conv["id"], "Quanto é 6 * 7?")

    types = [e["type"] for e in events]
    assert "tool_call" in types and "tool_result" in types
    call = [e for e in events if e["type"] == "tool_call"][0]
    assert call["tool"] == "calculate"
    result = [e for e in events if e["type"] == "tool_result"][0]
    assert result["status"] == "success"
    assert result["result"]["result"]["result"] == 42

    done = events[-1]
    assert done["type"] == "done"
    assert done["tool_calls"] == 1
    assert done["content"] == "O resultado é 42."
    assert '{"name"' not in done["content"]
    conversation_store.delete_conversation(conv["id"])


@pytest.mark.asyncio
async def test_native_tool_calls_are_executed(monkeypatch):
    _install_context(monkeypatch)
    rounds = {"n": 0}

    async def fake_stream(*args, **kwargs):
        rounds["n"] += 1
        if rounds["n"] == 1:
            kwargs["tool_calls_out"].append({
                "function": {"name": "calculate", "arguments": {"expression": "2 + 2"}}
            })
            return
        yield "Quatro."

    monkeypatch.setattr(ollama_client, "chat_stream", fake_stream)

    conv = conversation_store.create_conversation(title="Tool nativo")
    events = await _collect(conv["id"], "Some 2 + 2.")

    assert [e["type"] for e in events].count("tool_call") == 1
    done = events[-1]
    assert done["content"] == "Quatro."
    assert done["tool_calls"] == 1
    conversation_store.delete_conversation(conv["id"])


@pytest.mark.asyncio
async def test_protected_tool_call_waits_for_approval(client, tmp_path, monkeypatch):
    _install_context(monkeypatch)
    path_guard.add_authorized_directory(str(tmp_path))
    target = tmp_path / "criado-pelo-modelo.txt"

    async def fake_stream(*args, **kwargs):
        yield json.dumps({
            "name": "write_file",
            "arguments": {"path": str(target), "content": "conteudo aprovado"},
        })

    monkeypatch.setattr(ollama_client, "chat_stream", fake_stream)

    conv = conversation_store.create_conversation(title="Tool protegida")
    events = await _collect(conv["id"], "Crie o arquivo.")

    assert not target.exists(), "nada pode ser escrito antes da aprovação"
    auth = [e for e in events if e["type"] == "authorization_required"]
    assert auth and auth[0]["tool_name"] == "write_file"
    action_id = auth[0]["action_id"]
    assert events[-1]["type"] == "done"
    assert events[-1]["pending_action_id"] == action_id

    approved = client.post(
        "/api/security/authorize", json={"action_id": action_id, "approved": True}
    )
    assert approved.status_code == 200, approved.text
    payload = approved.json()
    assert payload["status"] == "executed"
    assert payload["result"]["status"] == "success"
    assert payload["conversation_id"] == conv["id"]
    assert target.read_text(encoding="utf-8") == "conteudo aprovado"

    # Its result was persisted so the next model turn knows the outcome.
    messages = conversation_store.get_messages(conv["id"])
    assert any(
        m["role"] == "assistant" and "write_file" in m["content"] and "Resultado" in m["content"]
        for m in messages
    )

    replay = client.post(
        "/api/security/authorize", json={"action_id": action_id, "approved": True}
    )
    assert replay.status_code == 404
    conversation_store.delete_conversation(conv["id"])


@pytest.mark.asyncio
async def test_model_without_tools_support_falls_back(monkeypatch):
    _install_context(monkeypatch)
    rounds = {"n": 0}

    async def fake_stream(*args, **kwargs):
        rounds["n"] += 1
        if rounds["n"] == 1:
            raise RuntimeError("model does not support tools")
        yield "Resposta sem ferramentas."

    monkeypatch.setattr(ollama_client, "chat_stream", fake_stream)

    conv = conversation_store.create_conversation(title="Sem tools")
    events = await _collect(conv["id"], "Olá.")

    notices = [e for e in events if e["type"] == "notice"]
    assert notices and "não suporta" in notices[0]["message"]
    assert events[-1]["type"] == "done"
    assert events[-1]["content"] == "Resposta sem ferramentas."
    conversation_store.delete_conversation(conv["id"])


@pytest.mark.asyncio
async def test_tool_round_limit_prevents_infinite_loop(monkeypatch):
    _install_context(monkeypatch)

    async def fake_stream(*args, **kwargs):
        kwargs["tool_calls_out"].append({
            "function": {"name": "calculate", "arguments": {"expression": "1 + 1"}}
        })
        return
        yield  # pragma: no cover (keeps this an async generator)

    monkeypatch.setattr(ollama_client, "chat_stream", fake_stream)

    conv = conversation_store.create_conversation(title="Loop")
    events = await _collect(conv["id"], "Loop.")
    calls = [e for e in events if e["type"] == "tool_call"]
    notices = [e for e in events if e["type"] == "notice"]
    assert len(calls) <= 3
    assert notices and "Limite" in notices[-1]["message"]
    assert events[-1]["type"] == "done"
    conversation_store.delete_conversation(conv["id"])


def test_raw_json_tool_call_parser_variants():
    from app.core.assistant import _parse_text_tool_call, _unwrap_code_fence

    fence = "`" * 3
    assert _parse_text_tool_call(
        '{"name": "calculate", "arguments": {"expression": "1+1"}}'
    )["function"]["name"] == "calculate"
    assert _parse_text_tool_call(
        fence + 'json\n{"name": "calculate", "arguments": {"expression": "1+1"}}\n' + fence
    )["function"]["arguments"] == {"expression": "1+1"}
    assert _parse_text_tool_call(
        '{"type": "function", "function": {"name": "calculate", '
        '"arguments": {"expression": "1+1"}}}'
    )["function"]["name"] == "calculate"
    assert _parse_text_tool_call(
        '{"type": "exec", "function": {"name": "calculate", "arguments": {}}}'
    ) is None
    # Invented extra keys and unknown tools are rejected, not guessed.
    assert _parse_text_tool_call(
        '{"name": "calculate", "arguments": {"expression": "1+1"}, "thought": "x"}'
    ) is None
    assert _parse_text_tool_call(
        '{"name": "rm_rf", "arguments": {"path": "/"}}'
    ) is None
    assert _parse_text_tool_call("apenas uma frase") is None
    assert _unwrap_code_fence(fence + "\ntexto normal\n" + fence) == "texto normal"
    assert _unwrap_code_fence(fence + "texto na mesma linha\n" + fence) == "texto na mesma linha"
    assert _unwrap_code_fence(fence + 'json\n{"a": 1}\n' + fence) == '{"a": 1}'
    assert _unwrap_code_fence("sem cerca") == "sem cerca"


@pytest.mark.asyncio
async def test_split_backticks_do_not_leak_fence(monkeypatch):
    _install_context(monkeypatch)
    rounds = {"n": 0}

    async def fake_stream(*args, **kwargs):
        rounds["n"] += 1
        if rounds["n"] == 1:
            yield '{"name": "calculate", "arguments": {"expression": "1+1"}}'
            return
        # Prose fenced with backticks split across chunks, as some models
        # stream them.
        yield "`"
        yield "`"
        yield "`"
        yield "O resultado é 2.\n"
        yield "`"
        yield "`"
        yield "`"

    monkeypatch.setattr(ollama_client, "chat_stream", fake_stream)

    conv = conversation_store.create_conversation(title="Crases")
    events = await _collect(conv["id"], "Calcule.")

    done = events[-1]
    assert done["type"] == "done"
    assert "`" not in done["content"], done["content"]
    assert "O resultado é 2." in done["content"]
    conversation_store.delete_conversation(conv["id"])


@pytest.mark.asyncio
async def test_fenced_prose_is_shown_without_fence(monkeypatch):
    _install_context(monkeypatch)

    async def fake_stream(*args, **kwargs):
        yield "```\n\n"
        yield "Preciso da sua autorização para executar `write_file` em `a.txt`. "
        yield "Nada foi executado ainda.\n```"

    monkeypatch.setattr(ollama_client, "chat_stream", fake_stream)

    conv = conversation_store.create_conversation(title="Cerca")
    events = await _collect(conv["id"], "Crie o arquivo.")

    assert not any(e["type"] == "tool_call" for e in events)
    done = events[-1]
    assert done["type"] == "done"
    assert done["content"].startswith("Preciso da sua autorização")
    assert "```" not in done["content"]
    conversation_store.delete_conversation(conv["id"])


def test_tool_schemas_and_required_arguments(client):
    tools = client.get("/api/tools/list").json()
    names = {t["name"] for t in tools}
    assert {"calculate", "write_file", "search_web", "read_file"} <= names
    for tool in tools:
        assert tool["parameters"]["type"] == "object"
        assert "properties" in tool["parameters"]

    missing = client.post(
        "/api/tools/execute", json={"tool_name": "calculate", "parameters": {}}
    ).json()
    assert missing["status"] == "error"
    assert "obrigat" in missing["error"].lower()

    unknown = client.post(
        "/api/tools/execute", json={"tool_name": "nao_existe", "parameters": {}}
    ).json()
    assert unknown["status"] == "error"


def test_model_cannot_execute_protected_tool_directly(client, tmp_path):
    path_guard.add_authorized_directory(str(tmp_path))
    target = tmp_path / "sem-aprovacao.txt"
    result = client.post(
        "/api/tools/execute",
        json={
            "tool_name": "write_file",
            "parameters": {"path": str(target), "content": "x"},
            "authorized": True,
        },
    ).json()
    assert result["status"] == "requires_authorization"
    assert not target.exists()


@pytest.mark.asyncio
async def test_read_url_tool_call_stops_at_authorization(monkeypatch):
    _install_context(monkeypatch)

    async def fake_stream(*args, **kwargs):
        yield '{"name": "read_url", "arguments": {"url": "https://example.com/artigo"}}'

    monkeypatch.setattr(ollama_client, "chat_stream", fake_stream)
    conv = conversation_store.create_conversation(title="Teste Read URL")
    try:
        events = await _collect(conv["id"], "O que diz esse artigo https://example.com/artigo?")
        types = [e["type"] for e in events]
        assert "tool_call" in types
        assert "authorization_required" in types
        auth_ev = [e for e in events if e["type"] == "authorization_required"][0]
        assert auth_ev["tool_name"] == "read_url"
        assert "example.com" in auth_ev["resource"]
    finally:
        conversation_store.delete_conversation(conv["id"])
