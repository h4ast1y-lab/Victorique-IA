"""
Foto do avatar da Victorique (sidebar, mensagens, tela inicial, ícone).

A foto padrão vem com o app (``app/ui/img/victorique-avatar.webp``). O usuário
pode enviar outra pelas Configurações: ela é validada com Pillow, recortada em
quadrado, reduzida e regravada como PNG em ``DATA_DIR/avatar/custom.png``.
Regravar descarta metadados e qualquer conteúdo que não seja a imagem em si.
A escolha fica na preferência ``avatar_photo`` ("default" ou "custom").
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any, Dict

from PIL import Image, UnidentifiedImageError

from app.config import BASE_DIR, DATA_DIR
from app.core import preferences

logger = logging.getLogger(__name__)

DEFAULT_PATH = BASE_DIR / "app" / "ui" / "img" / "victorique-avatar.webp"
AVATAR_DIR = DATA_DIR / "avatar"
CUSTOM_PATH = AVATAR_DIR / "custom.png"

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 40_000_000  # recusa "bombas" de descompressão
OUTPUT_SIZE = 512
ALLOWED_FORMATS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}


class AvatarError(ValueError):
    """Erro com mensagem pronta para o usuário."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _square(img: Image.Image) -> Image.Image:
    width, height = img.size
    side = min(width, height)
    left = (width - side) // 2
    # Retratos costumam ter o rosto no terço de cima: corta mais embaixo.
    top = (height - side) // 3 if height > width else (height - side) // 2
    return img.crop((left, top, left + side, top + side))


def process_upload(data: bytes) -> bytes:
    """Valida a imagem enviada e devolve o PNG quadrado que será salvo."""
    if not data:
        raise AvatarError("Arquivo vazio.")
    if len(data) > MAX_BYTES:
        raise AvatarError(f"Imagem maior que o limite de {MAX_BYTES // (1024 * 1024)} MB.", 413)
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            width, height = probe.size
            probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise AvatarError("Arquivo não é uma imagem válida (use PNG, JPG ou WEBP).") from None
    if fmt not in ALLOWED_FORMATS:
        raise AvatarError("Formato não suportado. Use PNG, JPG ou WEBP.")
    if width * height > MAX_PIXELS:
        raise AvatarError("Imagem grande demais (resolução).", 413)
    if min(width, height) < 32:
        raise AvatarError("Imagem pequena demais (mínimo 32×32).")
    try:
        # verify() invalida o objeto: reabre para decodificar de verdade.
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            img = img.convert("RGBA")
    except Exception:
        raise AvatarError("Não consegui ler essa imagem.") from None
    img = _square(img)
    if img.width > OUTPUT_SIZE:
        img = img.resize((OUTPUT_SIZE, OUTPUT_SIZE), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def current_path() -> Path:
    if preferences.load().get("avatar_photo") == "custom" and CUSTOM_PATH.is_file():
        return CUSTOM_PATH
    return DEFAULT_PATH


def info() -> Dict[str, Any]:
    path = current_path()
    source = "custom" if path == CUSTOM_PATH else "default"
    try:
        version = int(path.stat().st_mtime)
    except OSError:
        version = 0
    return {"source": source, "url": f"/api/avatar/photo?v={source}-{version}"}


def save_custom(data: bytes) -> Dict[str, Any]:
    png = process_upload(data)
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CUSTOM_PATH.with_suffix(".tmp")
    tmp.write_bytes(png)
    tmp.replace(CUSTOM_PATH)
    preferences.update({"avatar_photo": "custom"})
    return info()


def restore_default() -> Dict[str, Any]:
    preferences.update({"avatar_photo": "default"})
    try:
        CUSTOM_PATH.unlink(missing_ok=True)
    except OSError as exc:  # arquivo preso: a preferência já manda no padrão
        logger.warning("Não apaguei a foto personalizada: %s", exc)
    return info()


# ----------------- Ícone (.ico) para a janela e o executável -----------------
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
DEFAULT_ICO = BASE_DIR / "app" / "ui" / "img" / "victorique.ico"
WINDOW_ICO = AVATAR_DIR / "window.ico"


def _round(img: Image.Image) -> Image.Image:
    """Recorte redondo com borda suave (máscara desenhada em 4x e reduzida)."""
    from PIL import ImageDraw

    size = img.width
    big = size * 4
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, big - 1, big - 1), fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def make_ico(src: Path, dest: Path) -> Path:
    with Image.open(src) as img:
        img = _square(img.convert("RGBA")).resize((256, 256), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _round(img).save(dest, format="ICO", sizes=ICO_SIZES)
    return dest


def window_icon() -> Path | None:
    """Ícone da foto atual para a janela do app; None se não der para gerar."""
    try:
        if current_path() == DEFAULT_PATH and DEFAULT_ICO.is_file():
            return DEFAULT_ICO
        return make_ico(current_path(), WINDOW_ICO)
    except Exception as exc:
        logger.warning("Não gerei o ícone da janela: %s", exc)
        return DEFAULT_ICO if DEFAULT_ICO.is_file() else None
