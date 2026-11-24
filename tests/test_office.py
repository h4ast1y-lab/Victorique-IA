"""
Documentos de escritório: ler Word, Excel, PowerPoint, CSV e PDF em partes, e
editá-los sem perder nada (o original vai para a Reserva; anexos do chat, que
ficam nos dados do app, geram uma cópia em Documentos/Victorique).
"""
import asyncio
import json
from pathlib import Path

import pytest
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

from app.claude_code import victorique_tools
from app.claude_code.permissions import PermissionBridge
from app.config import DATA_DIR, settings
from app.security.path_guard import path_guard
from app.tools import office
from app.tools.file_tools import read_file
from app.tools.organizer import RESERVE_DIR_NAME
from app.tools.registry import tool_registry


@pytest.fixture
def area(tmp_path, monkeypatch):
    root = tmp_path / "escritorio"
    root.mkdir()
    path_guard.add_authorized_directory(str(root))
    monkeypatch.setattr(office, "default_output_dir", lambda: root / "Victorique")
    yield root
    path_guard.authorized_dirs = [d for d in path_guard.authorized_dirs if d != root.resolve()]


def _docx(path: Path) -> Path:
    from docx import Document

    doc = Document()
    doc.add_heading("Relatório do caso", 1)
    par = doc.add_paragraph("O culpado é ")
    par.add_run("o mordomo").bold = True
    par.add_run(", disse ela.")
    doc.add_paragraph("Segundo parágrafo sem graça.")
    doc.add_paragraph("Terceiro parágrafo.")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Suspeito"
    table.cell(0, 1).text = "Álibi"
    table.cell(1, 0).text = "Mordomo"
    table.cell(1, 1).text = "nenhum"
    doc.save(str(path))
    return path


def _xlsx(path: Path) -> Path:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Gastos"
    ws.append(["Item", "Valor"])
    ws.append(["Chá", 12])
    ws.append(["Livros", 30])
    ws["B4"] = "=SUM(B2:B3)"
    wb.create_sheet("Notas")["A1"] = "nada"
    wb.save(str(path))
    return path


def _pptx(path: Path) -> Path:
    from pptx import Presentation

    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[1])
    slide.shapes.title.text = "Pistas"
    slide.placeholders[1].text_frame.text = "Pegadas no jardim"
    deck.slides.add_slide(deck.slide_layouts[0]).shapes.title.text = "Conclusão"
    deck.save(str(path))
    return path


def _pdf(path: Path, pages: int = 4) -> Path:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for i in range(pages):
        writer.add_blank_page(width=200 + i, height=300)
    with open(path, "wb") as fh:
        writer.write(fh)
    return path


def _reserve_copies(root: Path, name: str):
    return list((root / RESERVE_DIR_NAME).rglob(name))


# ----------------------------------------------------------------- reading
def test_word_is_read_with_numbered_paragraphs_and_tables(area):
    path = _docx(area / "caso.docx")
    result = read_file(str(path))
    text = result["content"]
    assert result["format"] == "docx"
    assert "[¶1] # Relatório do caso" in text
    assert "[¶2] O culpado é o mordomo, disse ela." in text
    assert "Suspeito | Álibi" in text and "Mordomo | nenhum" in text
    assert "¶n" in result["hint"]
    found = read_file(str(path), query="mordomo")
    assert found["matches"] >= 1 and "[Seção 1]" in found["content"]


def test_spreadsheet_shows_values_formulas_and_every_sheet(area):
    path = _xlsx(area / "gastos.xlsx")
    first = read_file(str(path), start_page=1, end_page=2)
    text = first["content"]
    assert first["total_pages"] == 2
    assert "Planilha 'Gastos'" in text and "Planilha 'Notas'" in text
    assert "| A | B" in text
    assert "Chá | 12" in text
    assert "=SUM(B2:B3)" in text           # the formula is visible for editing


def test_powerpoint_and_csv_are_read(area):
    deck = read_file(str(_pptx(area / "aula.pptx")))
    assert deck["total_pages"] == 2
    assert "Título: Pistas" in deck["content"] and "• Pegadas no jardim" in deck["content"]
    assert "--- Slide 2/2 ---" in deck["content"]

    table = area / "lista.csv"
    table.write_text("nome;idade\nAvril;15\nKazuya;15\n", encoding="utf-8")
    rows = read_file(str(table))
    assert "Avril | 15" in rows["content"] and rows["format"] == "csv"


def test_old_formats_get_a_helpful_message(area):
    old = area / "velho.doc"
    old.write_bytes(b"\xd0\xcf\x11\xe0binario")
    with pytest.raises(ValueError, match="salve como .docx"):
        read_file(str(old))


