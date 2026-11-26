"""
Cliente do llama-server: raciocínio separado da resposta, ferramentas nativas
(formato OpenAI) e conversão do histórico interno para esse formato.
"""
import json

import httpx
import pytest

from app.core.assistant import assistant_engine
from app.memory.conversation_store import conversation_store
from app.models.events import ReasoningDelta
from app.models.llama_cpp_server_client import LlamaCppServerClient, to_openai_messages


def _sse(*chunks) -> bytes:
    lines = [f"data: {json.dumps(c)}\n\n" for c in chunks]
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode("utf-8")


def _delta(**delta):
    return {"choices": [{"index": 0, "delta": delta}]}


def _client_with(body: bytes, captured: dict) -> LlamaCppServerClient:
    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    client = LlamaCppServerClient(transport=httpx.MockTransport(handler))
    client._available = True
    return client


@pytest.mark.asyncio
async def test_reasoning_is_yielded_separately_from_content():
    captured = {}
    client = _client_with(_sse(
        _delta(reasoning_content="Vou pensar. "),
        _delta(reasoning_content="Pronto."),
        _delta(content="Resposta "),
        _delta(content="final."),
    ), captured)

    items = [x async for x in client.chat_stream(messages=[{"role": "user", "content": "oi"}])]

    reasoning = "".join(x.text for x in items if isinstance(x, ReasoningDelta))
    text = "".join(x for x in items if isinstance(x, str))
    assert reasoning == "Vou pensar. Pronto."
    assert text == "Resposta final."


@pytest.mark.asyncio
async def test_context_overflow_retries_without_the_oldest_turn():
    payloads = []

    def handler(request):
        payloads.append(json.loads(request.content))
        if len(payloads) == 1:
            return httpx.Response(400, json={"error": {
                "type": "exceed_context_size_error", "n_prompt_tokens": 8263, "n_ctx": 8192,
            }})
        return httpx.Response(200, content=_sse(_delta(content="Oi!")))

    client = LlamaCppServerClient(transport=httpx.MockTransport(handler))
    client._available = True
    messages = [
        {"role": "user", "content": "pergunta antiga"},
        {"role": "assistant", "content": "resposta antiga"},
        {"role": "user", "content": "oi"},
        {"role": "assistant", "tool_calls": [
            {"id": "call_a", "function": {"name": "calculate", "arguments": {}}},
        ]},
        {"role": "tool", "tool_call_id": "call_a", "content": "42"},
    ]
    tools = [{"type": "function", "function": {"name": "calculate", "parameters": {}}}]
    result = [x async for x in client.chat_stream(messages, system_prompt="Instruções", tools=tools)]

    assert result == ["Oi!"]
    assert payloads[1]["messages"] == payloads[0]["messages"][:1] + to_openai_messages(messages[2:])
    assert payloads[1]["tools"] == tools
    assert len(messages) == 5


@pytest.mark.asyncio
async def test_context_is_budgeted_before_generation():
    sent = []

    def handler(request):
        payload = json.loads(request.content)
        if request.url.path == "/apply-template":
            return httpx.Response(200, json={"prompt": json.dumps(payload, ensure_ascii=False)})
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"tokens": list(map(ord, payload["content"]))})
        if request.url.path == "/detokenize":
            return httpx.Response(200, json={"content": "".join(map(chr, payload["tokens"]))})
        assert request.url.path == "/v1/chat/completions"
        sent.append(payload)
        return httpx.Response(200, content=_sse(_delta(content="Certo.")))

    client = LlamaCppServerClient(n_ctx=8192, transport=httpx.MockTransport(handler))
    client._available = True
    previews = "Prévia de relatório: " + "a" * 4000
    tool_result = "Resultado: " + "b" * 3000
    messages = [
        {"role": "user", "content": "pergunta antiga " + "z" * 10000},
        {"role": "assistant", "content": "Resposta antiga."},
        {"role": "user", "content": "pergunta recente"},
        {"role": "assistant", "content": "Resposta recente."},
        {"role": "user", "content": "Pedido atual\nAnexo: relatório\n\n" + previews,
         "attachment_previews": previews},
        {"role": "assistant", "tool_calls": [
            {"id": "call_a", "function": {"name": "read_file", "arguments": {}}},
        ]},
        {"role": "tool", "tool_call_id": "call_a", "content": tool_result},
    ]
    result = [x async for x in client.chat_stream(
        messages, system_prompt="Instruções", num_ctx=8192, max_tokens=8192,
    )]

    assert result == ["Certo."] and len(sent) == 1
    request = sent[0]
    system, recent, _, current, call, tool = request["messages"]
    assert "Resumo de falas antigas" in system["content"] and "pergunta antiga" in system["content"]
    assert recent["content"] == "pergunta recente"
    assert current["content"].startswith("Pedido atual\nAnexo: relatório")
    assert current["content"].endswith("[prévia truncada]")
    assert tool["tool_call_id"] == call["tool_calls"][0]["id"] == "call_a"
    assert tool["content"].startswith("Resultado: ") and tool["content"].endswith("[resultado truncado]")
    size = len(json.dumps({"messages": request["messages"]}, ensure_ascii=False))
    assert 1024 <= request["max_tokens"] <= 8192 - size
    assert messages[-1]["content"] == tool_result


