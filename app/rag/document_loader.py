import logging
import os
import re
import shutil
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

from pypdf import PdfReader

from app.config import settings

logger = logging.getLogger("document_loader")


class OCREngine:
    """Local OCR for PDFs that have no embedded text layer.

    Uses pypdfium2 to render pages and Tesseract (via pytesseract) to read
    them. Nothing is uploaded: rendering and OCR run on this machine.
    """

    def __init__(self):
        self._resolved: Optional[Dict[str, Any]] = None

    def find_tesseract(self) -> Optional[str]:
        candidates: List[str] = []
        if settings.tesseract_cmd:
            candidates.append(settings.tesseract_cmd)
        if os.environ.get("TESSERACT_CMD"):
            candidates.append(os.environ["TESSERACT_CMD"])
        env_path = shutil.which("tesseract")
        if env_path:
            candidates.append(env_path)

        for base in (
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs"),
        ):
            if base:
                candidates.append(str(Path(base) / "Tesseract-OCR" / "tesseract.exe"))

        for candidate in candidates:
            try:
                if candidate and Path(candidate).is_file():
                    return str(Path(candidate))
            except OSError:
                continue
        return None

    def tessdata_dir(self, cmd: Optional[str] = None) -> Optional[Path]:
        prefix = os.environ.get("TESSDATA_PREFIX")
        if prefix:
            p = Path(prefix)
            if (p / "eng.traineddata").is_file() or (p / "por.traineddata").is_file():
                return p
            if (p / "tessdata").is_dir():
                return p / "tessdata"
        cmd = cmd or self.find_tesseract()
        if not cmd:
            return None
        candidate = Path(cmd).resolve().parent / "tessdata"
        return candidate if candidate.is_dir() else None

    def available_languages(self, cmd: Optional[str] = None) -> List[str]:
        data_dir = self.tessdata_dir(cmd)
        if not data_dir:
            return []
        try:
            return sorted(
                p.stem for p in data_dir.glob("*.traineddata") if p.is_file()
            )
        except OSError:
            return []

    def resolve_language(self, preferred: Optional[str] = None) -> str:
        available = self.available_languages()
        if not available:
            return "eng"
        requested = preferred if preferred is not None else settings.ocr_lang
        tokens = [t.strip() for t in str(requested or "").split("+") if t.strip()]
        chosen = [t for t in tokens if t in available]
        if not chosen:
            for candidate in ("por", "eng"):
                if candidate in available:
                    chosen = [candidate]
                    break
        if not chosen:
            usable = [lang for lang in available if lang != "osd"]
            chosen = usable[:1] or ["eng"]
        return "+".join(chosen)

    def status(self) -> Dict[str, Any]:
        """Small, JSON-serializable description used by /api/health."""
        cmd = self.find_tesseract()
        available = self.available_languages(cmd) if cmd else []
        deps_ok = True
        try:
            import pypdfium2  # noqa: F401
            import pytesseract  # noqa: F401
            from PIL import Image  # noqa: F401
        except Exception:
            deps_ok = False
        return {
            "enabled": bool(settings.ocr_enabled),
            "available": bool(cmd and deps_ok),
            "engine": "tesseract",
            "tesseract": cmd,
            "languages": available,
            "language_used": self.resolve_language() if cmd else None,
            "dpi": settings.ocr_dpi,
        }

    def ocr_pages(self, path: Path, page_indexes: List[int]) -> Dict[int, str]:
        cmd = self.find_tesseract()
        if not cmd:
            raise RuntimeError(
                "Tesseract não encontrado. Instale o Tesseract-OCR ou defina TESSERACT_CMD."
            )
        try:
            import pypdfium2 as pdfium
            import pytesseract
        except Exception as exc:  # pragma: no cover - depends on environment
            raise RuntimeError(f"Dependências de OCR indisponíveis: {exc}") from exc

        pytesseract.pytesseract.tesseract_cmd = cmd
        lang = self.resolve_language()
        scale = max(1.0, float(settings.ocr_dpi) / 72.0)
        results: Dict[int, str] = {}

        pdf = pdfium.PdfDocument(str(path))
        try:
            for index in page_indexes:
                page = pdf[index]
                try:
                    bitmap = page.render(scale=scale)
                    try:
                        image = bitmap.to_pil()
                    finally:
                        bitmap.close()
                    results[index] = pytesseract.image_to_string(image, lang=lang).strip()
                finally:
                    page.close()
        finally:
            pdf.close()
        return results


