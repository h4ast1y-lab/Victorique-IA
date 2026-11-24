"""
Speech balloon above the mascot, drawn with Pillow (no web view).

`render_balloon` returns the image plus the clickable areas of its buttons,
in pixels of that image. Text between asterisks (*a gesture*) is set in
italics, as in the chat. Long text is cut with an ellipsis; the full reply
lives in the chat window.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(r"C:\Windows\Fonts")
FONTS = {
    "regular": ("segoeui.ttf", "arial.ttf"),
    "bold": ("seguisb.ttf", "segoeuib.ttf", "arialbd.ttf"),
    "italic": ("segoeuii.ttf", "ariali.ttf"),
}

BG = (30, 27, 36, 246)
BORDER = (214, 178, 104, 255)
TEXT = (240, 234, 242, 255)
MUTED = (176, 166, 186, 255)
ACTION = (196, 178, 220, 255)
CASE_BG = (46, 40, 56, 255)
PRIMARY = (226, 190, 112, 255)
PRIMARY_HOVER = (240, 208, 138, 255)
PRIMARY_TEXT = (36, 28, 24, 255)
SECONDARY = (58, 52, 68, 255)
SECONDARY_HOVER = (78, 70, 90, 255)

WIDTH = 272          # logical px
PAD = 12
MAX_LINES = 8
TAIL_H = 10
Rect = Tuple[int, int, int, int]


@dataclass(frozen=True)
class Button:
    id: str
    label: str
    primary: bool = False


@dataclass(frozen=True)
class Bubble:
    text: str
    name: str = "Victorique"
    tag: str = ""
    case_title: Optional[str] = None
    buttons: Tuple[Button, ...] = field(default_factory=tuple)


@lru_cache(maxsize=24)
def _font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for name in FONTS[kind]:
        path = FONT_DIR / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size)


_MD = [
    (re.compile(r"```.*?```", re.S), " (código) "),
    (re.compile(r"`([^`]*)`"), r"\1"),
    (re.compile(r"\*\*([^*]+)\*\*"), r"\1"),
    (re.compile(r"!\[[^\]]*\]\([^)]*\)"), ""),
    (re.compile(r"\[([^\]]+)\]\([^)]*\)"), r"\1"),
    (re.compile(r"^#{1,6}\s*", re.M), ""),
    (re.compile(r"^\s*[-*+]\s+", re.M), "• "),
]


def plain_text(markdown: str) -> str:
    """Rough Markdown-to-text for a short excerpt of a chat reply."""
    text = markdown or ""
    for pattern, repl in _MD:
        text = pattern.sub(repl, text)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{2,}", "\n", text)).strip()


def _runs(text: str) -> List[Tuple[str, bool]]:
    """(word-or-newline, italic) tokens; *asterisks* mark italics."""
    out: List[Tuple[str, bool]] = []
    for i, part in enumerate(re.split(r"\*([^*\n]+)\*", text)):
        italic = i % 2 == 1
        for j, line in enumerate(part.split("\n")):
            if j:
                out.append(("\n", italic))
            out.extend((word, italic) for word in line.split())
    return out


def wrap(text: str, width: int, size: int) -> List[List[Tuple[str, bool]]]:
    regular, italic = _font("regular", size), _font("italic", size)
    lines: List[List[Tuple[str, bool]]] = [[]]
    used = 0.0
    space = regular.getlength(" ")
    for word, it in _runs(text):
        if word == "\n":
            lines.append([])
            used = 0.0
            continue
        font = italic if it else regular
        w = font.getlength(word)
        gap = space if lines[-1] else 0.0
        if lines[-1] and used + gap + w > width:
            lines.append([])
            used, gap = 0.0, 0.0
        while w > width and len(word) > 1:  # a very long word (a path): break it
            cut = len(word)
            while cut > 1 and font.getlength(word[:cut]) > width - used:
                cut -= 1
            lines[-1].append((word[:cut], it))
            lines.append([])
            word, used = word[cut:], 0.0
            w = font.getlength(word)
        lines[-1].append((word, it))
        used += gap + w
    return [line for line in lines if line] or [[("", False)]]


def render_balloon(bubble: Bubble, scale: float = 1.0, hover: Optional[str] = None,
                   tail_at: float = 0.5) -> Tuple[Image.Image, Dict[str, Rect]]:
    """The balloon image and {button id: rect} (with "close" for the ×).
    `tail_at` (0..1) places the tail that points down at her head."""
    s = max(0.75, scale)
    width = round(WIDTH * s)
    pad = round(PAD * s)
    body_size = round(13 * s)
    small = round(11 * s)
    inner = width - 2 * pad
    lines = wrap(bubble.text, inner, body_size)
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES]
        lines[-1] = lines[-1] + [("…", False)]
    line_h = round(body_size * 1.38)
    header_h = round(18 * s)
    case_h = round(40 * s) if bubble.case_title else 0
    button_h = round(26 * s) if bubble.buttons else 0
    gap = round(8 * s)
    height = pad + header_h + gap // 2 + len(lines) * line_h + (gap + case_h if case_h else 0) \
        + (gap + button_h if button_h else 0) + pad
    tail = round(TAIL_H * s)
    img = Image.new("RGBA", (width, height + tail), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    radius = round(12 * s)
    border = max(1, round(1.2 * s))
    d.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=BG, outline=BORDER, width=border)
    tx = min(max(round(width * tail_at), radius + tail), width - radius - tail)
    d.polygon([(tx - tail, height - 1 - border), (tx + tail, height - 1 - border), (tx, height + tail - 1)], fill=BG)
    d.line([(tx - tail, height - 1), (tx, height + tail - 1), (tx + tail, height - 1)], fill=BORDER, width=border)

    rects: Dict[str, Rect] = {}
    y = pad
    bold = _font("bold", round(12.5 * s))
    d.text((pad, y), bubble.name, font=bold, fill=PRIMARY)
    if bubble.tag:
        d.text((pad + bold.getlength(bubble.name) + round(6 * s), y + round(1.5 * s)), bubble.tag,
               font=_font("regular", small), fill=MUTED)
    cx = width - pad - round(6 * s)
    cy = y + round(8 * s)
    r = round(4.5 * s)
    close_color = TEXT if hover == "close" else MUTED
    d.line([(cx - r, cy - r), (cx + r, cy + r)], fill=close_color, width=max(1, round(1.4 * s)))
    d.line([(cx - r, cy + r), (cx + r, cy - r)], fill=close_color, width=max(1, round(1.4 * s)))
    hit = round(11 * s)
    rects["close"] = (cx - hit, cy - hit, cx + hit, cy + hit)
    y += header_h + gap // 2

    regular, italic = _font("regular", body_size), _font("italic", body_size)
    space = regular.getlength(" ")
    for line in lines:
        x = float(pad)
        for k, (word, it) in enumerate(line):
            font = italic if it else regular
            if k:
                x += space
            d.text((x, y), word, font=font, fill=ACTION if it else TEXT)
            x += font.getlength(word)
        y += line_h

    if case_h:
        y += gap
        d.rounded_rectangle((pad, y, width - pad, y + case_h), radius=round(7 * s), fill=CASE_BG)
        d.text((pad + round(9 * s), y + round(5 * s)), "Caso proposto", font=_font("regular", small), fill=MUTED)
        title = bubble.case_title or ""
        title_font = _font("bold", round(12.5 * s))
        while title and title_font.getlength(title) > inner - round(18 * s):
            title = title[:-2].rstrip() + "…"
        d.text((pad + round(9 * s), y + round(19 * s)), title, font=title_font, fill=TEXT)
        y += case_h

    if button_h:
        y += gap
        label_font = _font("bold", round(12 * s))
        x = width - pad
        for button in reversed(bubble.buttons):
            bw = round(label_font.getlength(button.label) + 22 * s)
            x0 = x - bw
            if button.primary:
                fill, color = (PRIMARY_HOVER if hover == button.id else PRIMARY), PRIMARY_TEXT
            else:
                fill, color = (SECONDARY_HOVER if hover == button.id else SECONDARY), TEXT
            d.rounded_rectangle((x0, y, x, y + button_h), radius=round(7 * s), fill=fill)
            tw = label_font.getlength(button.label)
            d.text((x0 + (bw - tw) / 2, y + (button_h - label_font.size * 1.33) / 2), button.label,
                   font=label_font, fill=color)
            rects[button.id] = (x0, y, x, y + button_h)
            x = x0 - round(6 * s)
    return img, rects
