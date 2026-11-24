"""
Documentos de escritório: ler e editar Word, Excel, PowerPoint, PDF e CSV.

Leitura (livre): ``document_pages`` devolve o documento em "páginas" — seções
do Word, planilhas do Excel (fatiadas em blocos de linhas), slides do
PowerPoint, blocos de linhas do CSV — para o ``read_file`` paginar e buscar.

Edição (sempre com aprovação, exceto no modo turbo): ``edit_word``,
``edit_spreadsheet``, ``edit_pdf`` e ``create_document``.

Segurança:
  * todo caminho passa pelo path_guard (ler: pasta autorizada; escrever: fora
    das pastas protegidas e do sistema);
  * editar um arquivo no lugar guarda antes uma cópia do original na Reserva
    (``_Quarentena/<carimbo>/...``), então nada se perde;
  * arquivos em pastas protegidas (ex.: anexos do chat, que ficam nos dados do
    app) nunca são alterados: a versão editada vai para ``Documentos/Victorique``;
  * a gravação é atômica (arquivo temporário + troca), sem arquivo pela metade.
"""
from __future__ import annotations

import csv
import io
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from app.security.path_guard import ensure_not_hardlinked, path_guard

Pages = List[Tuple[int, str]]

WORD_EXTS = {".docx"}
SHEET_EXTS = {".xlsx", ".xlsm"}
OLD_SHEET_EXTS = {".xls"}
TABLE_EXTS = {".csv", ".tsv"}
SLIDE_EXTS = {".pptx"}
PDF_EXTS = {".pdf"}
OFFICE_READ_EXTS = WORD_EXTS | SHEET_EXTS | OLD_SHEET_EXTS | TABLE_EXTS | SLIDE_EXTS
CREATE_EXTS = {".docx", ".xlsx", ".csv", ".pptx", ".md", ".txt"}
UNSUPPORTED_HINTS = {
    ".doc": "Formato .doc antigo (Word 97-2003): abra no Word e salve como .docx para eu ler e editar.",
    ".ppt": "Formato .ppt antigo: salve como .pptx para eu ler e editar.",
    ".odt": "Arquivo do LibreOffice (.odt): salve como .docx para eu ler e editar.",
    ".ods": "Planilha do LibreOffice (.ods): salve como .xlsx para eu ler e editar.",
    ".odp": "Apresentação do LibreOffice (.odp): salve como .pptx para eu ler e editar.",
}

MAX_EDIT_BYTES = 50 * 1024 * 1024
ROWS_PER_PAGE = 150          # linhas de planilha/CSV por "página"
WORD_SECTION_CHARS = 3500    # uma seção do Word quebra perto deste tamanho
MAX_CELL_CHARS = 200
MAX_OPERATIONS = 200
EDITED_SUFFIX = " (editado)"


def _unit_for(ext: str) -> str:
    if ext in SHEET_EXTS | OLD_SHEET_EXTS:
        return "Planilha"
    if ext in SLIDE_EXTS:
        return "Slide"
    if ext in TABLE_EXTS:
        return "Bloco"
    return "Seção"


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, datetime):
        value = value.strftime("%Y-%m-%d %H:%M") if (value.hour or value.minute) else value.strftime("%Y-%m-%d")
    text = str(value).replace("\r", " ").replace("\n", " ⏎ ").replace("|", "¦")
    return text if len(text) <= MAX_CELL_CHARS else text[: MAX_CELL_CHARS - 1] + "…"


def _column_letter(index: int) -> str:
    """1 -> A, 27 -> AA."""
    letters = ""
    while index > 0:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


# ===================================================================== reading
def _grid_pages(title: str, rows: Sequence[Tuple[int, Sequence[str]]], dims: str) -> List[str]:
    """Rows (number, cells) as compact tables, ROWS_PER_PAGE rows per page."""
    rows = [(n, list(cells)) for n, cells in rows if any(c for c in cells)]
    if not rows:
        return [f"{title} ({dims}): vazia."]
    width = max(len(cells) for _, cells in rows)
    header = "    | " + " | ".join(_column_letter(i + 1) for i in range(width))
    pages = []
    for start in range(0, len(rows), ROWS_PER_PAGE):
        chunk = rows[start: start + ROWS_PER_PAGE]
        first, last = chunk[0][0], chunk[-1][0]
        lines = [f"{title} ({dims}) — linhas {first}-{last}", header]
        for number, cells in chunk:
            cells = cells + [""] * (width - len(cells))
            lines.append(f"{number:>3} | " + " | ".join(cells))
        pages.append("\n".join(lines))
    return pages


def _trim(cells: List[str]) -> List[str]:
    while cells and not cells[-1]:
        cells.pop()
    return cells


def _xlsx_pages(path: Path) -> List[str]:
    from openpyxl import load_workbook

    values = load_workbook(str(path), read_only=True, data_only=True)
    formulas = load_workbook(str(path), read_only=True, data_only=False)
    try:
        pages: List[str] = []
        for ws_v in values.worksheets:
            ws_f = formulas[ws_v.title]
            rows: List[Tuple[int, List[str]]] = []
            for number, (row_v, row_f) in enumerate(
                zip(ws_v.iter_rows(values_only=True), ws_f.iter_rows(values_only=True)), 1
            ):
                cells = []
                for v, f in zip(row_v, row_f):
                    text = _cell_text(v)
                    if isinstance(f, str) and f.startswith("="):
                        text = f"{text} ({_cell_text(f)})" if text else _cell_text(f)
                    cells.append(text)
                rows.append((number, _trim(cells)))
            dims = ws_v.calculate_dimension() if hasattr(ws_v, "calculate_dimension") else ""
            pages.extend(_grid_pages(f"Planilha '{ws_v.title}'", rows, dims or "sem dados"))
        return pages
    finally:
        values.close()
        formulas.close()


