"""Ferramentas que o Claude Code usa para ler memórias e documentos da Victorique."""
import httpx
import pytest

from app.claude_code import victorique_tools
from app.claude_code.victorique_tools import (
    VICTORIQUE_TOOL_NAMES,
    buscar_documentos,
    buscar_memorias,
    create_victorique_server,
)
from app.memory.memory_store import memory_store
from app.memory.project_store import project_store


def _text(result):
    return "\n".join(part["text"] for part in result["content"])


@pytest.mark.asyncio
async def test_buscar_memorias_returns_active_memories():
    memory_store.add_memory("preference", "Prefiro relatórios em PDF")
    result = await buscar_memorias({"consulta": "relatórios"}, None)
    assert "Prefiro relatórios em PDF" in _text(result)


@pytest.mark.asyncio
async def test_buscar_memorias_respects_project():
    a = project_store.create_project("Projeto A")
    b = project_store.create_project("Projeto B")
    memory_store.add_memory("fact", "Segredo exclusivo do projeto B", project_id=b["id"])
    result = await buscar_memorias({"consulta": "segredo"}, a["id"])
    assert "Segredo exclusivo do projeto B" not in _text(result)


@pytest.mark.asyncio
async def test_buscar_documentos_offline_returns_notice(monkeypatch):
    async def offline(**kwargs):
        raise httpx.ConnectError("sem conexão")

    monkeypatch.setattr(victorique_tools.vector_store, "search", offline)
    result = await buscar_documentos({"consulta": "contrato"}, None)
    assert "indisponível" in _text(result)


@pytest.mark.asyncio
async def test_buscar_documentos_cites_title_and_page(monkeypatch):
    async def fake_search(**kwargs):
        return [{
            "document_title": "Contrato de Aluguel",
            "page": 3,
            "content": "O reajuste é anual.",
            "score": 0.9,
        }]

    monkeypatch.setattr(victorique_tools.vector_store, "search", fake_search)
    text = _text(await buscar_documentos({"consulta": "reajuste"}, None))
    assert "Contrato de Aluguel" in text
    assert "página 3" in text
    assert "O reajuste é anual." in text


def test_server_exposes_two_tools():
    server = create_victorique_server(None)
    assert server["name"] == "victorique"
    assert VICTORIQUE_TOOL_NAMES == [
        "mcp__victorique__buscar_memorias",
        "mcp__victorique__buscar_documentos",
    ]
