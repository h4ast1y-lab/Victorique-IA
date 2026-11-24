import pytest
from PIL import Image, ImageDraw, ImageFont

from app.config import settings
from app.models.ollama_client import ollama_client
from app.rag.document_loader import document_loader, ocr_engine


def _scanned_pdf(path, lines=("PROJETO ALFA", "CODIGO ORNITORRINCO 42")):
    image = Image.new("RGB", (1200, 420), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 56)
    except Exception:  # pragma: no cover - depends on fonts
        font = ImageFont.load_default()
    y = 60
    for line in lines:
        draw.text((50, y), line, fill="black", font=font)
        y += 110
    image.save(path, "PDF", resolution=150.0)
    return path


async def _fake_embedding(text, model=None):
    return [0.1] * 16


def test_ocr_is_available_on_this_machine():
    status = ocr_engine.status()
    if not status["available"]:
        pytest.skip("Tesseract/OCR não instalado")
    assert status["languages"]
    lang = ocr_engine.resolve_language("por+eng")
    available = set(status["languages"])
    assert set(lang.split("+")) <= available
    assert lang


def test_scanned_pdf_text_is_extracted_by_ocr(tmp_path):
    if not ocr_engine.status()["available"]:
        pytest.skip("Tesseract/OCR não instalado")
    pdf = _scanned_pdf(tmp_path / "digitalizado.pdf")
    pages = document_loader.load(str(pdf))
    text = "\n".join(p["text"] for p in pages).upper()
    assert "ORNITORRINCO" in text
    assert "42" in text
    assert document_loader.last_ocr["pages"] == [1]
    assert document_loader.last_ocr["error"] is None


def test_ocr_can_be_disabled(tmp_path, monkeypatch):
    pdf = _scanned_pdf(tmp_path / "desativado.pdf")
    monkeypatch.setattr(settings, "ocr_enabled", False)
    with pytest.raises(ValueError, match="desativado"):
        document_loader.load(str(pdf))


def test_txt_document_does_not_run_ocr(tmp_path):
    txt = tmp_path / "texto.txt"
    txt.write_text("Conteúdo de texto normal.", encoding="utf-8")
    pages = document_loader.load(str(txt))
    assert pages[0]["text"] == "Conteúdo de texto normal."
    assert document_loader.last_ocr["pages"] == []


def test_upload_scanned_pdf_indexes_ocr_text(client, tmp_path, monkeypatch):
    if not ocr_engine.status()["available"]:
        pytest.skip("Tesseract/OCR não instalado")
    monkeypatch.setattr(ollama_client, "generate_embeddings", _fake_embedding)
    pdf = _scanned_pdf(tmp_path / "digitalizado-upload.pdf")

    response = client.post(
        "/api/documents/upload",
        files={"file": ("digitalizado-upload.pdf", pdf.read_bytes(), "application/pdf")},
        data={"collection": "Geral"},
    )
    assert response.status_code == 200, response.text
    document = response.json()
    assert document["total_chunks"] >= 1
    assert document["ocr"]["pages"] == [1]

    docs = client.get("/api/documents").json()
    assert any(d["id"] == document["id"] for d in docs)

    client.delete(f"/api/documents/{document['id']}")
