"""
Procedural drawing of the miniature Victorique (desktop mascot).

Everything is drawn with Pillow from simple shapes in a 120 x 150 "design
unit" box (feet on y=147), at 3x supersampling and then reduced, so edges are
smooth and the alpha channel is real (the window shows the desktop behind
her). No image files: the figure is code, like the IA-2 procedural portrait
this replaces.

The figure is drawn facing right; the caller mirrors it to face left.
"""
from __future__ import annotations

import math
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Iterator, List, Optional, Sequence, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageOps

W, H = 120, 150
FLOOR = 147.0
SUPERSAMPLE = 3

Point = Tuple[float, float]
Color = Tuple[int, ...]

# ----------------- Palette -----------------
INK = (58, 38, 44, 255)
SKIN = (255, 238, 226, 255)
SKIN_SHADE = (240, 206, 192, 255)
HAIR_LIGHT = (252, 232, 160, 255)
HAIR = (240, 200, 98, 255)
HAIR_DARK = (204, 152, 62, 255)
HAIR_INK = (150, 100, 44, 255)
DRESS = (46, 36, 56, 255)
DRESS_LIGHT = (78, 62, 92, 255)
DRESS_DARK = (30, 22, 38, 255)
LACE = (250, 246, 240, 255)
LACE_SHADE = (214, 206, 218, 255)
WINE = (156, 42, 74, 255)
WINE_DARK = (108, 26, 50, 255)
IRIS_TOP = (26, 84, 56, 255)
IRIS_BOTTOM = (104, 186, 110, 255)
PUPIL = (12, 36, 24, 255)
MOUTH = (160, 72, 84, 255)
MOUTH_IN = (122, 40, 56, 255)
BLUSH = (246, 132, 146)
STOCKING = (250, 248, 244, 255)
SHOE = (38, 28, 34, 255)
PIPE_STEM = (238, 226, 204, 255)
PIPE_BOWL = (126, 80, 50, 255)
BOOK_COVER = (112, 40, 52, 255)
PAGE = (248, 240, 222, 255)
SMOKE = (236, 236, 240)
SPARK = (255, 222, 120, 255)


# ----------------- Geometry helpers -----------------
def ellipse(cx: float, cy: float, rx: float, ry: float, n: int = 40,
            a0: float = 0.0, a1: float = 2 * math.pi) -> List[Point]:
    return [(cx + rx * math.cos(a0 + (a1 - a0) * i / n), cy + ry * math.sin(a0 + (a1 - a0) * i / n))
            for i in range(n + (0 if a1 - a0 >= 2 * math.pi else 1))]