@pytest.mark.asyncio
async def test_native_tool_call_deltas_are_accumulated_and_tools_are_sent():
    captured = {}
    client = _client_with(_sse(
        _delta(tool_calls=[{"index": 0, "id": "call_a", "type": "function",
                            "function": {"name": "calculate", "arguments": ""}}]),
        _delta(tool_calls=[{"index": 0, "function": {"arguments": "{\"expression\": "}}]),
        _delta(tool_calls=[{"index": 0, "function": {"arguments": "\"6 * 7\"}"}}]),
    ), captured)
    tools = [{"type": "function", "function": {"name": "calculate", "parameters": {}}}]
    calls = []

    items = [x async for x in client.chat_stream(
        messages=[{"role": "user", "content": "6*7?"}], tools=tools, tool_calls_out=calls,
    )]

    assert captured["payload"]["tools"] == tools
    assert items == []
    assert calls == [{"id": "call_a", "function": {"name": "calculate", "arguments": {"expression": "6 * 7"}}}]


def test_internal_history_is_converted_to_openai_format():
    internal = [
        {"role": "user", "content": "6*7?"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_a", "function": {"name": "calculate", "arguments": {"expression": "6 * 7"}}},
        ]},
        {"role": "tool", "tool_name": "calculate", "tool_call_id": "call_a", "content": "{\"result\": 42}"},
    ]
    converted = to_openai_messages(internal)
    assert converted[1] == {
        "role": "assistant",
        "content": "",
        "tool_calls": [{
            "id": "call_a", "type": "function",
            "function": {"name": "calculate", "arguments": "{\"expression\": \"6 * 7\"}"},
        }],
    }
    assert converted[2] == {"role": "tool", "tool_call_id": "call_a", "content": "{\"result\": 42}"}


def test_server_is_started_with_jinja_for_tool_calling():
    client = LlamaCppServerClient()
    assert "--jinja" in client.build_args()


@pytest.mark.asyncio
async def test_engine_emits_reasoning_event_but_never_stores_or_speaks_it(monkeypatch):
    from app.models.ollama_client import ollama_client

    async def fake_context(*args, **kwargs):
        return {"system_prompt": "t", "messages": [{"role": "user", "content": "oi"}], "sources": []}

    async def fake_stream(*args, **kwargs):
        yield ReasoningDelta("pensamento secreto")
        yield "Olá!"

    spoken = []
    monkeypatch.setattr("app.core.assistant.context_builder.build_context", fake_context)
    monkeypatch.setattr(ollama_client, "chat_stream", fake_stream)
    monkeypatch.setattr("app.core.assistant.tts_engine.speak_async", spoken.append)

    conv = conversation_store.create_conversation(title="Raciocínio")
    events = []
    async for chunk in assistant_engine.chat_stream(
        conversation_id=conv["id"], user_message="oi", enable_rag=False
    ):
        events.append(json.loads(chunk.replace("data: ", "")))

    assert {"type": "reasoning", "content": "pensamento secreto"} in events
    tokens = "".join(e["content"] for e in events if e["type"] == "token")
    assert "pensamento" not in tokens
    assert events[-1]["content"] == "Olá!"
    stored = conversation_store.get_messages(conv["id"])
    assert all("pensamento" not in m["content"] for m in stored)
    assert all("pensamento" not in s for s in spoken)
    conversation_store.delete_conversation(conv["id"])


@pytest.mark.asyncio
async def test_tool_results_are_kept_for_the_next_turn(monkeypatch):
    from app.core.context_builder import context_builder
    from app.models.ollama_client import ollama_client

    async def fake_context(*args, **kwargs):
        return {"system_prompt": "t", "messages": [{"role": "user", "content": "6*7?"}], "sources": []}

    rounds = {"n": 0}
    seen_messages = []

    async def fake_stream(*args, **kwargs):
        rounds["n"] += 1
        seen_messages.append(kwargs["messages"])
        if rounds["n"] == 1:
            kwargs["tool_calls_out"].append(
                {"function": {"name": "calculate", "arguments": {"expression": "6 * 7"}}}
            )
            return
        yield "Deu 42."

    monkeypatch.setattr("app.core.assistant.context_builder.build_context", fake_context)
    monkeypatch.setattr(ollama_client, "chat_stream", fake_stream)

    conv = conversation_store.create_conversation(title="Rastro")
    async for _ in assistant_engine.chat_stream(
        conversation_id=conv["id"], user_message="6*7?", enable_rag=False
    ):
        pass

    # Within the turn, the tool message references the call id.
    second_round = seen_messages[1]
    assistant_call = [m for m in second_round if m.get("tool_calls")][0]
    tool_msg = [m for m in second_round if m["role"] == "tool"][0]
    assert tool_msg["tool_call_id"] == assistant_call["tool_calls"][0]["id"]

    # Across turns, the stored answer keeps a trace the model can read.
    stored = conversation_store.get_messages(conv["id"])
    answer = [m for m in stored if m["role"] == "assistant"][-1]
    assert answer["content"] == "Deu 42."
    assert answer["tool_trace"][0]["tool"] == "calculate"

    monkeypatch.undo()
    ctx = await context_builder.build_context(
        user_query="e agora?", conversation_history=stored, enable_rag=False
    )
    history_text = json.dumps(ctx["messages"], ensure_ascii=False)
    assert "calculate" in history_text and "42" in history_text
    conversation_store.delete_conversation(conv["id"])
