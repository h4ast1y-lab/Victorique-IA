import pytest
from app.models.ollama_client import ollama_client
from app.rag.text_splitter import text_splitter
from app.rag.vector_store import vector_store

@pytest.mark.live_ollama
@pytest.mark.asyncio
async def test_ollama_connectivity():
    is_up = await ollama_client.is_alive()
    assert is_up is True

    models = await ollama_client.list_models()
    model_names = [m["name"].split(":")[0] for m in models]
    assert "qwen2.5" in model_names or "nomic-embed-text" in model_names

@pytest.mark.live_ollama
@pytest.mark.asyncio
async def test_embeddings_generation():
    vec = await ollama_client.generate_embeddings("Teste de embedding local")
    assert isinstance(vec, list)
    assert len(vec) > 0
    assert all(isinstance(x, float) for x in vec[:10])

def test_text_splitter():
    sample_pages = [
        {"page": 1, "text": "Este é o primeiro parágrafo de teste. Ele contém informações importantes sobre o sistema."},
        {"page": 2, "text": "Este é o segundo parágrafo na página dois."}
    ]
    chunks = text_splitter.split_pages(sample_pages)
    assert len(chunks) >= 2
    assert chunks[0]["page"] == 1
    assert chunks[1]["page"] == 2