def bezier(p0: Point, p1: Point, p2: Point, p3: Point, n: int = 14) -> List[Point]:
    out = []
    for i in range(1, n + 1):
        t = i / n
        u = 1 - t
        out.append((u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                    u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
    return out


def path(start: Point, *segments) -> List[Point]:
    """Segments: (x, y) for a line, or ((c1), (c2), (end)) for a cubic curve."""
    pts = [start]
    for seg in segments:
        if isinstance(seg[0], (int, float)):
            pts.append(seg)
        else:
            pts.extend(bezier(pts[-1], seg[0], seg[1], seg[2]))
    return pts


def rotate(pts: Sequence[Point], deg: float, pivot: Point) -> List[Point]:
    if not deg:
        return list(pts)
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    px, py = pivot
    return [(px + (x - px) * c - (y - py) * s, py + (x - px) * s + (y - py) * c) for x, y in pts]


def shift(pts: Sequence[Point], dx: float = 0.0, dy: float = 0.0) -> List[Point]:
    return [(x + dx, y + dy) for x, y in pts]


# ----------------- Canvas -----------------
class Canvas:
    """A supersampled RGBA image addressed in design units, with a transform stack."""

    def __init__(self, scale: float):
        self.s = scale
        self.img = Image.new("RGBA", (max(1, round(W * scale)), max(1, round(H * scale))), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.img, "RGBA")
        self._tf: List[Callable[[List[Point]], List[Point]]] = []

    @contextmanager
    def transform(self, dx: float = 0.0, dy: float = 0.0, rot: float = 0.0,
                  pivot: Point = (0.0, 0.0)) -> Iterator[None]:
        def tf(pts: List[Point]) -> List[Point]:
            return shift(rotate(pts, rot, pivot), dx, dy)
        self._tf.append(tf)
        try:
            yield
        finally:
            self._tf.pop()

    def _px(self, pts: Sequence[Point]) -> List[Point]:
        pts = list(pts)
        for tf in reversed(self._tf):
            pts = tf(pts)
        return [(x * self.s, y * self.s) for x, y in pts]

    @staticmethod
    def _opaque(color: Optional[Color]) -> bool:
        return color is None or len(color) < 4 or color[3] >= 255

    def _layer(self, px: List[Point], pad: float):
        """A small transparent layer over the shape's box, for translucent paint:
        ImageDraw would otherwise blend into the alpha channel and punch holes."""
        xs = [p[0] for p in px]
        ys = [p[1] for p in px]
        left, top = int(min(xs) - pad) - 1, int(min(ys) - pad) - 1
        w, h = int(max(xs) + pad) - left + 2, int(max(ys) + pad) - top + 2
        layer = Image.new("RGBA", (max(1, w), max(1, h)), (0, 0, 0, 0))
        return layer, ImageDraw.Draw(layer), [(x - left, y - top) for x, y in px], (left, top)

    def _paste(self, layer: Image.Image, at: Tuple[int, int]) -> None:
        left, top = at
        box = (max(0, -left), max(0, -top))
        if box != (0, 0):
            layer = layer.crop((box[0], box[1], layer.width, layer.height))
            left, top = max(0, left), max(0, top)
        self.img.alpha_composite(layer, (left, top))

    def poly(self, pts: Sequence[Point], fill: Optional[Color], outline: Optional[Color] = INK,
             width: float = 1.0) -> None:
        px = self._px(pts)
        if len(px) < 3:
            return
        lw = max(1, round(width * self.s))
        if self._opaque(fill) and self._opaque(outline):
            draw, pts_px = self.draw, px
        else:
            layer, draw, pts_px, at = self._layer(px, lw)
        if fill is not None:
            draw.polygon(pts_px, fill=fill)
        if outline is not None and width > 0:
            draw.line(pts_px + [pts_px[0]], fill=outline, width=lw, joint="curve")
        if draw is not self.draw:
            self._paste(layer, at)

    def line(self, pts: Sequence[Point], color: Color = INK, width: float = 1.0) -> None:
        px = self._px(pts)
        if len(px) < 2:
            return
        lw = max(1, round(width * self.s))
        if self._opaque(color):
            draw, pts_px = self.draw, px
        else:
            layer, draw, pts_px, at = self._layer(px, lw)
        draw.line(pts_px, fill=color, width=lw, joint="curve")
        r = width * self.s / 2
        if r >= 1.5:  # round caps
            for x, y in (pts_px[0], pts_px[-1]):
                draw.ellipse((x - r, y - r, x + r, y + r), fill=color)
        if draw is not self.draw:
            self._paste(layer, at)

    def dot(self, x: float, y: float, r: float, fill: Color, outline: Optional[Color] = None,
            width: float = 0.8) -> None:
        self.poly(ellipse(x, y, r, r, n=24), fill, outline, width)

    def gradient(self, pts: Sequence[Point], top: Color, bottom: Color, y0: float, y1: float,
                 outline: Optional[Color] = INK, width: float = 1.0) -> None:
        """Polygon filled with a vertical gradient from y0 (top) to y1 (bottom)."""
        px = self._px(pts)
        xs = [p[0] for p in px]
        ys = [p[1] for p in px]
        left, top_px = int(min(xs)) - 1, int(min(ys)) - 1
        w, h = int(max(xs)) - left + 2, int(max(ys)) - top_px + 2
        if w <= 0 or h <= 0:
            return
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).polygon([(x - left, y - top_px) for x, y in px], fill=255)
        # Gradient positions in pixels of the (transformed) shape.
        g0 = self._px([(0, y0)])[0][1] - top_px
        g1 = self._px([(0, y1)])[0][1] - top_px
        ramp = Image.linear_gradient("L").resize((1, 256))
        span = max(1, int(abs(g1 - g0)))
        ramp = ramp.resize((1, span))
        g = Image.new("L", (1, h), 0)
        start = int(g0)
        if start > 0:
            g.paste(0, (0, 0, 1, min(h, start)))
        g.paste(ramp, (0, start))
        if start + span < h:
            g.paste(255, (0, max(0, start + span), 1, h))
        g = g.resize((w, h))
        layer = Image.composite(Image.new("RGBA", (w, h), bottom), Image.new("RGBA", (w, h), top), g)
        layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
        self.img.alpha_composite(layer, (left, top_px))
        if outline is not None and width > 0:
            self.draw.line(px + [px[0]], fill=outline, width=max(1, round(width * self.s)), joint="curve")


# ----------------- What to draw -----------------
@dataclass(frozen=True)
class Look:
    pose: str = "stand"          # stand, walk, sit, sleep, held, fall, land
    frame: int = 0               # animation frame of the pose
    expression: str = "neutral"  # one of avatar_protocol.EXPRESSIONS
    eyes: str = "open"           # open, blink, closed
    mouth: Optional[str] = None  # talk1, talk2 (overrides the expression's mouth)
    prop: Optional[str] = None   # pipe, tea, book, page-turn, hair-adjust, deduction, zzz
    prop_frame: int = 0
    gaze: float = 0.0            # -1..1, positive = towards where she faces
    tilt: float = 0.0            # head tilt in degrees


WALK_FRAMES = 6
POSES = ("stand", "walk", "sit", "sleep", "held", "fall", "land")
PROPS = ("pipe", "tea", "book", "page-turn", "hair-adjust", "deduction", "zzz")

# Expression -> (eye openness L/R, brow angle L/R, brow lift, mouth, blush 0-255, gaze)
EXPRESSION_FACE = {
    "neutral": ((0.62, 0.62), (0, 0), 0.0, "flat", 0, (0.0, 0.0)),
    "skeptical": ((0.48, 0.7), (-10, 12), 0.0, "slant", 0, (0.6, 0.0)),
    "annoyed": ((0.5, 0.5), (16, -16), 0.8, "pout", 40, (0.0, 0.0)),
    "concerned": ((0.8, 0.8), (-14, 14), -0.6, "frown", 0, (0.0, 0.2)),
    "happy": ((0.56, 0.56), (-4, 4), -0.8, "smile", 70, (0.0, 0.0)),
    "surprised": ((1.0, 1.0), (-6, 6), -2.6, "o", 0, (0.0, 0.0)),
    "embarrassed": ((0.7, 0.7), (-10, 10), -0.4, "wavy", 160, (-0.9, 0.3)),
    "focused": ((0.55, 0.55), (8, -8), 0.8, "flat", 0, (0.3, 0.6)),
    "sleepy": ((0.24, 0.24), (-3, 3), 0.3, "small", 20, (0.0, 0.4)),
    "deduction": ((0.74, 0.74), (6, -6), -0.8, "smug", 0, (0.4, 0.0)),
}


# ----------------- Parts -----------------
NECK: Point = (60.0, 73.0)


def _back_hair(c: Canvas, sway: float, lift: float) -> None:
    """The huge golden hair behind her, nearly to the floor."""
    def bx(x: float, y: float) -> Point:
        k = max(0.0, (y - 46) / 86)
        return (x + sway * k, y - lift * k)

    pts = path((60, 21), ((41, 19), (31, 31), (32, 46)),
               ((27, 70), (21, 98), (13, 127)))
    # Wavy curled ends.
    left, right = 13.0, 107.0
    n = 6
    for i in range(n):
        x0 = left + (right - left) * i / n
        x1 = left + (right - left) * (i + 1) / n
        pts.extend(bezier((x0, 127), (x0 + 2, 137.5), (x1 - 2, 137.5), (x1, 127), n=8))
    pts.extend(bezier((107, 127), (99, 98), (93, 70), (88, 46)))
    pts.extend(bezier((88, 46), (89, 31), (79, 19), (60, 21)))
    pts = [bx(x, y) for x, y in pts]
    c.gradient(pts, HAIR, HAIR_DARK, 30, 135, outline=HAIR_INK, width=1.0)
    # A few lighter strands for volume.
    for x0, x1 in ((30, 19), (36, 29), (90, 101), (84, 92)):
        strand = [bx(*p) for p in path((x0, 52), ((x0 - 3, 80), (x1 + 3, 100), (x1, 124)))]
        c.line(strand, HAIR_LIGHT, 1.1)


def _side_locks(c: Canvas, sway: float) -> None:
    for side in (-1, 1):
        x = 60 + side * 19.5
        tip = (60 + side * 22 + sway * 0.4, 101)
        pts = path((x - side * 4.5, 50),
                   ((x - side * 4, 66), (x - side * 0.5, 82), (tip[0] + side * 1.5, tip[1] - 6)),
                   ((tip[0] + side * 2.5, tip[1] - 2), (tip[0] - side * 0.5, tip[1] + 2), tip),
                   ((tip[0] + side * 3.2, tip[1] - 10), (x + side * 6, 76), (x + side * 3.5, 50)))
        c.gradient(pts, HAIR, HAIR_DARK, 50, 102, outline=HAIR_INK, width=0.9)
        c.line(path((x, 56), ((x - side * 0.5, 70), (x + side * 1.5, 84), (tip[0], 96))), HAIR_LIGHT, 0.8)


def _bonnet(c: Canvas) -> None:
    """Dark frilled headdress with lace and a wine ribbon."""
    outer = ellipse(60, 45, 29.5, 28.5, n=36, a0=math.radians(196), a1=math.radians(344))
    inner = ellipse(60, 45, 24.5, 23.0, n=36, a0=math.radians(344), a1=math.radians(196))
    c.poly(outer + inner, DRESS, INK, 1.0)
    c.line(ellipse(60, 45, 27, 25.8, n=30, a0=math.radians(200), a1=math.radians(340)), DRESS_LIGHT, 0.9)
    # Lace scallops along the inner edge.
    for i in range(11):
        a = math.radians(203 + i * 13.4)
        c.dot(60 + 24.2 * math.cos(a), 45 + 22.6 * math.sin(a) + 0.8, 2.1, LACE, LACE_SHADE, 0.6)
    # Ribbon bow on her right.
    bx, by = 84.5, 27.0
    c.poly([(bx, by), (bx + 8.5, by - 6.5), (bx + 9.5, by + 3.5)], WINE, INK, 0.9)
    c.poly([(bx, by), (bx - 6.5, by - 8.0), (bx - 8.0, by + 1.5)], WINE, INK, 0.9)
    c.poly([(bx - 1, by + 1), (bx + 2.5, by + 13), (bx + 5.5, by + 11.5), (bx + 1.5, by)], WINE_DARK, INK, 0.8)
    c.dot(bx, by, 2.4, WINE, INK, 0.8)


def _eye(c: Canvas, cx: float, cy: float, openness: float, gaze: Tuple[float, float],
         mode: str, happy: bool, mirror: int) -> None:
    rx, ry = 6.0, 6.9
    if mode in ("blink", "closed") or openness <= 0.05:
        if happy:
            c.line(path((cx - 5.5, cy + 1.5), ((cx - 3, cy - 3.2), (cx + 3, cy - 3.2), (cx + 5.5, cy + 1.5))), INK, 1.4)
        else:
            c.line(path((cx - 5.8, cy + 0.5), ((cx - 2.5, cy + 3.4), (cx + 2.5, cy + 3.4), (cx + 5.8, cy + 0.5))), INK, 1.4)
            c.line([(cx + mirror * 5.8, cy + 0.5), (cx + mirror * 7.4, cy - 0.6)], INK, 1.0)
        return
    gx, gy = gaze
    sclera = ellipse(cx, cy, rx, ry, n=32)
    c.poly(sclera, (255, 255, 255, 255), None)
    # Iris and pupil, kept inside the eye.
    ix, iy = cx + gx * 1.6, cy + 0.6 + gy * 1.2
    small = 0.82 if openness >= 0.99 else 1.0
    c.gradient(ellipse(ix, iy, 4.7 * small, 5.8 * small, n=28), IRIS_TOP, IRIS_BOTTOM,
               iy - 5.8, iy + 5.8, outline=(20, 56, 36, 255), width=0.6)
    c.dot(ix, iy + 0.4, 2.1 * small, PUPIL)
    c.dot(ix - 1.7, iy - 2.2, 1.45, (255, 255, 255, 255))
    c.dot(ix + 1.6, iy + 2.4, 0.7, (255, 255, 255, 235))
    # Upper lid: skin above the lid line, then the lash line.
    lid_y = cy - ry + (1 - openness) * 2 * ry * 0.82
    cover = [(cx - rx - 1.2, cy - ry - 2.5), (cx + rx + 1.2, cy - ry - 2.5),
             (cx + rx + 1.2, lid_y + 0.4)] + [(x, lid_y + 0.9 * math.sin(math.pi * (x - cx + rx) / (2 * rx)) * -1)
                                              for x in [cx + rx - i * rx / 6 for i in range(13)]] + [(cx - rx - 1.2, lid_y + 0.4)]
    c.poly(cover, SKIN, None)
    lash = [(x, lid_y - 0.9 * math.sin(math.pi * (x - cx + rx) / (2 * rx))) for x in
            [cx - rx + i * rx / 6 for i in range(13)]]
    c.line(lash, INK, 1.7)
    outer = cx + mirror * rx
    c.line([(outer, lid_y), (outer + mirror * 1.8, lid_y - 1.4)], INK, 1.1)
    c.line([(cx - rx * 0.6, cy + ry * 0.92), (cx + rx * 0.6, cy + ry * 0.92)], (150, 100, 100, 200), 0.6)


def _mouth(c: Canvas, kind: str) -> None:
    x, y = 60.0, 68.2
    if kind == "flat":
        c.line([(x - 2.4, y), (x + 2.4, y)], MOUTH, 0.9)
    elif kind == "small":
        c.line([(x - 1.4, y), (x + 1.4, y)], MOUTH, 0.9)
    elif kind == "slant":
        c.line([(x - 2.6, y + 0.6), (x + 2.6, y - 0.7)], MOUTH, 0.9)
    elif kind == "frown":
        c.line(path((x - 2.6, y + 0.8), ((x - 1.2, y - 0.9), (x + 1.2, y - 0.9), (x + 2.6, y + 0.8))), MOUTH, 0.9)
    elif kind == "smile":
        c.line(path((x - 2.8, y - 0.6), ((x - 1.2, y + 1.4), (x + 1.2, y + 1.4), (x + 2.8, y - 0.6))), MOUTH, 1.0)
    elif kind == "smug":
        c.line(path((x - 2.6, y + 0.2), ((x - 0.6, y + 1.0), (x + 1.6, y + 0.2), (x + 3.0, y - 1.2))), MOUTH, 1.0)
    elif kind == "pout":
        c.poly(ellipse(x, y + 0.3, 1.7, 1.1, n=16), MOUTH_IN, MOUTH, 0.6)
    elif kind == "wavy":
        c.line([(x - 2.8, y), (x - 1.4, y - 0.8), (x, y), (x + 1.4, y - 0.8), (x + 2.8, y)], MOUTH, 0.8)
    elif kind == "o":
        c.poly(ellipse(x, y + 0.4, 1.6, 2.1, n=18), MOUTH_IN, MOUTH, 0.7)
    elif kind == "talk1":
        c.poly(ellipse(x, y + 0.3, 2.3, 1.3, n=18), MOUTH_IN, MOUTH, 0.7)
    elif kind == "talk2":
        c.poly(ellipse(x, y + 0.5, 1.8, 2.2, n=18), MOUTH_IN, MOUTH, 0.7)
    else:
        c.line([(x - 2.4, y), (x + 2.4, y)], MOUTH, 0.9)


def _head(c: Canvas, look: Look) -> None:
    eyes_open, brows, lift, mouth, blush, gaze = EXPRESSION_FACE.get(look.expression, EXPRESSION_FACE["neutral"])
    gaze = (max(-1.0, min(1.0, gaze[0] + look.gaze)), gaze[1])
    # Cranium (hair) and face.
    c.gradient(ellipse(60, 44, 25.5, 24.5), HAIR_LIGHT, HAIR, 20, 60, outline=HAIR_INK, width=1.0)
    face = path((40.5, 50), ((40, 62), (48, 72.5), (60, 73)), ((72, 72.5), (80, 62), (79.5, 50)),
                ((79, 38), (41, 38), (40.5, 50)))
    c.poly(face, SKIN, INK, 1.0)
    c.poly(ellipse(60, 47, 19.5, 6, n=24, a0=math.pi, a1=2 * math.pi), SKIN_SHADE, None)
    if blush:
        for bx in (47.0, 73.0):
            c.poly(ellipse(bx, 64.5, 3.6, 1.9, n=20), BLUSH + (blush,), None)
            if blush > 120:
                for k in (-1.6, 0, 1.6):
                    c.line([(bx + k - 0.6, 65.4), (bx + k + 0.6, 63.6)], (220, 100, 116, 220), 0.5)
    happy = look.expression == "happy"
    mode = look.eyes
    _eye(c, 51.2, 58.2, eyes_open[0], gaze, mode, happy, -1)
    _eye(c, 68.8, 58.2, eyes_open[1], gaze, mode, happy, 1)
    c.line([(60.6, 63.2), (60.1, 64.1)], (214, 164, 150, 255), 0.7)
    _mouth(c, look.mouth or ("small" if mode == "closed" else mouth))
    # Bangs with pointed locks.
    bottom = [(83, 52), (78.5, 43.5), (75, 51), (70, 42.5), (65, 51.5), (60.5, 43), (56, 51.5),
              (51, 42.5), (46, 50.5), (42, 43.5), (37.5, 52)]
    top = ellipse(60, 44, 24.0, 22.8, n=30, a0=math.radians(178), a1=math.radians(362))
    c.gradient(top + bottom, HAIR_LIGHT, HAIR, 22, 52, outline=HAIR_INK, width=0.9)
    c.line([(52, 30), (48, 41)], HAIR_LIGHT, 1.0)
    c.line([(64, 29), (66, 40)], HAIR_LIGHT, 1.0)
    # Brows, drawn over the bangs as anime faces do.
    for (bx, ang, side) in ((51.0, brows[0], -1), (69.0, brows[1], 1)):
        by = 47.0 + lift
        pts = rotate([(bx - 3.4, by), (bx, by - 0.9), (bx + 3.4, by)], ang, (bx, by))
        c.line(pts, (128, 88, 42, 255), 1.0)
    _bonnet(c)


def _skirt(c: Canvas, top_y: float, hem_y: float, half_top: float, half_hem: float,
           sway: float, sitting: bool = False) -> None:
    lx, rx = 60 - half_hem + sway, 60 + half_hem + sway
    body = path((60 - half_top, top_y),
                (60 + half_top, top_y),
                ((60 + half_top + 6, top_y + 9), (rx - 3, hem_y - 12), (rx, hem_y)),
                (lx, hem_y),
                ((lx + 3, hem_y - 12), (60 - half_top - 6, top_y + 9), (60 - half_top, top_y)))
    c.gradient(body, DRESS, DRESS_LIGHT, top_y, hem_y + 4, outline=INK, width=1.0)
    for k in (-0.55, 0.0, 0.55):
        x0 = 60 + k * half_top * 1.4
        x1 = 60 + k * half_hem * 0.95 + sway
        c.line([(x0, top_y + 5), (x1, hem_y - 3)], DRESS_DARK, 0.9)
    # Wine ribbon and two tiers of lace at the hem.
    c.line([(lx + 2.2, hem_y - 4.2), (rx - 2.2, hem_y - 4.2)], WINE, 1.6)
    span = rx - lx
    n = max(6, int(span / 4.6))
    if not sitting:
        under = [(lx + 3, hem_y)]
        for i in range(n):
            x0 = lx + 3 + (span - 6) * i / n
            x1 = lx + 3 + (span - 6) * (i + 1) / n
            under.extend(bezier((x0, hem_y + 2), (x0, hem_y + 5.6), (x1, hem_y + 5.6), (x1, hem_y + 2), n=6))
        under.append((rx - 3, hem_y))
        c.poly(under, LACE_SHADE, INK, 0.8)
    lace = [(lx, hem_y - 2.6), (rx, hem_y - 2.6)]
    for i in range(n):
        x0 = rx - span * i / n
        x1 = rx - span * (i + 1) / n
        lace.extend(bezier((x0, hem_y + 1.2), (x0, hem_y + 4.4), (x1, hem_y + 4.4), (x1, hem_y + 1.2), n=6))
    c.poly(lace, LACE, INK, 0.8)
    for i in range(n):
        x = lx + span * (i + 0.5) / n
        c.dot(x, hem_y + 0.6, 0.55, LACE_SHADE)


def _bodice(c: Canvas) -> None:
    c.poly([(57.2, 66), (62.8, 66), (62.8, 75), (57.2, 75)], SKIN_SHADE, INK, 0.8)
    c.gradient([(50, 73.5), (70, 73.5), (72.5, 91), (47.5, 91)], DRESS_LIGHT, DRESS, 73, 91, outline=INK, width=1.0)
    # Collar and jabot.
    c.poly(ellipse(55.3, 75.4, 5.6, 3.3, n=22), LACE, INK, 0.8)
    c.poly(ellipse(64.7, 75.4, 5.6, 3.3, n=22), LACE, INK, 0.8)
    for y, r in ((79.6, 3.0), (82.8, 3.4), (86.2, 3.8)):
        c.poly(ellipse(60, y, r, 2.1, n=20), LACE, INK, 0.7)
    c.poly([(60, 77.4), (56, 75.2), (56.2, 79.4)], WINE, INK, 0.7)
    c.poly([(60, 77.4), (64, 75.2), (63.8, 79.4)], WINE, INK, 0.7)
    c.dot(60, 77.4, 1.5, WINE_DARK, INK, 0.6)


def _sleeve(c: Canvas, side: int) -> None:
    c.gradient(ellipse(60 + side * 12.6, 79.5, 5.8, 5.3, n=26), DRESS_LIGHT, DRESS, 74, 85, outline=INK, width=1.0)


def _arm(c: Canvas, side: int, angle: float, bend: float = 0.0, hand: Optional[Point] = None) -> Point:
    """Arm from the shoulder; `angle` swings it (positive = forward/outward for side)."""
    sx, sy = 60 + side * 12.6, 81.0
    length = 15.5
    a = math.radians(90 - side * 10 - side * angle)
    ex, ey = sx + math.cos(a) * length * 0.55, sy + math.sin(a) * length * 0.55
    b = a + math.radians(-side * bend)
    hx, hy = hand if hand else (ex + math.cos(b) * length * 0.5, ey + math.sin(b) * length * 0.5)
    sleeve = [(sx - 2.8, sy), (sx + 2.8, sy), (ex + 2.4, ey), (hx + 2.0, hy - 1.2), (hx - 2.0, hy - 1.2), (ex - 2.4, ey)]
    c.poly(sleeve, DRESS_LIGHT, INK, 1.0)
    c.line([(sx, sy + 1), (ex, ey), (hx, hy - 1.6)], DRESS, 0.9)
    c.poly(ellipse(hx, hy - 1.5, 3.0, 1.7, n=16), LACE, INK, 0.7)
    c.dot(hx, hy + 0.8, 2.5, SKIN, INK, 0.8)
    return (hx, hy)


def _legs(c: Canvas, lift_l: float, lift_r: float, fwd_l: float, fwd_r: float, top: float = 121.0) -> None:
    for x, lift, fwd in ((55.5, lift_l, fwd_l), (64.5, lift_r, fwd_r)):
        foot = FLOOR - 3.0 - lift
        c.poly([(x - 2.6, top), (x + 2.6, top), (x + 2.4 + fwd, foot), (x - 2.4 + fwd, foot)], STOCKING, INK, 0.8)
        shoe = path((x - 3.2 + fwd, foot - 0.4), ((x - 3.6 + fwd, foot + 3.4), (x + 4.8 + fwd, foot + 3.6), (x + 4.4 + fwd, foot)),
                    (x - 3.2 + fwd, foot - 0.4))
        c.poly(shoe, SHOE, INK, 0.7)
        c.line([(x - 2.4 + fwd, foot - 1.6), (x + 2.4 + fwd, foot - 1.6)], SHOE, 0.8)
        c.dot(x + 1.2 + fwd, foot + 0.6, 0.45, (200, 190, 196, 255))


# ----------------- Props -----------------
def _pipe(c: Canvas, frame: int, mouth: Point = (63.0, 68.6)) -> None:
    bowl = (83.5, 70.5)
    c.line(path(mouth, ((70, 70.5), (76, 72.5), (bowl[0] - 2.5, bowl[1] + 1.8))), INK, 2.3)
    c.line(path(mouth, ((70, 70.5), (76, 72.5), (bowl[0] - 2.5, bowl[1] + 1.8))), PIPE_STEM, 1.3)
    cup = path((bowl[0] - 3.2, bowl[1] - 3.2), (bowl[0] + 3.2, bowl[1] - 3.2),
               ((bowl[0] + 3.4, bowl[1] + 2), (bowl[0] + 1.5, bowl[1] + 4.2), (bowl[0], bowl[1] + 4.2)),
               ((bowl[0] - 1.5, bowl[1] + 4.2), (bowl[0] - 3.4, bowl[1] + 2), (bowl[0] - 3.2, bowl[1] - 3.2)))
    c.poly(cup, PIPE_BOWL, INK, 0.8)
    c.poly(ellipse(bowl[0], bowl[1] - 3.2, 3.2, 1.0, n=16), (70, 40, 26, 255), INK, 0.6)
    _smoke(c, bowl[0], bowl[1] - 5, frame)


def _smoke(c: Canvas, x: float, y: float, frame: int) -> None:
    for k in range(3):
        t = ((frame + k * 2) % 6) / 6.0
        alpha = int(200 * (1 - t))
        c.poly(ellipse(x + math.sin(t * 5 + k) * 2.2, y - t * 18, 1.6 + t * 2.6, 1.4 + t * 2.0, n=18),
               SMOKE + (alpha,), None)


def _book(c: Canvas, cx: float, cy: float, frame: int = 0, turning: bool = False, closed: bool = False) -> None:
    if closed:
        c.poly([(cx - 8, cy - 2), (cx + 8, cy - 2), (cx + 9, cy + 3.5), (cx - 9, cy + 3.5)], BOOK_COVER, INK, 0.9)
        c.line([(cx - 7.5, cy - 0.6), (cx + 7.5, cy - 0.6)], PAGE, 0.9)
        return
    c.poly([(cx - 10.5, cy - 5), (cx + 10.5, cy - 5), (cx + 11.5, cy + 3.8), (cx - 11.5, cy + 3.8)], BOOK_COVER, INK, 0.9)
    c.poly([(cx - 9.8, cy - 6.2), (cx - 0.4, cy - 5), (cx - 0.4, cy + 2.8), (cx - 10.6, cy + 2.4)], PAGE, INK, 0.7)
    c.poly([(cx + 0.4, cy - 5), (cx + 9.8, cy - 6.2), (cx + 10.6, cy + 2.4), (cx + 0.4, cy + 2.8)], PAGE, INK, 0.7)
    for i in range(3):
        y = cy - 3.4 + i * 2.0
        c.line([(cx - 8.2, y), (cx - 2.0, y + 0.3)], (190, 176, 160, 255), 0.5)
        c.line([(cx + 2.0, y + 0.3), (cx + 8.2, y)], (190, 176, 160, 255), 0.5)
    if turning:
        t = (frame % 6) / 5.0
        tip_x = cx + 9.8 - 19.6 * t
        lift = math.sin(t * math.pi) * 4.5
        c.poly([(cx, cy - 5), (tip_x, cy - 6.2 - lift), (tip_x + (0.8 if t < 0.5 else -0.8), cy + 2.4 - lift), (cx, cy + 2.8)],
               (255, 250, 236, 255), INK, 0.6)


def _tea(c: Canvas, cx: float, cy: float, frame: int) -> None:
    c.poly(ellipse(cx, cy + 3.2, 5.2, 1.4, n=20), LACE, INK, 0.7)
    cup = path((cx - 3.6, cy - 2.4), (cx + 3.6, cy - 2.4), ((cx + 3.4, cy + 1.6), (cx + 1.6, cy + 2.8), (cx, cy + 2.8)),
               ((cx - 1.6, cy + 2.8), (cx - 3.4, cy + 1.6), (cx - 3.6, cy - 2.4)))
    c.poly(cup, LACE, INK, 0.7)
    c.line([(cx - 3.2, cy - 0.6), (cx + 3.2, cy - 0.6)], WINE, 0.6)
    c.line(path((cx + 3.4, cy - 1.4), ((cx + 6, cy - 1.6), (cx + 6, cy + 1.6), (cx + 3.0, cy + 1.2))), INK, 0.8)
    _smoke(c, cx, cy - 3.5, frame)


def _sparkles(c: Canvas, frame: int) -> None:
    spots = ((30, 30, 0), (92, 40, 2), (86, 14, 4), (26, 58, 1))
    for x, y, phase in spots:
        r = 1.2 + 2.4 * abs(math.sin((frame + phase) * math.pi / 4))
        star = []
        for i in range(8):
            a = i * math.pi / 4
            rr = r if i % 2 == 0 else r * 0.32
            star.append((x + rr * math.cos(a), y + rr * math.sin(a)))
        c.poly(star, SPARK, (214, 160, 40, 255), 0.5)


def _zzz(c: Canvas, frame: int) -> None:
    for k in range(3):
        t = ((frame + k * 3) % 9) / 9.0
        size = 2.4 + k * 0.9 + t * 1.2
        x = 84 + k * 5 + math.sin(t * 6) * 1.5
        y = 38 - k * 8 - t * 6
        alpha = int(255 * (1 - t * 0.7))
        col = (96, 84, 140, alpha)
        c.line([(x - size, y - size), (x + size, y - size), (x - size, y + size), (x + size, y + size)], col, 1.0)


# ----------------- Poses -----------------
def _figure(c: Canvas, look: Look) -> None:
    pose = look.pose
    prop = look.prop
    f = look.frame

    if pose in ("sit", "sleep"):
        _sitting(c, look)
        return

    held = pose in ("held", "fall")
    walking = pose == "walk"
    phase = 2 * math.pi * (f % WALK_FRAMES) / WALK_FRAMES
    bob = -abs(math.sin(phase)) * 1.4 if walking else (-0.5 if (pose == "stand" and f % 2) else 0.0)
    squash = 1.6 if pose == "land" else 0.0
    sway = (-3.0 + math.sin(phase) * 1.2) if walking else 0.0
    lift = 6.0 if pose == "fall" else 0.0

    _back_hair(c, sway, lift)
    if held:
        _legs(c, 0.0, 0.0, -0.6, 0.6, top=118.0)
    elif walking:
        _legs(c, max(0.0, math.sin(phase)) * 3.0, max(0.0, -math.sin(phase)) * 3.0,
              max(0.0, math.sin(phase)) * 1.2, max(0.0, -math.sin(phase)) * 1.2)
    else:
        _legs(c, 0.0, 0.0, 0.0, 0.0)

    with c.transform(dy=bob + squash):
        _skirt(c, 89.0, 121.0 if not held else 118.0, 12.0, 30.0 if not held else 26.0,
               math.sin(phase) * 0.8 if walking else 0.0)
        _bodice(c)
        _side_locks(c, sway)
        # Arms: some props need them in front of the body.
        if held:
            left_hand = _arm(c, -1, 150 if pose == "fall" else 128, bend=-20)
            right_hand = _arm(c, 1, 150 if pose == "fall" else 128, bend=-20)
        else:
            swing = math.sin(phase) * 12 if walking else 0.0
            if prop == "hair-adjust":
                _arm(c, -1, 128, bend=-50)
            elif prop in ("book", "page-turn"):
                _arm(c, -1, 30, hand=(51.0, 95.0))
            else:
                _arm(c, -1, -swing)
            if prop == "pipe":
                _arm(c, 1, 120, hand=(66.5, 71.5))
            elif prop == "tea":
                _arm(c, 1, 60, hand=(67.0, 88.5))
            elif prop in ("book", "page-turn"):
                _arm(c, 1, 30, hand=(69.0, 95.0))
            else:
                _arm(c, 1, swing)
        _sleeve(c, -1)
        _sleeve(c, 1)

        with c.transform(rot=look.tilt, pivot=NECK):
            _head(c, look)
            if prop == "pipe":
                _pipe(c, look.prop_frame)
                c.poly(ellipse(70.5, 71.4, 3.0, 1.7, n=16), LACE, INK, 0.7)
                c.dot(70.2, 72.6, 2.5, SKIN, INK, 0.8)
        if prop == "hair-adjust":
            c.dot(41.5, 62.0, 2.3, SKIN, INK, 0.7)
        if prop in ("book", "page-turn"):
            _book(c, 60.0, 93.5, look.prop_frame, turning=prop == "page-turn")
        if prop == "tea":
            _tea(c, 68.0, 85.0, look.prop_frame)
    if prop == "deduction" or look.expression == "deduction":
        _sparkles(c, look.prop_frame)
    if prop == "zzz":
        _zzz(c, look.prop_frame)


def _sitting(c: Canvas, look: Look) -> None:
    """Seated on the floor with the skirt spread, reading (or dozing)."""
    sleeping = look.pose == "sleep"
    drop = 19.0
    breathe = 0.5 if (look.frame % 2) else 0.0
    with c.transform(dy=drop):
        _back_hair(c, 0.0, 10.5)
    with c.transform(dy=drop):
        # Spread skirt: wide and low.
        _skirt(c, 89.0, 125.0, 12.5, 37.0, 0.0, sitting=True)
        for x in (52.0, 68.0):  # shoes peeking out
            c.poly(path((x - 3.6, 125.5), ((x - 4.0, 129.5), (x + 4.0, 129.5), (x + 3.6, 125.5))), SHOE, INK, 0.7)
    with c.transform(dy=drop + breathe):
        _bodice(c)
        _side_locks(c, 0.0)
        if sleeping:
            _arm(c, -1, 25, hand=(53.0, 98.0))
            _arm(c, 1, 25, hand=(67.0, 98.0))
        else:
            _arm(c, -1, 30, hand=(51.5, 94.0))
            _arm(c, 1, 30, hand=(68.5, 94.0))
        _sleeve(c, -1)
        _sleeve(c, 1)
        tilt = look.tilt or (11.0 if sleeping else 3.0)
        head_look = Look(pose=look.pose, expression=look.expression,
                         eyes="closed" if sleeping else look.eyes, mouth=look.mouth,
                         gaze=look.gaze, tilt=tilt)
        with c.transform(dy=1.5 if sleeping else 0.0, rot=tilt, pivot=NECK):
            _head(c, head_look)
        if sleeping:
            _book(c, 60.0, 99.0, closed=True)
        else:
            _book(c, 60.0, 92.5, look.prop_frame, turning=look.prop == "page-turn")
    if sleeping or look.prop == "zzz":
        _zzz(c, look.prop_frame)


# ----------------- Public API -----------------
def size_for(height_px: int) -> Tuple[int, int]:
    height_px = max(40, int(height_px))
    return max(1, round(W * height_px / H)), height_px


@lru_cache(maxsize=192)
def render(look: Look, height_px: int) -> Image.Image:
    """RGBA image of the figure, facing right; feet at the bottom edge."""
    width, height = size_for(height_px)
    scale = height / H * SUPERSAMPLE
    canvas = Canvas(scale)
    _figure(canvas, look)
    return canvas.img.resize((width, height), Image.LANCZOS)


@lru_cache(maxsize=192)
def render_facing(look: Look, height_px: int, facing: int) -> Image.Image:
    img = render(look, height_px)
    return ImageOps.mirror(img) if facing < 0 else img


def feet_offset(height_px: int) -> int:
    """Pixels from the bottom of the image to the soles (they rest on the floor)."""
    return max(0, round((H - FLOOR - 0.6) * height_px / H))
