"""
Anexos do chat: imagens e documentos ficam só na conversa (data/chat_files),
nunca em Documentos; cada motor recebe o que sabe usar; apagar a conversa
apaga os anexos.
"""
import io
import json
from datetime import datetime, timedelta

import pytest
from PIL import Image

from app.claude_code import backend as claude_backend_mod
from app.claude_code.backend import build_user_content, claude_code_backend
from app.codex.backend import build_command, build_prompt
from app.config import DOCS_DIR
from app.core import attachments
from app.core.assistant import _attach_to_last_user_message
from app.memory.conversation_store import conversation_store
from app.memory.database import get_connection


def _png(size=(40, 30), color=(200, 30, 30)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _docx_bytes(text="O culpado é o mordomo.") -> bytes:
    from docx import Document

    doc = Document()
    doc.add_paragraph(text)
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _upload(client, name, data, mime="application/octet-stream"):
    return client.post("/api/chat/attachments", files={"file": (name, data, mime)})


@pytest.fixture
def fake_claude(monkeypatch):
    calls = []

    async def fake_run_turn(conversation_id, user_message, project_id, personality_id,
                            deep_thinking=False, attachments=None):
        calls.append({"conversation_id": conversation_id, "message": user_message,
                      "attachments": attachments})
        yield 'data: {"type": "done", "content": "Vi."}\n\n'

    monkeypatch.setattr(claude_code_backend, "run_turn", fake_run_turn)
    return calls


def test_images_stay_in_the_chat_not_in_documentos(client):
    docs_before = sorted(p.name for p in DOCS_DIR.iterdir())
    res = _upload(client, "pista.png", _png(), "image/png")
    assert res.status_code == 200
    meta = res.json()
    assert meta["kind"] == "image" and meta["name"] == "pista.png"
    assert meta["url"] == f"/api/chat/attachments/{meta['id']}"
    row = attachments.get(meta["id"])
    assert attachments.path_of(row).is_file()
    assert attachments.ATTACH_DIR in attachments.path_of(row).parents
    assert sorted(p.name for p in DOCS_DIR.iterdir()) == docs_before, "nothing goes to Documentos"
    assert client.get("/api/documents").json() == [] or all(
        d.get("title") != "pista.png" for d in client.get("/api/documents").json())

    image = client.get(meta["url"])
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    assert image.headers["content-disposition"].startswith("inline")
    assert image.content == attachments.path_of(row).read_bytes()


def test_bad_uploads_are_refused(client):
    assert _upload(client, "falsa.png", b"nao sou imagem", "image/png").status_code == 400
    assert _upload(client, "programa.exe", b"MZ...", "application/x-msdownload").status_code == 400
    assert _upload(client, "vazio.txt", b"", "text/plain").status_code == 400
    assert client.get("/api/chat/attachments/../../etc").status_code == 404
    assert client.get("/api/chat/attachments/" + "0" * 32).status_code == 404


def test_names_are_made_safe():
    assert attachments.safe_name("..\\..\\Windows\\win.ini") == "win.ini"
    assert attachments.safe_name("CON.png") == "_CON.png"
    assert attachments.safe_name('re:la"tó*rio?.docx') == "re_la_tó_rio_.docx"
    assert attachments.safe_name("nome. ") == "nome"


def test_message_with_only_attachments(client, fake_claude):
    image = _upload(client, "cena.png", _png(), "image/png").json()
    doc = _upload(client, "relatório.docx", _docx_bytes(),
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document").json()
    res = client.post("/api/chat", json={
        "message": "", "attachments": [image["id"], doc["id"]], "backend": "claude-code",
    })
    assert res.status_code == 200
    sent = fake_claude[-1]
    assert [a["id"] for a in sent["attachments"]] == [image["id"], doc["id"]]
    conv_id = sent["conversation_id"]
    conv = conversation_store.get_conversation(conv_id)
    assert conv["title"] == "cena.png"

    messages = client.get(f"/api/conversations/{conv_id}/messages").json()["messages"]
    user = [m for m in messages if m["role"] == "user"][0]
    assert [a["name"] for a in user["attachments"]] == ["cena.png", "relatório.docx"]
    assert "stored_name" not in user["attachments"][0], "no disk path reaches the UI"

    # Another conversation cannot reuse them.
    other = client.post("/api/chat", json={"message": "x", "attachments": [image["id"]],
                                           "backend": "claude-code"})
    assert other.status_code == 400

    # Deleting the conversation deletes the files.
    folder = attachments.ATTACH_DIR / image["id"]
    assert folder.is_dir()
    assert client.delete(f"/api/conversations/{conv_id}").status_code == 200
    assert not folder.exists() and attachments.get(image["id"]) is None


def test_empty_message_without_attachments_is_refused(client):
    assert client.post("/api/chat", json={"message": "  ", "backend": "claude-code"}).status_code == 422
    unknown = client.post("/api/chat", json={"message": "oi", "attachments": ["f" * 32]})
    assert unknown.status_code == 400


def test_unsent_upload_can_be_discarded(client, fake_claude):
    meta = _upload(client, "rascunho.png", _png(), "image/png").json()
    assert client.delete(f"/api/chat/attachments/{meta['id']}").status_code == 200
    assert attachments.get(meta["id"]) is None
    assert not (attachments.ATTACH_DIR / meta["id"]).exists()

    sent = _upload(client, "enviada.png", _png(), "image/png").json()
    client.post("/api/chat", json={"message": "veja", "attachments": [sent["id"]], "backend": "claude-code"})
    assert client.delete(f"/api/chat/attachments/{sent['id']}").status_code == 409


def test_orphans_are_cleaned_after_a_day(client):
    meta = _upload(client, "esquecida.png", _png(), "image/png").json()
    old = (datetime.now() - timedelta(hours=30)).isoformat()
    with get_connection() as conn:
        conn.execute("UPDATE chat_attachments SET created_at = ? WHERE id = ?", (old, meta["id"]))
    assert attachments.cleanup_orphans() >= 1
    assert attachments.get(meta["id"]) is None


# ----------------------------------------------------------------- per engine
def _rows(client, *uploads):
    rows = []
    for name, data, mime in uploads:
        meta = _upload(client, name, data, mime).json()
        rows.append(attachments.get(meta["id"]))
    return rows


def test_claude_gets_image_blocks_and_document_previews(client):
    big = _png(size=(3000, 1000))
    rows = _rows(client, ("foto.png", big, "image/png"),
                 ("caso.docx", _docx_bytes(), "application/octet-stream"))
    content = build_user_content("O que acha?", rows)
    assert isinstance(content, list) and content[0]["type"] == "image"
    source = content[0]["source"]
    assert source["type"] == "base64" and source["media_type"] == "image/jpeg"
    import base64
    shrunk = Image.open(io.BytesIO(base64.b64decode(source["data"])))
    assert max(shrunk.size) == attachments.MAX_IMAGE_SIDE
    text = content[-1]["text"]
    assert text.startswith("O que acha?") and "foto.png" in text
    assert "caso.docx" in text and "O culpado é o mordomo." in text
    assert str(attachments.path_of(rows[1])) in text

    only_doc = build_user_content("", rows[1:])
    assert isinstance(only_doc, str) and "O culpado é o mordomo." in only_doc
    assert build_user_content("oi", None) == "oi"


@pytest.mark.asyncio
async def test_claude_query_receives_the_blocks(client):
    rows = _rows(client, ("a.png", _png(), "image/png"))
    sent = []

    class FakeClient:
        def __init__(self, options):
            pass

        async def connect(self):
            pass

        async def query(self, prompt):
            if isinstance(prompt, str):
                sent.append(prompt)
            else:
                sent.extend([m async for m in prompt])

        async def receive_response(self):
            if False:
                yield None

        async def disconnect(self):
            pass

    backend = claude_backend_mod.ClaudeCodeBackend(FakeClient)
    conv = conversation_store.create_conversation()["id"]
    [c async for c in backend.run_turn(conv, "olha", None, None, attachments=rows)]
    message = sent[0]
    assert message["type"] == "user" and message["message"]["role"] == "user"
    kinds = [b["type"] for b in message["message"]["content"]]
    assert kinds == ["image", "text"]


def test_codex_gets_image_flags_and_the_note(client):
    rows = _rows(client, ("a.png", _png(), "image/png"))
    path = str(attachments.path_of(rows[0]))
    cmd = build_command(["codex"], "C:\\w", "thread-1", "", [path])
    assert f"--image={path}" in cmd
    assert cmd.index(f"--image={path}") < cmd.index("resume")
    assert cmd[-1] == "-"
    prompt = build_prompt("veja", None, None, [], False, resumed=True,
                          attachments_note=attachments.prompt_note(rows))
    assert prompt.rstrip().endswith(attachments.prompt_note(rows).rstrip())


def test_local_models_get_the_note_and_ollama_the_images(client):
    rows = _rows(client, ("a.png", _png(), "image/png"))
    note = attachments.history_note([attachments.public(r) for r in rows])
    messages = [{"role": "user", "content": "antes"}, {"role": "assistant", "content": "ok"},
                {"role": "user", "content": f"veja\n{note}"}]
    _attach_to_last_user_message(messages, rows, "ollama")
    assert messages[-1]["images"] and messages[0].get("images") is None
    assert messages[-1]["content"].startswith("veja") and note not in messages[-1]["content"]
    assert "a.png" in messages[-1]["content"]

    messages = [{"role": "user", "content": "veja"}]
    _attach_to_last_user_message(messages, rows, "llama-cpp-server")
    assert "images" not in messages[-1] and "não recebe imagens" in messages[-1]["content"]


def test_history_mentions_older_attachments(client, fake_claude):
    from app.core.context_builder import context_builder
    import asyncio

    meta = _upload(client, "mapa.png", _png(), "image/png").json()
    client.post("/api/chat", json={"message": "guarde", "attachments": [meta["id"]], "backend": "claude-code"})
    conv_id = fake_claude[-1]["conversation_id"]
    history = conversation_store.get_messages(conv_id)
    ctx = asyncio.run(context_builder.build_context("e agora?", history, enable_rag=False))
    user = [m for m in ctx["messages"] if m["role"] == "user"][0]
    assert "[anexos: mapa.png (imagem)]" in user["content"]

    exported = json.loads(conversation_store.export_conversation(conv_id, "json"))
    assert exported["messages"][0]["attachments"][0]["name"] == "mapa.png"
    assert "Anexos: mapa.png" in conversation_store.export_conversation(conv_id, "md")
