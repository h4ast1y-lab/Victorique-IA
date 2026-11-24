"""Document indexing and search must work without Ollama (keyword mode).

On a machine where the AI runs only through Claude Code there is no Ollama
to produce embeddings, so the RAG falls back to keyword matching.
"""
import httpx
import pytest

from app.memory.project_store import project_store
from app.models.ollama_client import ollama_client
from app.rag import vector_store as vs_module
from app.rag.vector_store import vector_store


async def _ollama_down(text, model=None):
    raise httpx.ConnectError("Ollama offline")


async def _fake_embedding(text, model=None):
    return [1.0, 0.0, 0.0]


@pytest.fixture
def no_ollama(monkeypatch):
    monkeypatch.setattr(ollama_client, "generate_embeddings", _ollama_down)


def _case(name):
    return project_store.create_project(name)["id"]


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_index_without_ollama_stores_keyword_only_chunks(tmp_path, no_ollama):
    path = _write(tmp_path, "contrato.txt", "O contrato de aluguel vence em março de 2027.")
    info = await vector_store.index_document(str(path), project_id=_case("caso-sem-ollama-1"))
    assert info["total_chunks"] >= 1
    assert info["search_mode"] == "keyword"
    vector_store.delete_document(info["id"])


@pytest.mark.asyncio
async def test_keyword_search_ignores_accents_and_case(tmp_path, no_ollama):
    project = _case("caso-sem-ollama-2")
    path = _write(
        tmp_path,
        "notas.txt",
        "A reunião sobre o orçamento da Biblioteca ficou para sexta-feira.",
    )
    info = await vector_store.index_document(str(path), project_id=project)
    try:
        hits = await vector_store.search("reuniao do ORCAMENTO", project_id=project)
        assert hits and hits[0]["document_title"] == "notas.txt"

        assert await vector_store.search("receita de bolo de cenoura", project_id=project) == []
    finally:
        vector_store.delete_document(info["id"])


@pytest.mark.asyncio
async def test_keyword_search_ranks_the_better_match_first(tmp_path, no_ollama):
    project = _case("caso-sem-ollama-3")
    a = await vector_store.index_document(
        str(_write(tmp_path, "a.txt", "Gatos dormem muito. O jardim tem flores.")), project_id=project
    )
    b = await vector_store.index_document(
        str(_write(tmp_path, "b.txt", "Gatos pretos e gatos brancos dormem no jardim.")), project_id=project
    )
    try:
        hits = await vector_store.search("gatos no jardim", project_id=project)
        assert [h["document_title"] for h in hits][:2] == ["b.txt", "a.txt"]
    finally:
        vector_store.delete_document(a["id"])
        vector_store.delete_document(b["id"])


@pytest.mark.asyncio
async def test_embedded_documents_stay_searchable_when_ollama_goes_away(tmp_path, monkeypatch):
    project = _case("caso-sem-ollama-4")
    monkeypatch.setattr(ollama_client, "generate_embeddings", _fake_embedding)
    info = await vector_store.index_document(
        str(_write(tmp_path, "c.txt", "O relatório trimestral mostra lucro.")), project_id=project
    )
    assert info["search_mode"] == "semantic"
    monkeypatch.setattr(ollama_client, "generate_embeddings", _ollama_down)
    try:
        hits = await vector_store.search("relatorio trimestral", project_id=project)
        assert hits and hits[0]["document_title"] == "c.txt"
    finally:
        vector_store.delete_document(info["id"])


def test_stopwords_alone_do_not_match():
    assert vs_module._keyword_score("o que é isso para", "o que é isso para você") == 0.0
