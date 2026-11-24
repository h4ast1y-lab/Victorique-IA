"""Pensamento Profundo: the thought block in her voice, split from the answer."""
import json

import pytest

from app.core.assistant import assistant_engine
from app.core.deep_thinking import DEEP_THINKING_INSTRUCTIONS, ThoughtSplitter
from app.memory.conversation_store import conversation_store
from app.models.events import ReasoningDelta
from app.models.ollama_client import ollama_client


def _run(chunks):
    splitter = ThoughtSplitter()
    out = []
    for chunk in chunks:
        out.extend(splitter.feed(chunk))
    out.extend(splitter.finish())
    thought = "".join(text for kind, text in out if kind == "thought")
    answer = "".join(text for kind, text in out if kind == "answer")
    return thought, answer


def test_splitter_separates_thought_and_answer():
    thought, answer = _run(["<pensamento>Hm, um enigma.</pensamento>\n\nA resposta é 4."])
    assert thought == "Hm, um enigma."
    assert answer == "A resposta é 4."


def test_splitter_handles_tag_split_across_chunks():
    thought, answer = _run(["  <pensa", "mento>abc</pen", "samento>", "\n", "resp", "osta"])
    assert thought == "abc"
    assert answer == "resposta"


def test_splitter_without_tag_is_all_answer():
    thought, answer = _run(["Sem pensar ", "em voz alta."])
    assert thought == ""
    assert answer == "Sem pensar em voz alta."


def test_splitter_less_than_sign_in_plain_answer_is_kept():
    thought, answer = _run(["<", "b> não é tag de pensamento"])
    assert thought == ""
    assert answer == "<b> não é tag de pensamento"


def test_splitter_keeps_leading_avatar_controls_in_answer():
    thought, answer = _run(["[expression:thinking]\n", "<pensamento>pista</pensamento>", "Resposta"])
    assert thought == "pista"
    assert answer.startswith("[expression:thinking]")
    assert answer.endswith("Resposta")


def test_splitter_is_case_insensitive_and_strips_thought_edges():
    thought, answer = _run(["<Pensamento>\n  ideia\n</PENSAMENTO>fim"])
    assert thought == "ideia"
    assert answer == "fim"


def test_unclosed_thought_is_flushed_as_thought_on_finish():
    thought, answer = _run(["<pensamento>pensei até acabar o espa", "ço"])
    assert thought == "pensei até acabar o espaço"
    assert answer == ""


def test_instructions_ask_for_the_block_in_her_voice():
    assert "<pensamento>" in DEEP_THINKING_INSTRUCTIONS
    assert "</pensamento>" in DEEP_THINKING_INSTRUCTIONS
    assert "primeira pessoa" in DEEP_THINKING_INSTRUCTIONS


def test_reasoning_saved_and_returned_by_store():
    conv = conversation_store.create_conversation(title="Pensou")
    conversation_store.add_message(conv["id"], "assistant", "Resposta", reasoning="Hm.", reasoning_seconds=2.5)
    message = conversation_store.get_messages(conv["id"])[-1]
    assert message["reasoning"] == "Hm."
    assert message["reasoning_seconds"] == 2.5
    conversation_store.delete_conversation(conv["id"])


async def _fake_context(*args, **kwargs):
    return {"system_prompt": "base", "messages": [{"role": "user", "content": "oi"}], "sources": []}


@pytest.mark.asyncio
async def test_local_turn_with_deep_thinking_emits_voice_reasoning(monkeypatch):
    monkeypatch.setattr("app.core.assistant.context_builder.build_context", _fake_context)
    seen = {}

    async def fake_stream(*args, **kwargs):
        seen["system"] = kwargs.get("system_prompt", "")
        yield ReasoningDelta("native reasoning in English")
        yield "<pensamento>Uma soma. Fácil"
        yield " demais.</pensamento>\n"
        yield "Dá 4."

    monkeypatch.setattr(ollama_client, "chat_stream", fake_stream)
    conv = conversation_store.create_conversation(title="Profundo")
    events = []
    async for chunk in assistant_engine.chat_stream(
        conversation_id=conv["id"], user_message="2+2?", backend="ollama",
        enable_rag=False, deep_thinking=True,
    ):
        events.append(json.loads(chunk.replace("data: ", "")))

    reasoning = [e for e in events if e["type"] == "reasoning"]
    assert "".join(e["content"] for e in reasoning) == "Uma soma. Fácil demais."
    assert all(e.get("voice") for e in reasoning)
    assert "native" not in json.dumps(reasoning)
    assert "".join(e["content"] for e in events if e["type"] == "token") == "Dá 4."
    assert "<pensamento>" in seen["system"]
    done = events[-1]
    assert done["type"] == "done" and done["content"] == "Dá 4."
    assert done["reasoning_seconds"] >= 0
    saved = conversation_store.get_messages(conv["id"])[-1]
    assert saved["content"] == "Dá 4."
    assert saved["reasoning"] == "Uma soma. Fácil demais."
    conversation_store.delete_conversation(conv["id"])


@pytest.mark.asyncio
async def test_local_turn_without_deep_thinking_keeps_native_reasoning(monkeypatch):
    monkeypatch.setattr("app.core.assistant.context_builder.build_context", _fake_context)

    async def fake_stream(*args, **kwargs):
        yield ReasoningDelta("raciocínio nativo")
        yield "<pensamento>x</pensamento> fica no texto"

    monkeypatch.setattr(ollama_client, "chat_stream", fake_stream)
    conv = conversation_store.create_conversation(title="Normal")
    events = []
    async for chunk in assistant_engine.chat_stream(
        conversation_id=conv["id"], user_message="oi", backend="ollama", enable_rag=False,
    ):
        events.append(json.loads(chunk.replace("data: ", "")))
    reasoning = [e for e in events if e["type"] == "reasoning"]
    assert [e["content"] for e in reasoning] == ["raciocínio nativo"]
    assert not reasoning[0].get("voice")
    conversation_store.delete_conversation(conv["id"])
