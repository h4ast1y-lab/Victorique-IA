from app.config import BASE_DIR, DB_PATH
from app.memory.memory_store import memory_store
from app.memory.project_store import project_store
from app.memory.conversation_store import conversation_store
from app.core.personality import personality_manager
from app.models.ollama_client import ollama_client


def _fake_embedding(*args, **kwargs):
    async def _inner(text, model=None):
        return [0.1] * 16
    return _inner


def test_memory_crud_and_toggle(client):
    r = client.post("/api/memories", json={"category": "preference", "content": "Prefiro respostas curtas."})
    assert r.status_code == 200, r.text
    mem = r.json()

    r = client.put(f"/api/memories/{mem['id']}", json={"content": "Prefiro respostas médias.", "is_active": False})
    assert r.status_code == 200
    updated = memory_store.get_memory(mem["id"])
    assert updated["content"] == "Prefiro respostas médias."
    assert updated["is_active"] == 0

    r = client.put(f"/api/memories/{mem['id']}", json={"content": updated["content"], "is_active": True})
    assert r.status_code == 200
    assert memory_store.get_memory(mem["id"])["is_active"] == 1

    r = client.delete(f"/api/memories/{mem['id']}")
    assert r.status_code == 200
    assert memory_store.get_memory(mem["id"]) is None


def test_memory_validation(client):
    r = client.post("/api/memories", json={"category": "invalida", "content": "x"})
    assert r.status_code == 400
    r = client.post("/api/memories", json={"category": "fact", "content": "   "})
    assert r.status_code == 400


def test_project_memory_scope(client):
    p = client.post("/api/projects", json={"name": "Projeto Escopo", "instructions": "seja técnico"}).json()
    m = client.post(
        "/api/memories",
        json={"category": "project", "content": "Fato do projeto", "project_id": p["id"]},
    ).json()
    assert m is not None

    ctx = memory_store.get_context_for_prompt(p["id"])
    assert "Fato do projeto" in ctx

    # Without a project, project-specific memories must not leak.
    ctx_global = memory_store.get_context_for_prompt(None)
    assert "Fato do projeto" not in ctx_global

    client.delete(f"/api/memories/{m['id']}")
    client.delete(f"/api/projects/{p['id']}")


def test_personality_default_is_updated_not_duplicated(client):
    before = [p for p in personality_manager.list_personalities() if p["is_default"]]
    assert before
    first_id = before[0]["id"]

    payload = {
        "id": first_id,
        "name": "Perfil Editado",
        "system_instructions": "Instruções editadas.",
        "tone": "tecnico",
        "formality": 4,
        "objectivity": 5,
        "detail_level": 2,
        "is_default": True,
    }
    r1 = client.post("/api/personalities", json=payload)
    r2 = client.post("/api/personalities", json=payload)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"] == first_id

    defaults = [p for p in personality_manager.list_personalities() if p["is_default"]]
    assert len(defaults) == 1

    # Restore original default profile for other tests.
    original = before[0]
    client.post("/api/personalities", json={
        "id": first_id,
        "name": original["name"],
        "system_instructions": original["system_instructions"],
        "tone": original["tone"],
        "formality": original["formality"],
        "objectivity": original["objectivity"],
        "detail_level": original["detail_level"],
        "is_default": True,
    })


def test_backup_create_list_restore(client):
    created = client.post("/api/backup", json={"label": "teste"})
    assert created.status_code == 200, created.text
    info = created.json()
    assert info["name"].endswith(".db")
    assert DB_PATH.exists()

    listed = client.get("/api/backups").json()
    assert any(b["name"] == info["name"] for b in listed)

    refused = client.post("/api/backup/restore", json={"name": info["name"], "confirm": False})
    assert refused.status_code == 400

    restored = client.post("/api/backup/restore", json={"name": info["name"], "confirm": True})
    assert restored.status_code == 200, restored.text
    assert restored.json()["pre_restore_backup"]

    bad = client.post("/api/backup/restore", json={"name": "../assistant.db", "confirm": True})
    assert bad.status_code == 400


def test_upload_index_and_delete(client, monkeypatch):
    monkeypatch.setattr(ollama_client, "generate_embeddings", _fake_embedding())

    files = {"file": ("nota-teste.txt", b"Conteudo exclusivo sobre o projeto Alfa. " * 20, "text/plain")}
    r = client.post("/api/documents/upload", files=files, data={"collection": "Geral"})
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["total_chunks"] >= 1

    docs = client.get("/api/documents").json()
    saved = [d for d in docs if d["id"] == doc["id"]][0]
    stored = saved["file_path"]

    # Uploading the same original name must create a second, distinct file.
    files2 = {"file": ("nota-teste.txt", b"Outro conteudo unico.", "text/plain")}
    r2 = client.post("/api/documents/upload", files=files2, data={"collection": "Geral"})
    assert r2.status_code == 200
    docs2 = client.get("/api/documents").json()
    assert len([d for d in docs2 if d["title"].startswith("nota-teste")]) >= 2

    from pathlib import Path
    assert Path(stored).exists()
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 200
    assert not Path(stored).exists(), "o arquivo armazenado deve ser removido com o documento"

    for d in docs2:
        client.delete(f"/api/documents/{d['id']}")