def _xls_pages(path: Path) -> List[str]:
    import xlrd

    book = xlrd.open_workbook(str(path), on_demand=True)
    try:
        pages: List[str] = []
        for sheet in book.sheets():
            rows = []
            for r in range(sheet.nrows):
                cells = []
                for c in range(sheet.ncols):
                    cell = sheet.cell(r, c)
                    value = cell.value
                    if cell.ctype == xlrd.XL_CELL_DATE:
                        try:
                            value = xlrd.xldate.xldate_as_datetime(value, book.datemode)
                        except Exception:
                            pass
                    cells.append(_cell_text(value))
                rows.append((r + 1, _trim(cells)))
            dims = f"{sheet.nrows} linhas × {sheet.ncols} colunas"
            pages.extend(_grid_pages(f"Planilha '{sheet.name}'", rows, dims))
        return pages
    finally:
        book.release_resources()


def _sniff_dialect(sample: str, ext: str):
    if ext == ".tsv":
        return "excel-tab"
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return "excel"


def _read_text_any(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _csv_rows(path: Path) -> Tuple[List[List[str]], Any]:
    text = _read_text_any(path)
    dialect = _sniff_dialect(text[:20000], path.suffix.lower())
    return [list(r) for r in csv.reader(io.StringIO(text), dialect)], dialect


def _csv_pages(path: Path) -> List[str]:
    rows, _ = _csv_rows(path)
    numbered = [(i, _trim([_cell_text(c) for c in row])) for i, row in enumerate(rows, 1)]
    width = max((len(r) for r in rows), default=0)
    return _grid_pages(f"Tabela '{path.name}'", numbered, f"{len(rows)} linhas × {width} colunas")


def _pptx_pages(path: Path) -> List[str]:
    from pptx import Presentation

    deck = Presentation(str(path))
    pages = []
    for number, slide in enumerate(deck.slides, 1):
        lines = [f"Slide {number}"]
        title = slide.shapes.title
        if title is not None and title.has_text_frame and title.text_frame.text.strip():
            lines.append(f"Título: {title.text_frame.text.strip()}")
        for shape in slide.shapes:
            if title is not None and shape.shape_id == title.shape_id:
                continue
            if shape.has_text_frame:
                for par in shape.text_frame.paragraphs:
                    text = "".join(run.text for run in par.runs).strip()
                    if text:
                        lines.append("  " * par.level + f"• {text}")
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    lines.append(" | ".join(_cell_text(cell.text) for cell in row.cells))
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                lines.append(f"Notas: {notes}")
        pages.append("\n".join(lines))
    return pages


def _word_blocks(doc) -> List[Tuple[str, str, bool]]:
    """(label, text, starts_section) for every body paragraph and table, in order."""
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    blocks = []
    p_index = 0
    t_index = 0
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            par = Paragraph(child, doc)
            p_index += 1
            text = par.text.strip()
            if not text:
                continue
            style = (par.style.name if par.style is not None else "") or ""
            heading = style.lower().startswith(("heading", "título", "titulo", "title"))
            prefix = "# " if heading else ""
            blocks.append((f"¶{p_index}", f"{prefix}{text}", heading))
        elif tag == "tbl":
            t_index += 1
            table = Table(child, doc)
            rows = []
            for row in table.rows:
                rows.append(" | ".join(_cell_text(cell.text) for cell in row.cells))
            blocks.append((f"Tabela {t_index}", "\n".join(rows), False))
    return blocks


def _docx_pages(path: Path) -> List[str]:
    from docx import Document

    doc = Document(str(path))
    pages: List[str] = []
    current: List[str] = []
    size = 0
    for label, text, heading in _word_blocks(doc):
        if current and (heading or size > WORD_SECTION_CHARS):
            pages.append("\n".join(current))
            current, size = [], 0
        line = f"[{label}] {text}"
        current.append(line)
        size += len(line)
    if current:
        pages.append("\n".join(current))
    sections = []
    for section in doc.sections[:1]:
        for part, label in ((section.header, "Cabeçalho"), (section.footer, "Rodapé")):
            try:
                text = "\n".join(p.text for p in part.paragraphs if p.text.strip())
            except Exception:
                text = ""
            if text:
                sections.append(f"{label}: {text}")
    if sections and pages:
        pages[0] = "\n".join(sections) + "\n" + pages[0]
    return pages


def document_pages(path: Path) -> Tuple[Pages, str]:
    """The office document as numbered pages, plus the unit name (Seção, Slide...)."""
    ext = path.suffix.lower()
    if ext in WORD_EXTS:
        texts = _docx_pages(path)
    elif ext in SHEET_EXTS:
        texts = _xlsx_pages(path)
    elif ext in OLD_SHEET_EXTS:
        texts = _xls_pages(path)
    elif ext in TABLE_EXTS:
        texts = _csv_pages(path)
    elif ext in SLIDE_EXTS:
        texts = _pptx_pages(path)
    else:
        raise ValueError(UNSUPPORTED_HINTS.get(ext, f"Formato '{ext}' não é um documento de escritório."))
    return [(i, t) for i, t in enumerate(texts, 1)], _unit_for(ext)


def unsupported_hint(ext: str) -> Optional[str]:
    return UNSUPPORTED_HINTS.get(ext.lower())


# ===================================================================== writing
def default_output_dir() -> Path:
    return Path.home() / "Documents" / "Victorique"


def _stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    for n in range(2, 1000):
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Não achei um nome livre para '{path.name}'.")


def _source(path: str, exts: set) -> Path:
    resolved = path_guard.validate_and_resolve(path, must_exist=True)
    if not resolved.is_file():
        raise IsADirectoryError(f"'{path}' não é um arquivo.")
    ext = resolved.suffix.lower()
    if ext not in exts:
        hint = UNSUPPORTED_HINTS.get(ext)
        raise ValueError(hint or f"Formato '{ext}' não suportado aqui. Aceitos: {', '.join(sorted(exts))}.")
    if resolved.stat().st_size > MAX_EDIT_BYTES:
        raise ValueError(f"Arquivo grande demais para editar (limite {MAX_EDIT_BYTES // (1024 * 1024)} MB).")
    return resolved


def _plan_output(src: Path, output_path: Optional[str], suffix: Optional[str] = None) -> Path:
    """Where the edited version goes: output_path, a copy (protected source) or src itself."""
    suffix = suffix or src.suffix
    if output_path:
        out = path_guard.validate_and_resolve(output_path, for_write=True)
        if out.suffix.lower() != suffix.lower():
            out = out.with_suffix(suffix)
            out = path_guard.validate_and_resolve(str(out), for_write=True)
        if out.exists() and out != src:
            raise FileExistsError(
                f"'{out}' já existe. Escolha outro output_path (nunca sobrescrevo outro arquivo)."
            )
        return out
    if path_guard.is_protected(str(src)):
        folder = default_output_dir()
        return _unique(folder / f"{src.stem}{EDITED_SUFFIX}{suffix}")
    if suffix.lower() != src.suffix.lower():
        return _unique(src.with_suffix(suffix))
    return src


def _backup(path: Path) -> Optional[str]:
    """Copies the original into the Reserva before it is replaced."""
    if not path.exists():
        return None
    from app.tools import organizer

    root = organizer.reserve_root_for(path)
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = Path(path.name)
    dest = root / organizer.RESERVE_DIR_NAME / _stamp() / relative
    dest = _unique(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(path), str(dest))
    return str(dest)


def _save(out: Path, writer: Callable[[Path], None]) -> Optional[str]:
    """Atomic save: temp file in the same folder, then replace. Backs up an existing out."""
    out = path_guard.validate_and_resolve(str(out), for_write=True)
    if out.exists():
        if out.is_dir():
            raise IsADirectoryError(f"'{out}' é uma pasta.")
        ensure_not_hardlinked(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    path_guard.validate_and_resolve(str(out.parent), for_write=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".victorique-", suffix=out.suffix, dir=str(out.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        writer(tmp)
        backup = _backup(out)
        os.replace(str(tmp), str(out))
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return backup


def _result(src: Optional[Path], out: Path, backup: Optional[str], done: List[str],
            warnings: Optional[List[str]] = None) -> Dict[str, Any]:
    result: Dict[str, Any] = {"status": "success", "file_path": str(out), "changes": done}
    if src is not None and src != out:
        result["original_untouched"] = str(src)
    if backup:
        result["backup"] = backup
        result["note"] = "O original foi copiado para a Reserva antes da edição."
    if warnings:
        result["warnings"] = warnings
    return result


def _operations(operations: Any) -> List[Dict[str, Any]]:
    if isinstance(operations, dict):
        operations = [operations]
    if not isinstance(operations, list) or not operations:
        raise ValueError("Informe 'operations': uma lista de operações.")
    if len(operations) > MAX_OPERATIONS:
        raise ValueError(f"Operações demais de uma vez (máximo {MAX_OPERATIONS}).")
    for op in operations:
        if not isinstance(op, dict) or not op.get("op"):
            raise ValueError("Cada operação precisa ser um objeto com o campo 'op'.")
    return operations


# ----------------------------------------------------------------------- Word
def _replace_in_paragraph(par, find: str, repl: str, limit: Optional[int]) -> int:
    """Replaces text even when Word split it across runs, keeping the first run's format."""
    count = 0
    search_from = 0
    while limit is None or count < limit:
        runs = list(par.runs)
        text = "".join(r.text for r in runs)
        pos = text.find(find, search_from)
        if pos < 0:
            break
        start, end = pos, pos + len(find)
        offset = 0
        first = True
        for run in runs:
            run_text = run.text
            r_start, r_end = offset, offset + len(run_text)
            offset = r_end
            if r_end <= start or r_start >= end:
                continue
            a, b = max(start, r_start) - r_start, min(end, r_end) - r_start
            if first:
                run.text = run_text[:a] + repl + run_text[b:]
                first = False
            else:
                run.text = run_text[:a] + run_text[b:]
        search_from = pos + len(repl)
        count += 1
    return count


def _all_paragraphs(doc):
    """Body, table cells (nested too), headers and footers."""
    def from_tables(tables):
        for table in tables:
            for row in table.rows:
                for cell in row.cells:
                    yield from cell.paragraphs
                    yield from from_tables(cell.tables)

    yield from doc.paragraphs
    yield from from_tables(doc.tables)
    for section in doc.sections:
        for part in (section.header, section.footer):
            try:
                yield from part.paragraphs
                yield from from_tables(part.tables)
            except Exception:
                continue


def _set_paragraph_text(par, text: str) -> None:
    runs = list(par.runs)
    if not runs:
        par.add_run(text)
        return
    runs[0].text = text
    for run in runs[1:]:
        run._element.getparent().remove(run._element)


def _style_or_none(doc, style: Optional[str]):
    if not style:
        return None
    try:
        return doc.styles[style]
    except KeyError:
        return None


def _add_heading(doc, text: str, level: int):
    level = max(0, min(int(level or 1), 9))
    try:
        return doc.add_heading(text, level)
    except KeyError:  # documents without the built-in heading styles
        par = doc.add_paragraph()
        run = par.add_run(text)
        run.bold = True
        return par


def _add_table(doc, rows: List[List[Any]]):
    rows = [list(r) if isinstance(r, (list, tuple)) else [r] for r in rows or []]
    if not rows:
        raise ValueError("A tabela precisa de pelo menos uma linha em 'rows'.")
    width = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=width)
    if _style_or_none(doc, "Table Grid") is not None:
        table.style = doc.styles["Table Grid"]
    for i, row in enumerate(rows):
        for j in range(width):
            table.cell(i, j).text = "" if j >= len(row) or row[j] is None else str(row[j])
    return table


def _paragraph_at(paras, index: Any, removed: set):
    try:
        i = int(index)
    except (TypeError, ValueError):
        raise ValueError(f"Índice de parágrafo inválido: {index!r}.")
    if i < 1 or i > len(paras):
        raise ValueError(f"O documento tem {len(paras)} parágrafos; ¶{i} não existe.")
    if i in removed:
        raise ValueError(f"O parágrafo ¶{i} já foi removido nesta edição.")
    return i, paras[i - 1]


def _move_to_end_of_body(doc, element) -> None:
    """New blocks go before the final section properties, like Word does."""
    body = doc.element.body
    body.remove(element)
    sect = body.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}sectPr")
    if sect is not None:
        sect.addprevious(element)
    else:
        body.append(element)


def edit_word(path: str, operations: Any, output_path: Optional[str] = None) -> Dict[str, Any]:
    """Applies a list of operations to a .docx (see the tool schema for the operations)."""
    from docx import Document

    ops = _operations(operations)
    src = _source(path, WORD_EXTS)
    out = _plan_output(src, output_path)
    doc = Document(str(src))
    paras = list(doc.paragraphs)       # ¶ numbers as read_file shows them, fixed before edits
    removed: set = set()
    done: List[str] = []
    warnings: List[str] = []

    for op in ops:
        kind = str(op["op"]).strip().lower()
        if kind == "replace":
            find = str(op.get("find") or "")
            if not find:
                raise ValueError("'replace' precisa de 'find' não vazio.")
            repl = str(op.get("replace") if op.get("replace") is not None else "")
            limit = op.get("count")
            limit = int(limit) if limit else None
            total = 0
            for par in _all_paragraphs(doc):
                left = None if limit is None else limit - total
                if left is not None and left <= 0:
                    break
                total += _replace_in_paragraph(par, find, repl, left)
            if total:
                done.append(f"trocou '{find[:40]}' por '{repl[:40]}' {total}x")
            else:
                warnings.append(f"'{find[:60]}' não foi encontrado no documento.")
        elif kind in ("append_paragraph", "append"):
            text = str(op.get("text") or "")
            par = doc.add_paragraph(text)
            style = _style_or_none(doc, op.get("style"))
            if style is not None:
                par.style = style
            done.append("acrescentou um parágrafo no fim")
        elif kind == "append_heading":
            _add_heading(doc, str(op.get("text") or ""), op.get("level") or 1)
            done.append("acrescentou um título no fim")
        elif kind == "append_table":
            table = _add_table(doc, op.get("rows"))
            _move_to_end_of_body(doc, table._tbl)
            done.append(f"acrescentou uma tabela de {len(table.rows)} linhas")
        elif kind in ("insert_paragraph", "insert"):
            text = str(op.get("text") or "")
            style = _style_or_none(doc, op.get("style"))
            if op.get("before") is not None:
                i, anchor = _paragraph_at(paras, op.get("before"), removed)
                new = anchor.insert_paragraph_before(text)
                where = f"antes do ¶{i}"
            elif op.get("after") is not None:
                i, anchor = _paragraph_at(paras, op.get("after"), removed)
                new = doc.add_paragraph(text)
                anchor._element.addnext(new._element)
                where = f"depois do ¶{i}"
            else:
                raise ValueError("'insert_paragraph' precisa de 'before' ou 'after' (número do ¶).")
            if style is not None:
                new.style = style
            done.append(f"inseriu um parágrafo {where}")
        elif kind in ("set_paragraph", "rewrite_paragraph"):
            i, par = _paragraph_at(paras, op.get("index"), removed)
            _set_paragraph_text(par, str(op.get("text") or ""))
            done.append(f"reescreveu o ¶{i}")
        elif kind in ("delete_paragraph", "remove_paragraph"):
            i, par = _paragraph_at(paras, op.get("index"), removed)
            par._element.getparent().remove(par._element)
            removed.add(i)
            done.append(f"removeu o ¶{i}")
        else:
            raise ValueError(
                f"Operação desconhecida para Word: '{kind}'. Use replace, append_paragraph, "
                "append_heading, append_table, insert_paragraph, set_paragraph ou delete_paragraph."
            )

    backup = _save(out, lambda tmp: doc.save(str(tmp)))
    return _result(src, out, backup, done, warnings)


# ---------------------------------------------------------------- spreadsheets
_CELL_RE = re.compile(r"^\$?([A-Za-z]{1,3})\$?(\d{1,7})$")


def _parse_cell(ref: str) -> Tuple[int, int]:
    match = _CELL_RE.match(str(ref).strip())
    if not match:
        raise ValueError(f"Célula inválida: '{ref}' (use algo como A1 ou BC12).")
    letters, number = match.group(1).upper(), int(match.group(2))
    column = 0
    for ch in letters:
        column = column * 26 + (ord(ch) - 64)
    if number < 1:
        raise ValueError(f"Célula inválida: '{ref}'.")
    return number, column


def _value(value: Any) -> Any:
    """JSON values as cell values; numeric strings stay text unless they look like numbers."""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("="):
            return stripped
        if re.fullmatch(r"-?\d+(\.\d+)?", stripped):
            try:
                return int(stripped) if "." not in stripped else float(stripped)
            except ValueError:
                return value
    return value


def _sheet_warnings(src: Path) -> List[str]:
    try:
        with zipfile.ZipFile(str(src)) as z:
            names = z.namelist()
    except Exception:
        return []
    lost = []
    if any(n.startswith("xl/charts/") for n in names):
        lost.append("gráficos")
    if any(n.startswith("xl/pivotTables/") for n in names):
        lost.append("tabelas dinâmicas")
    if any(n.startswith("xl/slicers/") for n in names):
        lost.append("segmentações")
    if not lost:
        return []
    return [
        "A planilha original tem " + ", ".join(lost) + ", que o editor pode não preservar. "
        "O original está intacto na Reserva (ou no arquivo de origem)."
    ]


def _xlsx_apply(wb, ops: List[Dict[str, Any]]) -> List[str]:
    done: List[str] = []

    def sheet(name: Any):
        if name in (None, ""):
            return wb.active
        if str(name) not in wb.sheetnames:
            raise ValueError(f"A planilha '{name}' não existe. Existem: {', '.join(wb.sheetnames)}.")
        return wb[str(name)]

    def put_rows(ws, rows, first_row):
        for r, row in enumerate(rows or []):
            values = row if isinstance(row, (list, tuple)) else [row]
            for c, value in enumerate(values, 1):
                ws.cell(row=first_row + r, column=c, value=_value(value))

    for op in ops:
        kind = str(op["op"]).strip().lower()
        if kind == "set_cells":
            ws = sheet(op.get("sheet"))
            cells = op.get("cells") or {}
            if not isinstance(cells, dict) or not cells:
                raise ValueError("'set_cells' precisa de 'cells': {\"A1\": valor, ...}.")
            for ref, value in cells.items():
                r, c = _parse_cell(ref)
                ws.cell(row=r, column=c, value=_value(value))
            done.append(f"preencheu {len(cells)} célula(s) em '{ws.title}'")
        elif kind == "append_rows":
            ws = sheet(op.get("sheet"))
            rows = op.get("rows") or []
            last = ws.max_row if (ws.max_row > 1 or ws.cell(1, 1).value is not None) else 0
            put_rows(ws, rows, last + 1)
            done.append(f"acrescentou {len(rows)} linha(s) em '{ws.title}'")
        elif kind == "insert_rows":
            ws = sheet(op.get("sheet"))
            at = int(op.get("at") or 0)
            rows = op.get("rows") or []
            if at < 1 or not rows:
                raise ValueError("'insert_rows' precisa de 'at' (linha, 1 = primeira) e 'rows'.")
            ws.insert_rows(at, len(rows))
            put_rows(ws, rows, at)
            done.append(f"inseriu {len(rows)} linha(s) na linha {at} de '{ws.title}'")
        elif kind == "delete_rows":
            ws = sheet(op.get("sheet"))
            start = int(op.get("start") or 0)
            count = int(op.get("count") or 1)
            if start < 1 or count < 1:
                raise ValueError("'delete_rows' precisa de 'start' (linha) e 'count'.")
            ws.delete_rows(start, count)
            done.append(f"removeu {count} linha(s) a partir da {start} em '{ws.title}'")
        elif kind == "add_sheet":
            name = str(op.get("name") or "").strip()
            if not name:
                raise ValueError("'add_sheet' precisa de 'name'.")
            if name in wb.sheetnames:
                raise ValueError(f"Já existe uma planilha chamada '{name}'.")
            ws = wb.create_sheet(title=name[:31])
            put_rows(ws, op.get("rows") or [], 1)
            done.append(f"criou a planilha '{ws.title}'")
        elif kind == "rename_sheet":
            ws = sheet(op.get("sheet"))
            new_name = str(op.get("new_name") or "").strip()[:31]
            if not new_name:
                raise ValueError("'rename_sheet' precisa de 'new_name'.")
            old = ws.title
            ws.title = new_name
            done.append(f"renomeou a planilha '{old}' para '{new_name}'")
        elif kind == "delete_sheet":
            ws = sheet(op.get("sheet"))
            if len(wb.sheetnames) == 1:
                raise ValueError("Não dá para remover a única planilha do arquivo.")
            title = ws.title
            wb.remove(ws)
            done.append(f"removeu a planilha '{title}'")
        else:
            raise ValueError(
                f"Operação desconhecida para planilha: '{kind}'. Use set_cells, append_rows, "
                "insert_rows, delete_rows, add_sheet, rename_sheet ou delete_sheet."
            )
    return done


def _xls_to_workbook(src: Path):
    """Old .xls -> openpyxl workbook (values only), saved later as .xlsx."""
    import xlrd
    from openpyxl import Workbook

    book = xlrd.open_workbook(str(src))
    wb = Workbook()
    wb.remove(wb.active)
    for sheet in book.sheets():
        ws = wb.create_sheet(title=sheet.name[:31] or "Planilha")
        for r in range(sheet.nrows):
            for c in range(sheet.ncols):
                cell = sheet.cell(r, c)
                value = cell.value
                if cell.ctype == xlrd.XL_CELL_EMPTY:
                    continue
                if cell.ctype == xlrd.XL_CELL_DATE:
                    try:
                        value = xlrd.xldate.xldate_as_datetime(value, book.datemode)
                    except Exception:
                        pass
                ws.cell(row=r + 1, column=c + 1, value=value)
    return wb


def _csv_apply(rows: List[List[str]], ops: List[Dict[str, Any]]) -> List[str]:
    done: List[str] = []

    def to_text(value: Any) -> str:
        return "" if value is None else str(value)

    def ensure(r: int, c: int) -> None:
        while len(rows) < r:
            rows.append([])
        while len(rows[r - 1]) < c:
            rows[r - 1].append("")

    for op in ops:
        kind = str(op["op"]).strip().lower()
        if kind == "set_cells":
            cells = op.get("cells") or {}
            for ref, value in cells.items():
                r, c = _parse_cell(ref)
                ensure(r, c)
                rows[r - 1][c - 1] = to_text(value)
            done.append(f"preencheu {len(cells)} célula(s)")
        elif kind == "append_rows":
            new = [[to_text(v) for v in (row if isinstance(row, (list, tuple)) else [row])]
                   for row in op.get("rows") or []]
            rows.extend(new)
            done.append(f"acrescentou {len(new)} linha(s)")
        elif kind == "insert_rows":
            at = int(op.get("at") or 0)
            new = [[to_text(v) for v in (row if isinstance(row, (list, tuple)) else [row])]
                   for row in op.get("rows") or []]
            if at < 1 or not new:
                raise ValueError("'insert_rows' precisa de 'at' e 'rows'.")
            rows[at - 1:at - 1] = new
            done.append(f"inseriu {len(new)} linha(s) na linha {at}")
        elif kind == "delete_rows":
            start = int(op.get("start") or 0)
            count = int(op.get("count") or 1)
            if start < 1:
                raise ValueError("'delete_rows' precisa de 'start'.")
            del rows[start - 1:start - 1 + count]
            done.append(f"removeu {count} linha(s) a partir da {start}")
        else:
            raise ValueError(
                f"Operação '{kind}' não vale para CSV. Use set_cells, append_rows, insert_rows ou delete_rows."
            )
    return done


def edit_spreadsheet(path: str, operations: Any, output_path: Optional[str] = None) -> Dict[str, Any]:
    """Edits .xlsx/.xlsm/.csv/.tsv; an old .xls is converted and saved as .xlsx."""
    ops = _operations(operations)
    src = _source(path, SHEET_EXTS | OLD_SHEET_EXTS | TABLE_EXTS)
    ext = src.suffix.lower()
    warnings: List[str] = []

    if ext in TABLE_EXTS:
        rows, dialect = _csv_rows(src)
        done = _csv_apply(rows, ops)
        out = _plan_output(src, output_path)

        def write_csv(tmp: Path) -> None:
            with open(tmp, "w", encoding="utf-8-sig", newline="") as fh:
                csv.writer(fh, dialect).writerows(rows)

        backup = _save(out, write_csv)
        return _result(src, out, backup, done)

    from openpyxl import load_workbook

    if ext in OLD_SHEET_EXTS:
        wb = _xls_to_workbook(src)
        out = _plan_output(src, output_path, suffix=".xlsx")
        warnings.append("O .xls antigo foi convertido: a versão editada é um .xlsx novo (só valores).")
    else:
        wb = load_workbook(str(src), keep_vba=(ext == ".xlsm"))
        out = _plan_output(src, output_path)
        warnings.extend(_sheet_warnings(src))
    done = _xlsx_apply(wb, ops)
    backup = _save(out, lambda tmp: wb.save(str(tmp)))
    return _result(src, out, backup, done, warnings)


# ------------------------------------------------------------------------ PDF
def _page_numbers(spec: Any, total: int) -> List[int]:
    """'1-3,5', [1, 2], 'all' or 'last' -> 0-based page indices, in the given order."""
    if spec in (None, "", "all", "todas"):
        return list(range(total))
    items: List[Any] = spec if isinstance(spec, list) else str(spec).replace(" ", "").split(",")
    pages: List[int] = []
    for item in items:
        text = str(item).lower()
        if not text:
            continue
        if text in ("last", "ultima", "última"):
            pages.append(total - 1)
            continue
        if "-" in text:
            a, b = text.split("-", 1)
            start = int(a) if a else 1
            end = total if b in ("", "last", "fim") else int(b)
            if start < 1 or end > total or start > end:
                raise ValueError(f"Intervalo de páginas inválido: '{item}' (o PDF tem {total}).")
            pages.extend(range(start - 1, end))
        else:
            n = int(text)
            if n < 1 or n > total:
                raise ValueError(f"Página {n} não existe (o PDF tem {total}).")
            pages.append(n - 1)
    return pages


def edit_pdf(path: str, operations: Any, output_path: Optional[str] = None) -> Dict[str, Any]:
    """Page-level PDF edits: keep/extract, delete, rotate, reorder, merge, metadata."""
    from pypdf import PdfReader, PdfWriter

    ops = _operations(operations)
    src = _source(path, PDF_EXTS)
    out = _plan_output(src, output_path)
    reader = PdfReader(str(src))
    if reader.is_encrypted:
        raise PermissionError("O PDF está protegido por senha; não consigo editá-lo.")
    pages = list(reader.pages)
    metadata: Dict[str, str] = {}
    done: List[str] = []

    for op in ops:
        kind = str(op["op"]).strip().lower()
        if kind in ("keep_pages", "extract_pages", "reorder"):
            chosen = _page_numbers(op.get("pages"), len(pages))
            if not chosen:
                raise ValueError("Nenhuma página escolhida.")
            pages = [pages[i] for i in chosen]
            done.append(f"ficou com {len(pages)} página(s)")
        elif kind == "delete_pages":
            drop = set(_page_numbers(op.get("pages"), len(pages)))
            if len(drop) >= len(pages):
                raise ValueError("Não dá para remover todas as páginas.")
            pages = [p for i, p in enumerate(pages) if i not in drop]
            done.append(f"removeu {len(drop)} página(s)")
        elif kind == "rotate":
            degrees = int(op.get("degrees") or 90)
            if degrees % 90:
                raise ValueError("A rotação precisa ser múltipla de 90 graus.")
            chosen = _page_numbers(op.get("pages"), len(pages))
            for i in chosen:
                pages[i].rotate(degrees)
            done.append(f"girou {len(chosen)} página(s) em {degrees}°")
        elif kind in ("merge", "append_pdf"):
            others = op.get("paths") or ([op["path"]] if op.get("path") else [])
            if not others:
                raise ValueError("'merge' precisa de 'paths': PDFs a juntar no fim.")
            for other in others:
                other_src = _source(str(other), PDF_EXTS)
                other_reader = PdfReader(str(other_src))
                if other_reader.is_encrypted:
                    raise PermissionError(f"'{other_src.name}' está protegido por senha.")
                pages.extend(other_reader.pages)
                done.append(f"juntou '{other_src.name}' ({len(other_reader.pages)} pág.)")
        elif kind == "metadata":
            for key in ("title", "author", "subject", "keywords"):
                if op.get(key):
                    metadata[f"/{key.capitalize()}"] = str(op[key])
            done.append("atualizou os metadados")
        else:
            raise ValueError(
                f"Operação desconhecida para PDF: '{kind}'. Use keep_pages, delete_pages, "
                "rotate, merge ou metadata. (O texto dentro do PDF não é editável aqui: "
                "para reescrever o conteúdo, crie um .docx novo com create_document.)"
            )

    writer = PdfWriter()
    for page in pages:
        writer.add_page(page)
    if reader.metadata:
        try:
            writer.add_metadata({k: str(v) for k, v in reader.metadata.items() if isinstance(k, str)})
        except Exception:
            pass
    if metadata:
        writer.add_metadata(metadata)

    def write_pdf(tmp: Path) -> None:
        with open(tmp, "wb") as fh:
            writer.write(fh)

    backup = _save(out, write_pdf)
    result = _result(src, out, backup, done)
    result["total_pages"] = len(pages)
    return result


# ------------------------------------------------------------------- creation
_TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _markdown_blocks(content: str):
    """Yields ('heading', level, text), ('bullet', text), ('number', text), ('table', rows), ('text', text)."""
    lines = (content or "").replace("\r\n", "\n").split("\n")
    i = 0
    paragraph: List[str] = []

    def flush():
        if paragraph:
            text = " ".join(s.strip() for s in paragraph).strip()
            paragraph.clear()
            if text:
                return ("text", text)
        return None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if _TABLE_LINE.match(line):
            block = flush()
            if block:
                yield block
            rows = []
            while i < len(lines) and _TABLE_LINE.match(lines[i]):
                if not _TABLE_RULE.match(lines[i]):
                    rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            if rows:
                yield ("table", rows)
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        bullet = re.match(r"^[-*•]\s+(.*)$", stripped)
        number = re.match(r"^\d+[.)]\s+(.*)$", stripped)
        if heading or bullet or number or not stripped:
            block = flush()
            if block:
                yield block
            if heading:
                yield ("heading", len(heading.group(1)), heading.group(2).strip())
            elif bullet:
                yield ("bullet", bullet.group(1).strip())
            elif number:
                yield ("number", number.group(1).strip())
        else:
            paragraph.append(stripped)
        i += 1
    block = flush()
    if block:
        yield block


def _inline_runs(par, text: str) -> None:
    """**negrito** and *itálico* in docx runs."""
    for piece in re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", text):
        if not piece:
            continue
        if piece.startswith("**") and piece.endswith("**") and len(piece) > 4:
            par.add_run(piece[2:-2]).bold = True
        elif piece.startswith("*") and piece.endswith("*") and len(piece) > 2:
            par.add_run(piece[1:-1]).italic = True
        else:
            par.add_run(piece)


def _write_docx(tmp: Path, content: str, title: Optional[str]) -> None:
    from docx import Document

    doc = Document()
    if title:
        _add_heading(doc, title, 0)
    for block in _markdown_blocks(content):
        kind = block[0]
        if kind == "heading":
            _add_heading(doc, block[2], block[1])
        elif kind in ("bullet", "number"):
            style = "List Bullet" if kind == "bullet" else "List Number"
            par = doc.add_paragraph(style=style if _style_or_none(doc, style) is not None else None)
            _inline_runs(par, block[1])
        elif kind == "table":
            _add_table(doc, block[1])
        else:
            _inline_runs(doc.add_paragraph(), block[1])
    doc.save(str(tmp))


def _sheets_from(rows: Any, sheets: Any, content: str) -> Dict[str, List[List[Any]]]:
    if isinstance(sheets, dict) and sheets:
        return {str(k)[:31] or "Planilha": list(v or []) for k, v in sheets.items()}
    if isinstance(rows, list) and rows:
        return {"Planilha1": rows}
    if content and content.strip():
        dialect = _sniff_dialect(content[:20000], ".csv")
        return {"Planilha1": [list(r) for r in csv.reader(io.StringIO(content), dialect)]}
    return {"Planilha1": []}


def _write_xlsx(tmp: Path, data: Dict[str, List[List[Any]]]) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in data.items():
        ws = wb.create_sheet(title=name)
        for r, row in enumerate(rows, 1):
            values = row if isinstance(row, (list, tuple)) else [row]
            for c, value in enumerate(values, 1):
                ws.cell(row=r, column=c, value=_value(value))
        if rows:
            for cell in ws[1]:
                cell.font = Font(bold=True)
            for c in range(1, max(len(r) if isinstance(r, (list, tuple)) else 1 for r in rows) + 1):
                width = max(
                    (len(str(r[c - 1])) for r in rows if isinstance(r, (list, tuple)) and len(r) >= c and r[c - 1] is not None),
                    default=8,
                )
                ws.column_dimensions[_column_letter(c)].width = min(60, max(8, width + 2))
    wb.save(str(tmp))


def _write_pptx(tmp: Path, content: str, title: Optional[str]) -> None:
    from pptx import Presentation

    deck = Presentation()
    blocks = list(_markdown_blocks(content))
    if title:
        slide = deck.slides.add_slide(deck.slide_layouts[0])
        slide.shapes.title.text = title
    slide = None
    body = None
    for block in blocks:
        kind = block[0]
        if kind == "heading":
            slide = deck.slides.add_slide(deck.slide_layouts[1])
            slide.shapes.title.text = block[2]
            body = slide.placeholders[1].text_frame
            body.text = ""
            continue
        if slide is None:
            slide = deck.slides.add_slide(deck.slide_layouts[1])
            slide.shapes.title.text = title or ""
            body = slide.placeholders[1].text_frame
            body.text = ""
        lines = [" | ".join(r) for r in block[1]] if kind == "table" else [block[-1]]
        for line in lines:
            par = body.paragraphs[0] if not body.paragraphs[0].text else body.add_paragraph()
            par.text = str(line)
    if not deck.slides:
        deck.slides.add_slide(deck.slide_layouts[0]).shapes.title.text = title or ""
    deck.save(str(tmp))


def create_document(
    path: str,
    content: str = "",
    title: Optional[str] = None,
    rows: Optional[List[List[Any]]] = None,
    sheets: Optional[Dict[str, List[List[Any]]]] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """New .docx/.pptx (from Markdown-like text), .xlsx/.csv (from rows) or .md/.txt."""
    target = path_guard.validate_and_resolve(path, for_write=True)
    ext = target.suffix.lower()
    if ext not in CREATE_EXTS:
        hint = " (Para PDF, crie um .docx e exporte pelo Word.)" if ext == ".pdf" else ""
        raise ValueError(f"Não sei criar '{ext}'. Aceitos: {', '.join(sorted(CREATE_EXTS))}.{hint}")
    if target.exists() and not overwrite:
        raise FileExistsError(f"'{target}' já existe. Use overwrite=true para substituí-lo (o original vai para a Reserva).")

    if ext == ".docx":
        writer = lambda tmp: _write_docx(tmp, content, title)  # noqa: E731
    elif ext == ".pptx":
        writer = lambda tmp: _write_pptx(tmp, content, title)  # noqa: E731
    elif ext == ".xlsx":
        data = _sheets_from(rows, sheets, content)
        writer = lambda tmp: _write_xlsx(tmp, data)  # noqa: E731
    elif ext == ".csv":
        data = _sheets_from(rows, None, content)
        table = next(iter(data.values()))

        def writer(tmp: Path) -> None:
            with open(tmp, "w", encoding="utf-8-sig", newline="") as fh:
                csv.writer(fh).writerows(table)
    else:
        text = (f"# {title}\n\n" if title and ext == ".md" else "") + (content or "")

        def writer(tmp: Path) -> None:
            tmp.write_text(text, encoding="utf-8")

    backup = _save(target, writer)
    return _result(None, target, backup, [f"criou {target.name}"])