# ----------------------------------------------------------------- Word edits
def test_word_edits_keep_formatting_and_back_up_the_original(area):
    from docx import Document

    path = _docx(area / "caso.docx")
    result = office.edit_word(str(path), [
        {"op": "replace", "find": "mordomo, disse", "replace": "jardineiro, afirmou"},
        {"op": "delete_paragraph", "index": 3},
        {"op": "insert_paragraph", "after": 4, "text": "Depois do terceiro."},
        {"op": "set_paragraph", "index": 4, "text": "Terceiro, reescrito."},
        {"op": "append_heading", "text": "Anexo", "level": 2},
        {"op": "append_table", "rows": [["a", "b"], ["1", "2"]]},
    ])
    assert result["file_path"] == str(path) and len(result["changes"]) == 6
    assert _reserve_copies(area, "caso.docx"), "the original goes to the Reserva"

    doc = Document(str(path))
    texts = [p.text for p in doc.paragraphs]
    assert texts[1] == "O culpado é o jardineiro, afirmou ela."
    # the run that was bold keeps its bold
    assert any(run.bold and "jardineiro" in run.text for run in doc.paragraphs[1].runs)
    assert "Segundo parágrafo sem graça." not in texts
    assert texts.index("Terceiro, reescrito.") + 1 == texts.index("Depois do terceiro.")
    assert "Anexo" in texts and len(doc.tables) == 2


def test_word_reports_missing_text_and_bad_indices(area):
    path = _docx(area / "caso.docx")
    result = office.edit_word(str(path), [{"op": "replace", "find": "inexistente", "replace": "x"}])
    assert result["warnings"] and not result["changes"]
    with pytest.raises(ValueError, match="não existe"):
        office.edit_word(str(path), [{"op": "delete_paragraph", "index": 99}])
    with pytest.raises(ValueError, match="desconhecida"):
        office.edit_word(str(path), [{"op": "explodir"}])


# ----------------------------------------------------------------- spreadsheets
def test_spreadsheet_edits(area):
    from openpyxl import load_workbook

    path = _xlsx(area / "gastos.xlsx")
    result = office.edit_spreadsheet(str(path), [
        {"op": "set_cells", "cells": {"B3": 35, "C1": "Obs", "B5": "=B4*2"}},
        {"op": "append_rows", "sheet": "Notas", "rows": [["chá preto"], ["chá verde"]]},
        {"op": "add_sheet", "name": "Resumo", "rows": [["total", "=Gastos!B4"]]},
        {"op": "rename_sheet", "sheet": "Notas", "new_name": "Anotações"},
    ])
    assert len(result["changes"]) == 4 and result.get("backup")
    wb = load_workbook(str(path))
    assert wb.sheetnames == ["Gastos", "Anotações", "Resumo"]
    assert wb["Gastos"]["B3"].value == 35 and wb["Gastos"]["B5"].value == "=B4*2"
    assert [c.value for c in wb["Anotações"]["A"]] == ["nada", "chá preto", "chá verde"]
    assert wb["Resumo"]["B1"].value == "=Gastos!B4"
    with pytest.raises(ValueError, match="não existe"):
        office.edit_spreadsheet(str(path), [{"op": "set_cells", "sheet": "X", "cells": {"A1": 1}}])
    with pytest.raises(ValueError, match="Célula inválida"):
        office.edit_spreadsheet(str(path), [{"op": "set_cells", "cells": {"1A": 1}}])


def test_csv_edits_keep_the_delimiter(area):
    table = area / "lista.csv"
    table.write_text("nome;idade\nAvril;15\n", encoding="utf-8")
    office.edit_spreadsheet(str(table), [
        {"op": "set_cells", "cells": {"B2": "16"}},
        {"op": "append_rows", "rows": [["Kazuya", 15]]},
    ])
    assert table.read_text(encoding="utf-8-sig").splitlines() == ["nome;idade", "Avril;16", "Kazuya;15"]


# ----------------------------------------------------------------- PDF
def test_pdf_page_edits(area):
    from pypdf import PdfReader

    path = _pdf(area / "dossie.pdf", 4)
    other = _pdf(area / "anexo.pdf", 2)
    office.edit_pdf(str(path), [
        {"op": "delete_pages", "pages": "2"},
        {"op": "rotate", "pages": "1", "degrees": 90},
        {"op": "merge", "paths": [str(other)]},
        {"op": "metadata", "title": "Dossiê"},
    ])
    reader = PdfReader(str(path))
    assert len(reader.pages) == 5
    assert reader.pages[0].rotation == 90
    assert [round(float(p.mediabox.width)) for p in reader.pages[:3]] == [200, 202, 203]
    assert reader.metadata.title == "Dossiê"
    assert _reserve_copies(area, "dossie.pdf")

    out = office.edit_pdf(str(path), [{"op": "keep_pages", "pages": "3-4"}],
                          output_path=str(area / "trecho.pdf"))
    assert out["total_pages"] == 2 and len(PdfReader(str(path)).pages) == 5
    with pytest.raises(FileExistsError):
        office.edit_pdf(str(path), [{"op": "keep_pages", "pages": "1"}], output_path=str(other))
    with pytest.raises(ValueError, match="não existe"):
        office.edit_pdf(str(path), [{"op": "delete_pages", "pages": "9"}])


