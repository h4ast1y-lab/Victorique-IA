"""Regressions for the project-wide review: connections between the modules."""
import asyncio
import json
import sqlite3

import httpx
import pytest
from claude_agent_sdk import ResultMessage, StreamEvent

from app.claude_code import backend as claude_backend
from app.codex import backend as codex_backend
from app.core import preferences
from app.core.avatar_protocol import AvatarControlParser
from app.core.transcript import recent_transcript
from app.life import generator
from app.memory import database
from app.memory.conversation_store import conversation_store
from app.memory.memory_store import memory_store
from app.memory.project_store import project_store
from app.models.ollama_client import ollama_client
from app.rag.vector_store import vector_store
from app.tools import file_tools, web_search


# ----------------- database -----------------
def test_with_block_closes_the_connection():
    with database.get_connection() as conn:
        conn.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_renamed_conversation_keeps_the_same_timestamp_format():
    conv = conversation_store.create_conversation(title="antes")
    conversation_store.update_title(conv["id"], "depois")
    updated = conversation_store.get_conversation(conv["id"])["updated_at"]
    assert "T" in updated  # local ISO like create/add_message, not CURRENT_TIMESTAMP
    conversation_store.delete_conversation(conv["id"])


def test_project_updates_keep_the_same_timestamp_format():
    project = project_store.create_project("caso-formato")
    project_store.update_project(project["id"], name="caso-formato-2")
    project_store.set_archived(project["id"], True)
    assert "T" in project_store.get_project(project["id"])["updated_at"]
    project_store.delete_project(project["id"])


def test_export_has_the_whole_conversation():
    conv = conversation_store.create_conversation(title="longa")
    for i in range(130):
        conversation_store.add_message(conv["id"], "user", f"mensagem {i}")
    exported = json.loads(conversation_store.export_conversation(conv["id"], "json"))
    assert len(exported["messages"]) == 130
    assert exported["messages"][0]["content"] == "mensagem 0"
    conversation_store.delete_conversation(conv["id"])


def test_search_treats_percent_and_underscore_as_text():
    a = conversation_store.create_conversation(title="desconto de 50% hoje")
    b = conversation_store.create_conversation(title="desconto de 500 reais")
    c = conversation_store.create_conversation(title="arquivo zq_wy.txt")
    d = conversation_store.create_conversation(title="arquivo zqxwy.txt")
    try:
        found = {x["id"] for x in conversation_store.search_conversations("50%")}
        assert a["id"] in found and b["id"] not in found
        found = {x["id"] for x in conversation_store.search_conversations("zq_wy")}
        assert c["id"] in found and d["id"] not in found
    finally:
        for conv in (a, b, c, d):
            conversation_store.delete_conversation(conv["id"])


def test_saved_backend_is_shared(client):
    before = client.get("/api/settings").json()["default_backend"]
    try:
        client.post("/api/settings", json={"default_backend": "codex"})
        assert database.saved_backend() == "codex"
    finally:
        client.post("/api/settings", json={"default_backend": before})


# ----------------- preferences -----------------
def test_preferences_are_cached_and_updates_refresh_the_cache():
    preferences.invalidate_cache()
    first = preferences.load()
    first["user_name"] = "mutated by caller"
    assert preferences.load()["user_name"] != "mutated by caller"  # a copy each time
    before = preferences.load()["idle_minutes"]
    try:
        preferences.update({"idle_minutes": 7})
        assert preferences.load()["idle_minutes"] == 7
    finally:
        preferences.update({"idle_minutes": before})


def test_user_name_line_is_neutral():
    prefs = preferences.defaults()
    prefs["user_name"] = "Ana"
    line = preferences.prompt_lines(prefs)[0]
    assert "Chame-o" not in line and "Ana" in line


# ----------------- memories -----------------
def test_standing_memories_survive_the_limit():
    rule = memory_store.add_memory("instruction", "Nunca use emojis nas respostas.")
    facts = [memory_store.add_memory("fact", f"Fato número {i} sem relação") for i in range(12)]
    try:
        ctx = memory_store.get_context_for_prompt(user_query="fato número", max_items=3)
        assert "Nunca use emojis" in ctx
    finally:
        memory_store.delete_memory(rule["id"])
        for fact in facts:
            memory_store.delete_memory(fact["id"])


# ----------------- Claude Code / Codex -----------------
def test_claude_append_prompt_carries_saved_memories():
    mem = memory_store.add_memory("preference", "Prefere respostas curtas e diretas.")
    try:
        assert "Prefere respostas curtas" in claude_backend.build_append_prompt(None, None)
    finally:
        memory_store.delete_memory(mem["id"])


