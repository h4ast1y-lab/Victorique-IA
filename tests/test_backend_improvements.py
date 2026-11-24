import io
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.rag.document_loader import document_loader
from app.rag.vector_store import _lexical_score, vector_store
from app.tools.system_tools import get_system_metrics
from app.tools.web_search import read_url, _is_safe_public_url
from app.memory.memory_store import memory_store


def test_get_system_metrics():
    metrics = get_system_metrics()
    assert "cpu" in metrics
    assert "ram" in metrics
    assert "disk_c" in metrics
    assert metrics["cpu"]["logical_cores"] >= 1
    # RAM check
    if "total_gb" in metrics["ram"]:
        assert metrics["ram"]["total_gb"] > 0
        assert 0 <= metrics["ram"]["usage_percent"] <= 100
    # Disk check
    if "total_gb" in metrics["disk_c"]:
        assert metrics["disk_c"]["total_gb"] > 0


def test_read_url_ssrf_protection():
    # Loopback / local hosts must be blocked
    assert _is_safe_public_url("http://localhost:8000") is False
    assert _is_safe_public_url("http://127.0.0.1:8765") is False
    assert _is_safe_public_url("http://192.168.1.1/admin") is False
    assert _is_safe_public_url("ftp://example.com") is False
    assert _is_safe_public_url("file:///etc/passwd") is False
    # Public URLs must be allowed
    assert _is_safe_public_url("https://www.google.com") is True
    assert _is_safe_public_url("https://pt.wikipedia.org/wiki/Python") is True


@pytest.mark.asyncio
async def test_read_url_blocked_execution():
    res = await read_url("http://127.0.0.1:8765/secret")
    assert res["status"] == "error"
    assert "não permitida" in res["error"]


def test_document_loader_new_formats(tmp_path):
    # 1. Test Structured Code / Text (.py, .json)
    py_file = tmp_path / "script.py"
    py_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")
    loaded_py = document_loader.load(str(py_file))
    assert len(loaded_py) == 1
    assert "def hello():" in loaded_py[0]["text"]

    json_file = tmp_path / "data.json"
    json_file.write_text('{"name": "assistente", "status": "active"}', encoding="utf-8")
    loaded_json = document_loader.load(str(json_file))
    assert len(loaded_json) == 1
    assert "assistente" in loaded_json[0]["text"]

    # 2. Test DOCX loading via raw zip/xml
    docx_file = tmp_path / "test.docx"
    doc_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
        <w:body>
            <w:p><w:r><w:t>Primeiro parágrafo do documento Word de teste.</w:t></w:r></w:p>
            <w:p><w:r><w:t>Segundo parágrafo importante.</w:t></w:r></w:p>
        </w:body>
    </w:document>"""
    with zipfile.ZipFile(str(docx_file), "w") as z:
        z.writestr("word/document.xml", doc_xml)
    loaded_docx = document_loader.load(str(docx_file))
    assert len(loaded_docx) == 1
    assert "Primeiro parágrafo do documento Word" in loaded_docx[0]["text"]
    assert "Segundo parágrafo importante." in loaded_docx[0]["text"]

    # 3. Test EPUB loading via raw zip/html
    epub_file = tmp_path / "test.epub"
    chapter1_html = "<html><body><h1>Capítulo 1</h1><p>Era uma vez uma IA local rodando no computador.</p></body></html>"
    chapter2_html = "<html><body><h1>Capítulo 2</h1><p>Com busca híbrida e segurança reforçada.</p></body></html>"
    with zipfile.ZipFile(str(epub_file), "w") as z:
        z.writestr("OEBPS/ch1.xhtml", chapter1_html)
        z.writestr("OEBPS/ch2.xhtml", chapter2_html)
    loaded_epub = document_loader.load(str(epub_file))
    assert len(loaded_epub) == 2
    assert "Capítulo 1" in loaded_epub[0]["text"]
    assert "IA local rodando no computador" in loaded_epub[0]["text"]
    assert "Capítulo 2" in loaded_epub[1]["text"]


def test_lexical_score_and_hybrid():
    text = "A arquitetura do assistente utiliza FastAPI no backend e Ollama para inferência."
    # Match exato
    assert _lexical_score("FastAPI no backend", text) > 0.5
    # Match de palavras
    assert _lexical_score("FastAPI Ollama", text) > 0.3
    # Nenhuma palavra
    assert _lexical_score("abacaxi melancia", text) == 0.0


def test_memory_store_semantic_filtering():
    # Cria memórias com categorias e conteúdos distintos
    m1 = memory_store.add_memory("preference", "Prefiro programar em Python e FastAPI")
    m2 = memory_store.add_memory("project", "O projeto de automação financeira usa SQLite")
    m3 = memory_store.add_memory("fact", "O computador tem placa de vídeo GTX 1660 Super")
    m4 = memory_store.add_memory("instruction", "Sempre responda de forma objetiva")

    try:
        # Quando pesquisamos por "Python", a memória sobre Python deve vir no topo
        ctx = memory_store.get_context_for_prompt(user_query="Python FastAPI backend", max_items=2)
        assert "Python" in ctx
        assert "FastAPI" in ctx
    finally:
        memory_store.delete_memory(m1["id"])
        memory_store.delete_memory(m2["id"])
        memory_store.delete_memory(m3["id"])
        memory_store.delete_memory(m4["id"])


def test_stt_upload_audio_endpoint():
    client = TestClient(app)
    # Envia um arquivo wav dummy para o endpoint
    wav_header = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    response = client.post(
        "/api/stt/upload-audio",
        files={"file": ("mic_recording.wav", io.BytesIO(wav_header), "audio/wav")}
    )
    # Deve responder 200 (com no_speech ou ok)
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


@pytest.mark.asyncio
async def test_turbo_mode_auto_authorization(monkeypatch, tmp_path):
    from app.tools.registry import tool_registry
    from app.security.path_guard import path_guard

    path_guard.add_authorized_directory(str(tmp_path))
    target = tmp_path / "turbo_file.txt"

    # Com turbo_mode = True, write_file executa imediatamente sem pending request
    monkeypatch.setattr(settings, "turbo_mode", True)
    tool = tool_registry.tools["write_file"]
    assert tool.needs_approval is False

    res = await tool_registry.execute_tool(
        "write_file",
        {"path": str(target), "content": "conteúdo gerado autonomamente no modo turbo"}
    )
    assert res["status"] == "success"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "conteúdo gerado autonomamente no modo turbo"
