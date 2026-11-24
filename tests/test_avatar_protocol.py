"""Visual control markers ([expression:ID], [gesture:ID]).

Ported from Victorique-IA-2 and extended for the desktop mascot.
"""
import json

import pytest

from app.config import settings
from app.core.assistant import assistant_engine
from app.core.avatar_protocol import (
    AVATAR_INSTRUCTIONS,
    EXPRESSIONS,
    GESTURES,
    AvatarControlParser,
    avatar_manifest,
    split_leading_controls,
)
from app.memory.conversation_store import conversation_store
from app.models.ollama_client import ollama_client


def test_registered_controls_survive_every_stream_split():
    raw = "[expression:skeptical]\r\n[gesture:page-turn]\nOra, isto é evidente."
    for split in range(len(raw) + 1):
        parser = AvatarControlParser()
        controls, visible = [], []
        for chunk in (raw[:split], raw[split:]):
            found, text = parser.feed(chunk)
            controls.extend(found)
            visible.extend(text)
        found, text = parser.finish()
        controls.extend(found)
        visible.extend(text)
        assert controls == [
            {"type": "avatar", "expression": "skeptical"},
            {"type": "avatar", "gesture": "page-turn"},
        ]
        assert "".join(visible) == "Ora, isto é evidente."


def test_unknown_leading_controls_are_hidden_but_nonleading_text_is_preserved():
    parser = AvatarControlParser()
    controls, text = parser.feed("[expression:invented]\nResposta")
    assert controls == []
    assert "".join(text) == "Resposta"

    parser = AvatarControlParser()
    controls, text = parser.feed("Resposta [expression:happy]")
    assert controls == []
    assert "".join(text) == "Resposta [expression:happy]"


def test_ordinary_brackets_are_not_swallowed():
    parser = AvatarControlParser()
    controls, text = parser.feed("[1] primeiro item")
    found, rest = parser.finish()
    assert controls == [] and found == []
    assert "".join(text + rest) == "[1] primeiro item"


def test_truncated_marker_is_dropped_at_the_end():
    parser = AvatarControlParser()
    assert parser.feed("[expres") == ([], [])
    assert parser.finish() == ([], [])


def test_prompt_and_ids_are_bounded_data():
    assert "[expression:ID]" in AVATAR_INSTRUCTIONS
    assert "[gesture:ID]" in AVATAR_INSTRUCTIONS
    assert len(EXPRESSIONS) == len(set(EXPRESSIONS))
    assert len(GESTURES) == len(set(GESTURES))
    assert all(value.replace("-", "").isalnum() for value in (*EXPRESSIONS, *GESTURES))


def test_avatar_manifest_is_the_media_free_contract(client):
    manifest = avatar_manifest()
    assert manifest["schemaVersion"] == 1
    assert manifest["renderer"] == "desktop-mascot"
    assert manifest["media"] is False
    assert manifest["expressions"] == list(EXPRESSIONS)
    assert [item["id"] for item in manifest["gestures"]] == list(GESTURES)

    response = client.get("/api/avatar/manifest")
    assert response.status_code == 200
    assert response.json() == manifest


@pytest.mark.parametrize("text, expected", [
    ("[expression:happy]\n{\"name\": \"x\"}", ("[expression:happy]\n", "{\"name\": \"x\"}")),
    ("[expression:focused]\n[gesture:pipe]\nTexto", ("[expression:focused]\n[gesture:pipe]\n", "Texto")),
    ("Texto simples", ("", "Texto simples")),
    ("[1] item", ("", "[1] item")),
])
def test_split_leading_controls(text, expected):
    assert split_leading_controls(text) == expected


@pytest.mark.parametrize("partial", ["[", "[expr", "[expression:hap", "[expression:happy]\n[ges"])
def test_split_leading_controls_waits_on_unfinished_marker(partial):
    assert split_leading_controls(partial) is None


async def _run(monkeypatch, tokens, tools=False):
    async def fake_tokens(*args, **kwargs):
        for token in tokens:
            yield token

    async def fake_context(*args, **kwargs):
        return {"system_prompt": "teste", "messages": [], "sources": []}

    monkeypatch.setattr(ollama_client, "chat_stream", fake_tokens)
    monkeypatch.setattr("app.core.assistant.context_builder.build_context", fake_context)
    monkeypatch.setattr(settings, "tool_calling_enabled", tools)

    conv = conversation_store.create_conversation(title="Avatar protocol")
    try:
        events = []
        async for chunk in assistant_engine.chat_stream(
            conversation_id=conv["id"], user_message="resolva", backend="ollama"
        ):
            events.append(json.loads(chunk.removeprefix("data: ")))
        saved = conversation_store.get_messages(conv["id"])[-1]["content"]
        return events, saved
    finally:
        conversation_store.delete_conversation(conv["id"])


@pytest.mark.asyncio
@pytest.mark.parametrize("tools", [False, True])
async def test_model_controls_become_sse_and_never_reach_saved_text(monkeypatch, tools):
    events, saved = await _run(
        monkeypatch, ("[expression:happy]", "\n[gesture:tea]", "\nHmph. Resolvido."), tools=tools)
    avatar = [event for event in events if event["type"] == "avatar"]
    assert avatar == [
        {"type": "avatar", "expression": "happy"},
        {"type": "avatar", "gesture": "tea"},
    ]
    assert "".join(e["content"] for e in events if e["type"] == "token") == "Hmph. Resolvido."
    assert events[-1]["content"] == "Hmph. Resolvido."
    assert saved == "Hmph. Resolvido."


@pytest.mark.asyncio
async def test_marker_before_a_local_tool_call_does_not_hide_the_call(monkeypatch):
    async def fake_tokens(*args, **kwargs):
        for token in ("[expression:focused]\n", '{"name": "get_system_metrics", ', '"arguments": {}}'):
            yield token

    monkeypatch.setattr(ollama_client, "chat_stream", fake_tokens)
    state = {"buffering": True, "prefix": "", "text": [], "calls": [],
             "strip_fence": False, "use_llama_cpp": False, "backend_name": "ollama"}
    shown = [t async for t in assistant_engine._stream_model_round(state, messages=[])]
    assert shown == []
    assert len(state["calls"]) == 1 and "get_system_metrics" in json.dumps(state["calls"][0])


@pytest.mark.asyncio
async def test_marker_before_prose_is_flushed_for_the_parser(monkeypatch):
    async def fake_tokens(*args, **kwargs):
        for token in ("[expression:happy]", "\nOra, ", "claro."):
            yield token

    monkeypatch.setattr(ollama_client, "chat_stream", fake_tokens)
    state = {"buffering": True, "prefix": "", "text": [], "calls": [],
             "strip_fence": False, "use_llama_cpp": False, "backend_name": "ollama"}
    shown = [t async for t in assistant_engine._stream_model_round(state, messages=[])]
    assert "".join(shown) == "[expression:happy]\nOra, claro."
    assert state["calls"] == []
