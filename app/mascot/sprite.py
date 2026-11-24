"""
Victorique's pixel-art frames for the desktop mascot.

The frames come from the sprite sheets in assets/source/, packed by
scripts/build_mascot_sprites.py into assets/victorique.webp plus
assets/victorique.json. Every frame has an anchor: the point that sits on her
position (the soles for most poses, the seat when she sits on a window edge,
her hand while she is dragged (under the real cursor), the screen edge when
she peeks).

`render(look, height)` gives the RGBA image at a given standing height and
where its anchor is, mirrored when the drawing faces the other way.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageOps

ASSETS = Path(__file__).resolve().parent / "assets"
ATLAS_IMAGE = ASSETS / "victorique.webp"
ATLAS_DATA = ASSETS / "victorique.json"

# Animations never mirrored. The dragged frames used to carry a drawn arrow
# cursor; it is erased when the atlas is built, so she can hang on either side.
NO_MIRROR: set = set()
EFFECTS = ("zzz",)


@dataclass(frozen=True)
class Look:
    """What to draw: a frame of an animation, which way she faces (1 right,
    -1 left; front-facing animations ignore it) and an optional effect."""
    anim: str = "blink"
    frame: int = 0
    facing: int = 1
    effect: Optional[str] = None
    effect_frame: int = 0


class _Atlas:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._image: Optional[Image.Image] = None
        self._data: Dict = {}

    def _load(self) -> None:
        with self._lock:
            if self._image is None:
                self._data = json.loads(ATLAS_DATA.read_text(encoding="utf-8"))
                image = Image.open(ATLAS_IMAGE)
                image.load()
                self._image = image.convert("RGBA")

    @property
    def data(self) -> Dict:
        if self._image is None:
            self._load()
        return self._data

    def frame(self, anim: str, index: int) -> Tuple[Image.Image, float, float]:
        data = self.data["anims"][anim]
        frames = data["frames"]
        x, y, w, h, ax, ay = frames[index % len(frames)]
        assert self._image is not None
        return self._image.crop((x, y, x + w, y + h)), ax, ay


_atlas = _Atlas()


def stand_height() -> int:
    """Standing height of the frames in the atlas (px)."""
    return int(_atlas.data["stand_height"])


def animations() -> List[str]:
    return list(_atlas.data["anims"])


def frame_count(anim: str) -> int:
    return len(_atlas.data["anims"][anim]["frames"])


def facing_of(anim: str) -> str:
    """Which way the drawing faces: left, right or front."""
    return _atlas.data["anims"][anim]["facing"]


def mirrored(look: Look) -> bool:
    native = facing_of(look.anim)
    if look.anim in NO_MIRROR or native == "front":
        return False
    return (native == "left") != (look.facing < 0)


@lru_cache(maxsize=256)
def render(look: Look, height: int) -> Tuple[Image.Image, Tuple[int, int]]:
    """The frame scaled so that her standing height is `height` px, and the
    anchor's position inside that image."""
    crop, ax, ay = _atlas.frame(look.anim, look.frame)
    scale = height / stand_height()
    w = max(1, round(crop.width * scale))
    h = max(1, round(crop.height * scale))
    img = crop.resize((w, h), Image.LANCZOS) if (w, h) != crop.size else crop.copy()
    ax, ay = ax * scale, ay * scale
    if mirrored(look):
        img = ImageOps.mirror(img)
        ax = w - ax
    if look.effect == "zzz":
        img, (ax, ay) = _with_zzz(img, (ax, ay), height, look.effect_frame)
    return img, (round(ax), round(ay))


def body_width(height: int) -> float:
    """About how wide she is standing (for keeping her on screen)."""
    return height * 0.5


@lru_cache(maxsize=8)
def _font(size: int) -> ImageFont.ImageFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _with_zzz(img: Image.Image, anchor: Tuple[float, float], height: int,
              frame: int) -> Tuple[Image.Image, Tuple[float, float]]:
    """Three drifting z's beside the head of a sleeping frame (9-frame cycle)."""
    pad_top, pad_right = round(height * 0.22), round(height * 0.28)
    canvas = Image.new("RGBA", (img.width + pad_right, img.height + pad_top), (0, 0, 0, 0))
    canvas.alpha_composite(img, (0, pad_top))
    d = ImageDraw.Draw(canvas)
    base_x, base_y = img.width * 0.72, pad_top + img.height * 0.12
    for k in range(3):
        phase = ((frame % 9) / 9.0 + k / 3.0) % 1.0
        size = max(7, round(height * (0.07 + 0.05 * phase)))
        x = base_x + phase * pad_right * 0.9
        y = base_y - phase * (pad_top + img.height * 0.1)
        alpha = round(255 * min(1.0, 1.6 - 1.6 * phase))
        d.text((x, y), "z", font=_font(size), fill=(236, 226, 205, alpha),
               stroke_width=max(1, size // 9), stroke_fill=(40, 30, 40, alpha))
    return canvas, (anchor[0], anchor[1] + pad_top)


# ----------------- The little door to the Biblioteca -----------------
DOOR_COLORS = {"frame": "#3e2718", "wood": "#7a5236", "dark": "#5a3b26", "brass": "#c9a55a",
               "inside": "#1c140f", "glow": "#6b4a2a"}
DOOR_GRID = (16, 24)        # drawn on a small grid, scaled up with hard edges


@lru_cache(maxsize=32)
def door_image(frame: int, height: int) -> Image.Image:
    """Pixel-art door in the hall's woods: 0 closed, 1 ajar, 2 open.

    Its height is three quarters of hers; transparent around it."""
    gw, gh = DOOR_GRID
    c = DOOR_COLORS
    img = Image.new("RGBA", (gw, gh), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((1, 0, gw - 2, gh - 1), fill=c["frame"])          # frame
    d.rectangle((3, 2, gw - 4, gh - 1), fill=c["inside"])         # doorway
    d.rectangle((4, gh - 5, gw - 5, gh - 1), fill=c["glow"])      # lamplight on the floor inside
    frame = max(0, min(2, int(frame)))
    leaf = {0: gw - 6, 1: 6, 2: 2}[frame]                         # width of the door leaf
    x0, x1 = 3, 3 + leaf - 1
    d.rectangle((x0, 2, x1, gh - 1), fill=c["wood"])
    if leaf >= 6:
        d.rectangle((x0 + 1, 4, x1 - 1, 10), outline=c["dark"])
        d.rectangle((x0 + 1, 13, x1 - 1, gh - 3), outline=c["dark"])
        d.point((x1 - 1, 12), fill=c["brass"])                      # knob
    else:
        d.line((x1, 2, x1, gh - 1), fill=c["dark"])
    h = max(4, round(0.75 * height))
    w = max(3, round(h * gw / gh))
    return img.resize((w, h), Image.NEAREST)