def test_codex_instructions_carry_saved_memories():
    mem = memory_store.add_memory("preference", "Gosta de tabelas em Markdown.")
    try:
        text = codex_backend._instructions(None, None, [], False, "tabela")
        assert "Gosta de tabelas" in text
    finally:
        memory_store.delete_memory(mem["id"])


def test_transcript_skips_the_message_being_sent():
    history = [
        {"role": "user", "content": "primeira"},
        {"role": "assistant", "content": "resposta"},
        {"role": "user", "content": "agora"},
    ]
    text = recent_transcript(history, "agora")
    assert "primeira" in text and "resposta" in text and "agora" not in text


def test_with_transcript_wraps_text_and_image_prompts():
    assert claude_backend.with_transcript("oi", "") == "oi"
    wrapped = claude_backend.with_transcript("oi", "Usuário: antes")
    assert "<conversa_ate_aqui>" in wrapped and wrapped.endswith("oi")
    blocks = [{"type": "image", "source": {}}, {"type": "text", "text": "veja"}]
    out = claude_backend.with_transcript(blocks, "Usuário: antes")
    assert out[0]["type"] == "image" and "Usuário: antes" in out[1]["text"]
    assert blocks[1]["text"] == "veja"  # the original list is left alone


class _Client:
    def __init__(self, options, log):
        self.options = options
        self.log = log

    async def connect(self, prompt=None):
        pass

    async def query(self, prompt, session_id="default"):
        self.log.append(prompt)

    async def receive_response(self):
        yield StreamEvent(uuid="u", session_id="s", event={
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "text_delta", "text": "ok"},
        })
        yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1,
                            is_error=False, num_turns=1, session_id="s-new", result=None)

    async def interrupt(self):
        pass

    async def disconnect(self):
        pass


@pytest.mark.asyncio
async def test_new_claude_session_sees_the_conversation_so_far():
    """First Claude turn after chatting in another mode: no longer blind."""
    conv = conversation_store.create_conversation()["id"]
    conversation_store.add_message(conv, "user", "Meu gato se chama Bartolomeu.")
    conversation_store.add_message(conv, "assistant", "Anotado.")
    conversation_store.add_message(conv, "user", "Qual o nome do gato?")
    prompts = []
    backend = claude_backend.ClaudeCodeBackend(lambda options: _Client(options, prompts))
    async for _ in backend.run_turn(conv, "Qual o nome do gato?", None, None):
        pass
    assert "Bartolomeu" in prompts[0] and prompts[0].endswith("Qual o nome do gato?")
    # The next turn resumes the session: the plain message is enough.
    async for _ in backend.run_turn(conv, "Obrigado", None, None):
        pass
    assert prompts[1] == "Obrigado"
    conversation_store.delete_conversation(conv)


# ----------------- avatar markers -----------------
@pytest.mark.parametrize("chunks", [
    ["\n[expression:happy]\nOlá"],
    [" ", "\n", "[expr", "ession:happy]\n", "Olá"],
    ["\r\n\r\n[expression:happy]", "\nOlá"],
])
def test_marker_after_leading_blank_lines_does_not_leak(chunks):
    parser = AvatarControlParser()
    controls, visible = [], []
    for chunk in chunks:
        c, v = parser.feed(chunk)
        controls += c
        visible += v
    c, v = parser.finish()
    assert controls + c == [{"type": "avatar", "expression": "happy"}]
    assert "".join(visible + v) == "Olá"


def test_leading_whitespace_before_prose_is_kept():
    parser = AvatarControlParser()
    _, visible = parser.feed("  texto normal")
    _, rest = parser.finish()
    assert "".join(visible + rest) == "  texto normal"


# ----------------- web (SSRF) -----------------
@pytest.mark.parametrize("url", [
    "http://172.16.0.5/", "http://[::1]/", "http://[fd00::1]/", "http://100.64.1.1/",
    "http://0.0.0.0/", "http://printer.local/", "http://user:pw@example.com/",
    "http://[::ffff:127.0.0.1]/",
])
def test_internal_urls_are_refused(url):
    assert web_search._is_safe_public_url(url) is False


def test_names_that_resolve_inside_are_refused():
    assert web_search._host_is_public("localhost") is False
    assert web_search._host_is_public("2130706433") is False  # 127.0.0.1 in decimal