class DocumentLoader:
    def __init__(self):
        self.ocr = OCREngine()
        self.last_ocr: Dict[str, Any] = {}

    def load(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Loads document content by page/section.
        Returns a list of dicts: [{"page": int, "text": str}]
        """
        p = Path(file_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")

        self.last_ocr = {"pages": [], "error": None, "language": None}
        ext = p.suffix.lower()
        if ext == ".pdf":
            return self._load_pdf(p)
        elif ext in [".txt", ".md"]:
            return self._load_text(p)
        elif ext == ".docx":
            return self._load_docx(p)
        elif ext == ".epub":
            return self._load_epub(p)
        elif ext in [".csv", ".json", ".py", ".js", ".html", ".css", ".xml", ".yaml", ".yml"]:
            return self._load_structured_text(p)
        else:
            supported = ", ".join(settings.allowed_document_extensions)
            raise ValueError(
                f"Formato de arquivo não suportado: '{ext}'. Suportados: {supported}"
            )

    def _load_docx(self, path: Path) -> List[Dict[str, Any]]:
        """Extrai parágrafos de documento Word (.docx) sem dependências externas."""
        try:
            with zipfile.ZipFile(str(path)) as z:
                xml_content = z.read("word/document.xml")
            root = ET.fromstring(xml_content)
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            paragraphs = []
            for p in root.iterfind(".//w:p", ns):
                texts = [node.text for node in p.iterfind(".//w:t", ns) if node.text]
                if texts:
                    paragraphs.append("".join(texts))
            full_text = "\n\n".join(paragraphs).strip()
            if not full_text:
                return []
            return [{"page": 1, "text": full_text}]
        except Exception as exc:
            raise ValueError(f"Falha ao ler arquivo DOCX '{path.name}': {exc}") from exc

    def _load_epub(self, path: Path) -> List[Dict[str, Any]]:
        """Extrai capítulos/seções de livro digital (.epub)."""
        try:
            with zipfile.ZipFile(str(path)) as z:
                html_files = [
                    f for f in z.namelist()
                    if f.lower().endswith((".html", ".xhtml", ".htm"))
                ]
                pages = []
                page_idx = 1
                for h in sorted(html_files):
                    raw = z.read(h).decode("utf-8", errors="replace")
                    # Remove scripts, styles e tags HTML
                    text = re.sub(r"<style.*?</style>", "", raw, flags=re.DOTALL | re.IGNORECASE)
                    text = re.sub(r"<script.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
                    text = re.sub(r"<[^>]+>", " ", text)
                    text = " ".join(text.split()).strip()
                    if len(text) > 40:
                        pages.append({"page": page_idx, "text": text})
                        page_idx += 1
                return pages
        except Exception as exc:
            raise ValueError(f"Falha ao ler arquivo EPUB '{path.name}': {exc}") from exc

    def _load_structured_text(self, path: Path) -> List[Dict[str, Any]]:
        """Carrega arquivos de código, dados e texto estruturado."""
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            return []
        header = f"[{path.name} - Formato {path.suffix.upper()}]\n"
        return [{"page": 1, "text": header + text}]

    def _load_pdf(self, path: Path) -> List[Dict[str, Any]]:
        reader = PdfReader(str(path))
        raw_texts: List[str] = []
        for page in reader.pages:
            raw_texts.append((page.extract_text() or "").strip())

        needs_ocr = [
            idx
            for idx, text in enumerate(raw_texts)
            if len(text) < max(1, int(settings.ocr_min_chars))
        ]

        ocr_results: Dict[int, str] = {}
        ocr_error: Optional[str] = None
        self.last_ocr = {"pages": [], "error": None, "language": None}

        if needs_ocr and settings.ocr_enabled:
            logger.info(f"OCR necessário em {len(needs_ocr)} página(s) de {path.name}")
            try:
                ocr_results = self.ocr.ocr_pages(path, needs_ocr)
                self.last_ocr = {
                    "pages": sorted(idx + 1 for idx in ocr_results),
                    "language": self.ocr.resolve_language(),
                    "error": None,
                }
            except Exception as exc:
                ocr_error = str(exc)
                self.last_ocr["error"] = ocr_error
                logger.warning(f"OCR falhou para {path.name}: {exc}")

        pages: List[Dict[str, Any]] = []
        for idx, text in enumerate(raw_texts):
            candidate = ocr_results.get(idx, text)
            candidate = (candidate or "").strip()
            if candidate:
                pages.append({"page": idx + 1, "text": candidate})

        if not pages and needs_ocr:
            if not settings.ocr_enabled:
                raise ValueError(
                    "PDF sem texto extraível e o OCR está desativado "
                    "(ASSISTANT_OCR=0)."
                )
            if ocr_error:
                raise ValueError(
                    "PDF sem texto extraível e o OCR falhou: "
                    f"{ocr_error}"
                )
            raise ValueError(
                "PDF sem texto extraível e o OCR não encontrou texto legível. "
                "Verifique a qualidade do documento ou use um PDF com texto."
            )
        return pages

    def _load_text(self, path: Path) -> List[Dict[str, Any]]:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            return []
        return [{"page": 1, "text": text}]


ocr_engine = OCREngine()
document_loader = DocumentLoader()