def test_upload_rejects_unsupported_extension(client):
    r = client.post(
        "/api/documents/upload",
        files={"file": ("malicioso.exe", b"MZ...", "application/octet-stream")},
    )
    assert r.status_code == 400


def test_conversation_persistence_and_search(client):
    conv = client.post("/api/conversations", json={"title": "Busca Ímpar 123"}).json()
    conversation_store.add_message(conv["id"], "user", "mensagem sobre ornitorrinco")
    found = client.get("/api/conversations/search", params={"q": "ornitorrinco"}).json()
    assert any(c["id"] == conv["id"] for c in found)
    client.delete(f"/api/conversations/{conv['id']}")


def test_documents_do_not_leak_between_projects(client, monkeypatch):
    monkeypatch.setattr(ollama_client, "generate_embeddings", _fake_embedding())

    proj = client.post("/api/projects", json={"name": "Projeto Isolado RAG"}).json()
    upload = client.post(
        "/api/documents/upload",
        files={"file": ("segredo-projeto.txt", b"Codigo interno do projeto isolado.", "text/plain")},
        data={"collection": "Geral", "project_id": proj["id"]},
    )
    assert upload.status_code == 200, upload.text

    global_docs = client.get("/api/documents").json()
    global_docs = [d for d in global_docs if d["project_id"] is None]
    assert all(d["id"] != upload.json()["id"] for d in global_docs)

    scoped = client.get("/api/documents", params={"project_id": proj["id"]}).json()
    assert [d["id"] for d in scoped] == [upload.json()["id"]]

    from app.rag.vector_store import vector_store

    # The project document must be invisible from a global (no project) search.
    import asyncio

    global_hits = asyncio.run(
        vector_store.search("codigo interno projeto isolado", project_id=None)
    )
    project_hits = asyncio.run(
        vector_store.search("codigo interno projeto isolado", project_id=proj["id"])
    )
    assert all(h["document_id"] != upload.json()["id"] for h in global_hits)
    assert any(h["document_id"] == upload.json()["id"] for h in project_hits)

    client.delete(f"/api/documents/{upload.json()['id']}")
    client.delete(f"/api/projects/{proj['id']}")


def test_conversation_scope_isolation(client):
    proj = client.post("/api/projects", json={"name": "Projeto Isolado Chat"}).json()
    scoped = client.post(
        "/api/conversations", json={"title": "Conversa do projeto", "project_id": proj["id"]}
    ).json()
    global_conv = client.post("/api/conversations", json={"title": "Conversa global"}).json()

    only_project = client.get("/api/conversations", params={"project_id": proj["id"]}).json()
    assert [c["id"] for c in only_project] == [scoped["id"]]

    # Sem filtro, a API lista tudo (compatibilidade); o isolamento visual é
    # aplicado pela interface, que só exibe o escopo atual.
    unfiltered = client.get("/api/conversations").json()
    assert any(c["id"] == scoped["id"] for c in unfiltered)
    assert any(c["id"] == global_conv["id"] for c in unfiltered)

    js = (BASE_DIR / "app" / "ui" / "js" / "app.js").read_text(encoding="utf-8")
    assert "c.project_id || null) === (currentProjectId || null)" in js

    hit_in_project = client.get(
        "/api/conversations/search", params={"q": "projeto", "project_id": proj["id"]}
    ).json()
    hit_global = client.get("/api/conversations/search", params={"q": "projeto"}).json()
    assert any(c["id"] == scoped["id"] for c in hit_in_project)
    assert all(c["id"] != scoped["id"] for c in hit_global)

    client.delete(f"/api/conversations/{scoped['id']}")
    client.delete(f"/api/conversations/{global_conv['id']}")
    client.delete(f"/api/projects/{proj['id']}")


def test_settings_model_validation(client):
    bad = client.post("/api/settings", json={"default_model": "modelo com espaço"})
    assert bad.status_code == 400
    ok = client.post("/api/settings", json={"default_model": "qwen2.5-coder:7b"})
    assert ok.status_code == 200
    assert client.get("/api/settings").json()["default_model"] == "qwen2.5-coder:7b"


def test_cases_can_be_archived_and_reopened(client):
    case = client.post("/api/projects", json={"name": "Caso do Relógio"}).json()
    assert case["archived"] == 0
    res = client.post(f"/api/projects/{case['id']}/archive", json={"archived": True})
    assert res.status_code == 200 and res.json()["status"] == "archived"
    listed = {p["id"]: p for p in client.get("/api/projects").json()}
    assert listed[case["id"]]["archived"] == 1
    client.post(f"/api/projects/{case['id']}/archive", json={"archived": False})
    listed = {p["id"]: p for p in client.get("/api/projects").json()}
    assert listed[case["id"]]["archived"] == 0
    assert client.post("/api/projects/nao-existe/archive", json={"archived": True}).status_code == 404