@pytest.mark.asyncio
async def test_redirect_to_the_app_itself_is_blocked(monkeypatch):
    def handler(request):
        return httpx.Response(302, headers={"location": "http://127.0.0.1:8765/api/backups"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(web_search, "_host_is_public", lambda host: host == "public.example")
    monkeypatch.setattr(web_search.httpx, "AsyncClient",
                        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    result = await web_search.read_url("http://public.example/")
    assert result["status"] == "error" and "redirecionou" in result["error"]


# ----------------- RAG without Ollama -----------------
@pytest.mark.asyncio
async def test_search_with_nothing_indexed_does_not_call_ollama(monkeypatch):
    async def never(*args, **kwargs):
        raise AssertionError("embedding requested with no document to compare")

    monkeypatch.setattr(ollama_client, "generate_embeddings", never)
    project = project_store.create_project("caso-sem-documentos")
    try:
        assert await vector_store.search("qualquer coisa", project_id=project["id"]) == []
    finally:
        project_store.delete_project(project["id"])


def test_failed_connection_is_remembered_for_a_while(monkeypatch):
    client = type(ollama_client)("http://127.0.0.1:9")  # nothing listens on port 9
    assert asyncio.run(client.is_alive()) is False
    assert client.recently_down()
    with pytest.raises(httpx.ConnectError):
        asyncio.run(client.generate_embeddings("x"))


# ----------------- file search -----------------
def test_search_files_skips_protected_folders(tmp_path, monkeypatch):
    from app.security.path_guard import path_guard
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep" / "a.txt").write_text("x", encoding="utf-8")
    (tmp_path / "secret").mkdir()
    (tmp_path / "secret" / "b.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(path_guard, "authorized_dirs", [tmp_path.resolve()])
    original = path_guard.is_protected
    monkeypatch.setattr(path_guard, "is_protected",
                        lambda p: "secret" in str(p) or original(p))
    found = file_tools.search_files(str(tmp_path), "*.txt")
    names = [r["name"] for r in found["results"]]
    assert names == ["a.txt"] and not found.get("truncated")


def test_search_files_stops_at_the_entry_budget(tmp_path, monkeypatch):
    from app.security.path_guard import path_guard
    for i in range(30):
        (tmp_path / f"f{i}.log").write_text("x", encoding="utf-8")
    monkeypatch.setattr(path_guard, "authorized_dirs", [tmp_path.resolve()])
    monkeypatch.setattr(file_tools, "SEARCH_MAX_ENTRIES", 5)
    found = file_tools.search_files(str(tmp_path), "*.pdf")
    assert found["truncated"] is True and found["results"] == []


# ----------------- API -----------------
def test_health_does_not_probe_ollama_outside_ollama_mode(client, monkeypatch):
    async def never():
        raise AssertionError("Ollama probed in Claude Code mode")

    monkeypatch.setattr(ollama_client, "get_version", never)
    monkeypatch.setattr(ollama_client, "is_alive", never)
    monkeypatch.setattr(ollama_client, "list_models", never)
    before = client.get("/api/settings").json()["default_backend"]
    client.post("/api/settings", json={"default_backend": "claude-code"})
    try:
        body = client.get("/api/health").json()
    finally:
        client.post("/api/settings", json={"default_backend": before})
    assert body["active_backend"] == "claude-code" and body["ollama_online"] is None


def test_chat_rejects_an_unknown_mode(client):
    response = client.post("/api/chat", json={"message": "oi", "backend": "gpt-99"})
    assert response.status_code == 400


def test_llama_cpp_load_no_longer_crashes(client, monkeypatch):
    from app.models.llama_cpp_client import llama_cpp_client
    monkeypatch.setattr(llama_cpp_client, "load_model", lambda path, n_ctx=None: True)
    response = client.post("/api/llama-cpp/load", json={"model_path": "C:/modelo.gguf"})
    assert response.status_code == 200 and response.json()["status"] == "loaded"


def test_stt_transcribe_refuses_files_outside_authorized_folders(client, monkeypatch):
    from app.voice import stt_engine
    monkeypatch.setattr(type(stt_engine), "available", property(lambda self: True))
    response = client.post("/api/stt/transcribe", json={"file_path": "C:/Windows/win.ini"})
    assert response.status_code == 403


def test_blank_case_name_is_refused_on_update(client):
    project = client.post("/api/projects", json={"name": "  Caso X  "}).json()
    try:
        assert project["name"] == "Caso X"
        response = client.put(f"/api/projects/{project['id']}", json={"name": "   "})
        assert response.status_code == 400
    finally:
        client.delete(f"/api/projects/{project['id']}")


# ----------------- vida própria -----------------
def test_codex_mode_lines_come_from_the_bank():
    with pytest.raises(RuntimeError):
        asyncio.run(generator.ask_model("s", "u", "codex"))