# ----------------------------------------------------------------- creation
def test_create_documents_from_markdown_and_rows(area):
    from docx import Document
    from openpyxl import load_workbook
    from pptx import Presentation

    office.create_document(
        str(area / "notas.docx"),
        "# Caso\nUm parágrafo com **negrito**.\n\n- pista um\n- pista dois\n\n| a | b |\n|---|---|\n| 1 | 2 |",
        title="Diário",
    )
    doc = Document(str(area / "notas.docx"))
    texts = [p.text for p in doc.paragraphs]
    assert texts[:3] == ["Diário", "Caso", "Um parágrafo com negrito."]
    assert "pista dois" in texts and len(doc.tables) == 1
    assert any(r.bold for r in doc.paragraphs[2].runs)

    office.create_document(str(area / "tabela.xlsx"), rows=[["nome", "idade"], ["Avril", "15"]])
    ws = load_workbook(str(area / "tabela.xlsx")).active
    assert ws["A2"].value == "Avril" and ws["B2"].value == 15

    office.create_document(str(area / "aula.pptx"), "# Um\n- a\n# Dois\n- b")
    assert len(Presentation(str(area / "aula.pptx")).slides) == 2

    with pytest.raises(FileExistsError):
        office.create_document(str(area / "aula.pptx"), "# x")
    with pytest.raises(ValueError, match="Não sei criar"):
        office.create_document(str(area / "x.pdf"), "oi")


def test_protected_files_are_copied_never_changed(area):
    attachments = DATA_DIR / "chat_files" / "teste-office"
    attachments.mkdir(parents=True, exist_ok=True)
    source = _docx(attachments / "anexo.docx")
    before = source.read_bytes()
    result = office.edit_word(str(source), [{"op": "append_paragraph", "text": "nova linha"}])
    assert source.read_bytes() == before
    assert Path(result["file_path"]).parent == area / "Victorique"
    assert Path(result["file_path"]).name == "anexo (editado).docx"
    assert result["original_untouched"] == str(source)
    with pytest.raises(PermissionError):
        office.edit_word(str(_docx(area / "x.docx")), [{"op": "append", "text": "x"}],
                         output_path=str(DATA_DIR / "x.docx"))


# ----------------------------------------------------------------- wiring
def test_edits_need_approval_and_reads_do_not(area, monkeypatch):
    path = _docx(area / "caso.docx")
    read = asyncio.run(tool_registry.execute_tool("read_file", {"path": str(path)}))
    assert read["status"] == "success"
    pending = asyncio.run(tool_registry.execute_tool(
        "edit_word", {"path": str(path), "operations": [{"op": "append", "text": "x"}]}))
    assert pending["status"] == "requires_authorization"
    monkeypatch.setattr(settings, "turbo_mode", True)
    done = asyncio.run(tool_registry.execute_tool(
        "edit_word", {"path": str(path), "operations": [{"op": "append", "text": "x"}]}))
    assert done["status"] == "success"


class _Recorder(PermissionBridge):
    def __init__(self):
        self.emitted = []
        super().__init__(emit=self.emitted.append, conversation_id="c1", ttl=0.2)


def test_claude_document_tools(area, monkeypatch):
    path = _docx(area / "caso.docx")
    read = asyncio.run(victorique_tools.ler_documento({"path": str(path), "query": "mordomo"}))
    assert "mordomo" in read["content"][0]["text"] and not read.get("is_error")

    failed = asyncio.run(victorique_tools.editar_word({"path": str(path), "operations": [{"op": "x"}]}))
    assert failed["is_error"] and "Nada foi alterado" in failed["content"][0]["text"]

    ok = asyncio.run(victorique_tools.editar_planilha({
        "path": str(_xlsx(area / "g.xlsx")), "operations": [{"op": "set_cells", "cells": {"A9": 1}}]}))
    assert json.loads(ok["content"][0]["text"])["status"] == "success"

    tool = "mcp__victorique__editar_word"
    assert tool not in victorique_tools.VICTORIQUE_TOOL_NAMES     # never pre-approved
    assert "mcp__victorique__ler_documento" in victorique_tools.VICTORIQUE_TOOL_NAMES

    bridge = _Recorder()
    asked = asyncio.run(bridge.can_use_tool(tool, {"path": str(path), "operations": []}, None))
    assert isinstance(asked, PermissionResultDeny) and bridge.emitted   # asked, then timed out

    denied = asyncio.run(_Recorder().can_use_tool(
        tool, {"path": str(path), "operations": [], "output_path": str(DATA_DIR / "x.docx")}, None))
    assert isinstance(denied, PermissionResultDeny)

    monkeypatch.setattr(settings, "turbo_mode", True)
    bridge = _Recorder()
    allowed = asyncio.run(bridge.can_use_tool(tool, {"path": str(path), "operations": []}, None))
    assert isinstance(allowed, PermissionResultAllow) and not bridge.emitted
