"""
Builds the desktop mascot's sprite atlas from the sheets in
app/mascot/assets/source/ (one animation per sheet, frames side by side).

    .venv\\Scripts\\python.exe scripts\\build_mascot_sprites.py [--debug DIR]

Writes app/mascot/assets/victorique.webp (all frames packed) and
victorique.json (where each frame is, plus its anchor: the point that sits on
her position, usually the soles). Run it again after changing a sheet; the
app only reads the two output files.

What it does to each sheet: removes the background (transparent sheets are
thresholded on alpha; white ones are flood-filled from the border), removes
the floor shadows of the jump and fall sheets, cuts the frames at the
emptiest columns near the even grid, puts every sheet on the same scale (the
sheets draw her at different sizes) and finds each frame's anchor.

--source DIR reads sheets made by postprocess_sprites.py instead (already cut
out, on one pixel grid and one scale, so nothing is resampled here).

--debug DIR also writes a contact sheet per animation with the anchors marked
and a line-up of one frame of each animation at the common scale.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app" / "mascot" / "assets" / "source"
ORIGINAL = SOURCE       # the hand-tuned sheets, the fallback for --source
OUT_IMAGE = ROOT / "app" / "mascot" / "assets" / "victorique.webp"
OUT_JSON = ROOT / "app" / "mascot" / "assets" / "victorique.json"

STAND_HEIGHT = 240      # standing figure height in the atlas, in px
PREPARED = False        # sheets already cut out and scaled (--source)


def is_prepared(sheet: "Sheet") -> bool:
    """This sheet comes from the --source folder (a sheet missing there falls
    back to the original one in assets/source, cut and scaled as before)."""
    return PREPARED and (SOURCE / sheet.file).exists()
POOL = 4                # labeling runs on a 4x4 max-pooled mask
MIN_PART = 4            # pooled cells; smaller specks are noise


@dataclass
class Sheet:
    anim: str
    file: str
    rows: int
    cols: int
    background: str         # "alpha" (threshold) or "white" (flood fill)
    threshold: int = 128
    white_low: int = 228    # white sheets: lightest grey still counted as background
    facing: str = "front"   # which way the drawing faces: left, right, front
    anchor_x: str = "hem"   # hem, head, left, right, cursor
    anchor_y: str = "base"  # base (sheet floor line), self (own bottom), seat, cursor
    ref: Tuple[int, ...] = (0,)   # frame(s) whose height is her standing height
    ref_height: Optional[float] = None   # or that height given directly (sheet px)
    shadow: bool = False
    main_only: bool = False  # keep only each frame's biggest part (drops effect marks)


SHEETS: List[Sheet] = [
    Sheet("walk", "01-andar.webp", 1, 6, "alpha", facing="left", anchor_x="head"),
    Sheet("moods", "02-humores.webp", 1, 6, "alpha"),
    Sheet("talk", "03-falar.webp", 1, 6, "alpha"),
    Sheet("blink", "04-piscar.webp", 1, 6, "alpha"),
    Sheet("sit_down", "05-sentar.webp", 1, 6, "alpha"),
    Sheet("sitting", "06-sentada.webp", 1, 6, "alpha", ref_height=544.0),
    Sheet("turn", "07-virar.webp", 1, 6, "alpha", ref=(2,)),
    Sheet("stand_up", "08-levantar.webp", 1, 6, "alpha", ref=(5,)),
    Sheet("held", "09-arrastada.webp", 2, 6, "white", white_low=195, facing="right",
          anchor_x="cursor", anchor_y="cursor"),
    Sheet("jump", "10-pular.webp", 1, 8, "alpha", threshold=215, facing="right",
          anchor_y="self"),
    Sheet("fall", "11-cair.webp", 1, 8, "alpha", threshold=215, facing="right",
          anchor_y="self", ref=(7,), shadow=True),
    Sheet("climb", "12-escalar.webp", 2, 6, "alpha", facing="right", anchor_x="right",
          ref_height=330.0),
    Sheet("edge", "13-beirada.webp", 1, 12, "alpha", anchor_y="seat", ref_height=327.0),
    # Hidden behind an edge on her left, leaning out to the right.
    Sheet("peek", "14-espiar.webp", 1, 9, "alpha", facing="right", anchor_x="left",
          ref_height=470.0),
    Sheet("tea", "15-cha.webp", 1, 12, "white"),
    Sheet("read", "16-ler.webp", 1, 12, "white"),
    Sheet("close_book", "17-fechar-livro.webp", 1, 6, "white"),
    Sheet("glance", "18-olhar.webp", 1, 6, "alpha"),
    Sheet("think", "19-pensar.webp", 1, 6, "alpha"),
    Sheet("doze", "20-cochilar.webp", 1, 6, "alpha"),
    # Second batch (2026-11-24): expressions and reactions. Generated over
    # white and cut out, so they are flood-filled like the white sheets.
    Sheet("happy", "21-feliz.webp", 1, 6, "white", white_low=215),
    Sheet("point", "22-apontar.webp", 1, 6, "white", white_low=215),
    Sheet("confused", "23-confusa.webp", 1, 6, "white", white_low=215),
    Sheet("surprised", "24-surpresa.webp", 1, 6, "white", white_low=215),
    Sheet("sigh", "25-suspirar.webp", 1, 8, "white", white_low=215),
    Sheet("wake", "26-despertar.webp", 1, 8, "white", white_low=215),
    # Stamping her feet; frames 3-5 are in the air, so the floor line is the
    # sheet's own (the motion marks under her feet are dropped).
    Sheet("tantrum", "27-birra.webp", 1, 8, "white", white_low=215, facing="right",
          main_only=True),
]


# ----------------- Masks -----------------
def flood_background(rgb: np.ndarray, *, low: int = 228, spread: int = 14) -> np.ndarray:
    """True where the pixel is near-white background reachable from the border."""
    bgish = (rgb.min(-1) >= low) & ((rgb.max(-1) - rgb.min(-1)) <= spread)
    # copy(): an image made by fromarray shares the array, and floodfill
    # writes would not land on it.
    im = Image.fromarray(np.where(bgish, 255, 0).astype("uint8")).copy()
    h, w = bgish.shape
    seeds = [(x, 0) for x in range(0, w, 16)] + [(x, h - 1) for x in range(0, w, 16)]
    seeds += [(0, y) for y in range(0, h, 16)] + [(w - 1, y) for y in range(0, h, 16)]
    for seed in seeds:
        if im.getpixel(seed) == 255:
            ImageDraw.floodfill(im, seed, 128)
    return np.asarray(im) == 128


def sheet_mask(sheet: Sheet, img: Image.Image) -> Tuple[np.ndarray, np.ndarray]:
    """(mask, rgba) of the whole sheet."""
    rgba = np.asarray(img.convert("RGBA")).astype(np.int16)
    if sheet.background == "alpha":
        mask = rgba[..., 3] > sheet.threshold
    else:
        # Over white, so a semi-transparent white halo reads as background too.
        alpha = rgba[..., 3:4] / 255.0
        rgb = (rgba[..., :3] * alpha + 255 * (1 - alpha)).astype(np.int16)
        mask = ~flood_background(rgb, low=sheet.white_low)
    if sheet.shadow:
        mask &= ~shadow_pixels(rgba, mask)
    return mask, rgba


def shadow_pixels(rgba: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """The flat grey floor shadow of the fall sheet: its exact colour, low down."""
    rgb = rgba[..., :3]
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    grey = (r >= 84) & (r <= 110) & (g >= 81) & (g <= 106) & (b >= 84) & (b <= 110)
    grey &= (np.abs(r - b) <= 6) & ((r - g) >= -2) & ((r - g) <= 8)
    rows = np.nonzero(mask.any(axis=1))[0]
    floor = rows.max() if len(rows) else mask.shape[0]
    band = np.zeros_like(mask)
    band[max(0, floor - 30):] = True
    return grey & band


def label(mask: np.ndarray) -> Tuple[np.ndarray, int]:
    """4-connected components (pure Python; masks here are pooled and small)."""
    h, w = mask.shape
    lab = np.zeros((h, w), dtype=np.int32)
    grid = mask.tolist()
    n = 0
    for y in range(h):
        for x in range(w):
            if grid[y][x] and not lab[y, x]:
                n += 1
                lab[y, x] = n
                queue = deque([(y, x)])
                while queue:
                    cy, cx = queue.popleft()
                    for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                        if 0 <= ny < h and 0 <= nx < w and grid[ny][nx] and not lab[ny, nx]:
                            lab[ny, nx] = n
                            queue.append((ny, nx))
    return lab, n


def drop_specks(mask: np.ndarray) -> np.ndarray:
    h, w = mask.shape
    ph, pw = h // POOL, w // POOL
    pooled = mask[: ph * POOL, : pw * POOL].reshape(ph, POOL, pw, POOL).any(axis=(1, 3))
    lab, n = label(pooled)
    if not n:
        return mask
    sizes = np.bincount(lab.ravel(), minlength=n + 1)
    keep = sizes >= MIN_PART
    keep[0] = False
    kept = keep[lab]
    full = np.zeros_like(mask)
    full[: ph * POOL, : pw * POOL] = np.repeat(np.repeat(kept, POOL, axis=0), POOL, axis=1)
    return mask & full


def biggest_part(mask: np.ndarray) -> np.ndarray:
    """The largest connected part of `mask` (labelled on the pooled grid)."""
    h, w = mask.shape
    ph, pw = h // POOL, w // POOL
    if not ph or not pw:
        return mask
    pooled = mask[: ph * POOL, : pw * POOL].reshape(ph, POOL, pw, POOL).any(axis=(1, 3))
    lab, n = label(pooled)
    if n <= 1:
        return mask
    sizes = np.bincount(lab.ravel(), minlength=n + 1)
    sizes[0] = 0
    kept = lab == int(np.argmax(sizes))
    full = np.zeros_like(mask)
    full[: ph * POOL, : pw * POOL] = np.repeat(np.repeat(kept, POOL, axis=0), POOL, axis=1)
    return mask & full


def dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    out = mask.copy()
    for _ in range(radius):
        grown = out.copy()
        grown[1:] |= out[:-1]
        grown[:-1] |= out[1:]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        out = grown
    return out


def cuts(profile: np.ndarray, parts: int, window: int) -> List[int]:
    """Boundaries splitting `profile` into `parts`, each moved to the emptiest
    position within `window` of the even grid."""
    size = len(profile)
    out = [0]
    for k in range(1, parts):
        nominal = round(k * size / parts)
        lo, hi = max(1, nominal - window), min(size - 1, nominal + window)
        segment = profile[lo:hi]
        best = np.flatnonzero(segment == segment.min())
        # among the emptiest columns, the one closest to the grid line
        pick = lo + best[np.argmin(np.abs(best + lo - nominal))]
        out.append(int(pick))
    out.append(size)
    return out


# ----------------- Frames -----------------
@dataclass
class Frame:
    image: Image.Image      # cropped, at sheet scale
    box: Tuple[int, int, int, int]   # in sheet coordinates
    mask: np.ndarray        # cropped


def frames_of(sheet: Sheet) -> List[List[Frame]]:
    if is_prepared(sheet):
        sheet = replace(sheet, background="alpha", threshold=128, shadow=False)
        img = Image.open(SOURCE / sheet.file)
    else:
        if PREPARED:
            print(f"  {sheet.file}: not in {SOURCE.name}/, using the original sheet")
        img = Image.open(ORIGINAL / sheet.file)
    mask, rgba = sheet_mask(sheet, img)
    mask = drop_specks(mask)
    h, w = mask.shape
    row_cuts = cuts(mask.sum(axis=1), sheet.rows, h // (sheet.rows * 4)) if sheet.rows > 1 else [0, h]
    rows: List[List[Frame]] = []
    for r in range(sheet.rows):
        y0, y1 = row_cuts[r], row_cuts[r + 1]
        band = mask[y0:y1]
        col_cuts = cuts(band.sum(axis=0), sheet.cols, w // (sheet.cols * 3))
        row: List[Frame] = []
        for c in range(sheet.cols):
            x0, x1 = col_cuts[c], col_cuts[c + 1]
            cell = band[:, x0:x1].copy()
            if sheet.main_only:
                cell &= biggest_part(cell)
            ys, xs = np.nonzero(cell)
            if not len(ys):
                raise SystemExit(f"{sheet.file}: empty frame at row {r}, column {c}")
            bx0, bx1 = x0 + xs.min(), x0 + xs.max() + 1
            by0, by1 = y0 + ys.min(), y0 + ys.max() + 1
            # only this cell's pixels (a neighbour may poke into the box)
            crop_mask = cell[ys.min():ys.max() + 1, xs.min():xs.max() + 1].copy()
            pixels = rgba[by0:by1, bx0:bx1].copy()
            pixels[..., 3] = np.where(crop_mask, 255, 0)
            image = Image.fromarray(pixels.astype("uint8"), "RGBA")
            row.append(Frame(image, (int(bx0), int(by0), int(bx1), int(by1)), crop_mask))
        rows.append(row)
    return rows


def extent(mask: np.ndarray, rows: slice) -> Tuple[float, float]:
    cols = np.nonzero(mask[rows].any(axis=0))[0]
    if not len(cols):
        cols = np.nonzero(mask.any(axis=0))[0]
    return float(cols.min()), float(cols.max() + 1)


def cursor_tip(frame: Frame) -> Tuple[float, float]:
    """Top vertex of the white arrow cursor drawn in the dragged sheet."""
    ys, xs = np.nonzero(cursor_patch(frame))
    top = ys.min()
    x = xs[ys <= top + 2].min()
    return float(x) - 2.0, float(top) - 3.0


def cursor_patch(frame: Frame) -> np.ndarray:
    """The white inside of the arrow cursor drawn in the dragged sheet."""
    px = np.asarray(frame.image).astype(np.int16)
    rgb = px[..., :3]
    white = (rgb.min(-1) >= 238) & ((rgb.max(-1) - rgb.min(-1)) <= 10) & frame.mask
    h, w = white.shape
    white[:, : int(w * 0.55)] = False      # the cursor is on her right
    lab, n = label(white)
    if not n:
        raise SystemExit("cursor not found in the dragged sheet")
    # The arrow's inside is the biggest white patch (cuffs and frills are small).
    sizes = np.bincount(lab.ravel(), minlength=n + 1)
    sizes[0] = 0
    return lab == int(np.argmax(sizes))


def erase_cursor(frame: Frame) -> Frame:
    """The dragged frame without its drawn arrow cursor.

    The app shows the real cursor at the anchor instead, so she can be
    mirrored when pulled to the left (a mirrored arrow would look wrong)."""
    arrow = cursor_patch(frame)
    px = np.asarray(frame.image).astype(np.int16)
    ys, xs = np.nonzero(arrow)
    tip_y = int(ys.min())
    tip_x = int(xs[ys <= tip_y + 2].min())
    # The arrow's outline (and its soft edge) is everything right next to its
    # white inside. Her hand ends at the tip: beside the hand nothing left of
    # the tip goes; below it, the outline of the arrow's straight left side.
    erase = dilate(arrow, 11)
    hand_rows = slice(0, tip_y + 14)
    erase[hand_rows, : max(0, tip_x - 1)] = False
    erase[tip_y + 14:, : max(0, tip_x - 8)] = False
    mask = frame.mask & ~erase
    # Crumbs of the outline left out of reach: small parts in the arrow's
    # corner (below and right of the tip). Marks over her head stay.
    h, w = mask.shape
    lab, n = label(mask)
    if n > 1:
        sizes = np.bincount(lab.ravel(), minlength=n + 1)
        sizes[0] = 0
        main = int(np.argmax(sizes))
        for part in range(1, n + 1):
            if part == main:
                continue
            pys, pxs = np.nonzero(lab == part)
            if pxs.min() >= tip_x - 12 and pys.min() >= tip_y - 6:
                mask[lab == part] = False
    pixels = px.copy()
    pixels[..., 3] = np.where(mask, 255, 0)
    image = Image.fromarray(pixels.astype("uint8"), "RGBA")
    return Frame(image, frame.box, mask)


def seat_line(mask: np.ndarray) -> float:
    """Where the skirt ends and the dangling legs begin (sitting on an edge)."""
    widths = mask.sum(axis=1).astype(float)
    h = len(widths)
    lower = np.arange(h // 2, h)
    widest = lower[np.argmax(widths[lower])]
    for y in range(widest, h):
        if widths[y] < widths[widest] * 0.5:
            return float(y)
    return float(h)


def anchor(sheet: Sheet, frame: Frame, base: float) -> Tuple[float, float]:
    m = frame.mask
    h = m.shape[0]
    bx0, by0 = frame.box[0], frame.box[1]
    if sheet.anchor_x == "cursor":
        return cursor_tip(frame)
    if sheet.anchor_x == "head":
        lo, hi = extent(m, slice(0, max(1, int(h * 0.18))))
    elif sheet.anchor_x == "hem":
        lo, hi = extent(m, slice(int(h * 0.9), h))
    elif sheet.anchor_x == "left":
        lo = hi = extent(m, slice(0, h))[0]
    else:  # right
        lo = hi = extent(m, slice(0, h))[1]
    ax = (lo + hi) / 2
    if sheet.anchor_y == "self":
        ay = float(h)
    elif sheet.anchor_y == "seat":
        ay = seat_line(m)
    else:
        ay = base - by0
    return ax, ay


# ----------------- Packing -----------------
def build(debug: Optional[Path] = None) -> Dict:
    packed: List[Tuple[str, int, Image.Image, Tuple[float, float]]] = []
    anims: Dict[str, Dict] = {}
    for sheet in SHEETS:
        rows = frames_of(sheet)
        flat = [f for row in rows for f in row]
        if sheet.ref_height:
            ref = sheet.ref_height
        else:
            ref = float(np.mean([flat[i].box[3] - flat[i].box[1] for i in sheet.ref]))
        prepared = is_prepared(sheet)
        scale = 1.0 if prepared else STAND_HEIGHT / ref
        entries = []
        # postprocess_sprites.py already erased the drawn cursor and saved its tips
        tips_file = SOURCE / (sheet.file.rsplit(".", 1)[0] + ".cursor.json")
        tips = (json.loads(tips_file.read_text(encoding="utf-8"))
                if prepared and sheet.anchor_x == "cursor" else None)
        index = 0
        for row in rows:
            base = max(f.box[3] for f in row)
            for f in row:
                if tips is not None:
                    tx, ty = tips[index]
                    ax, ay = float(tx - f.box[0]), float(ty - f.box[1])
                else:
                    ax, ay = anchor(sheet, f, base)
                    if sheet.anchor_x == "cursor":
                        f = erase_cursor(f)
                index += 1
                w = max(1, round(f.image.width * scale))
                h = max(1, round(f.image.height * scale))
                small = f.image if prepared else f.image.resize((w, h), Image.LANCZOS)
                entries.append((small, (ax * scale, ay * scale)))
        anims[sheet.anim] = {"facing": sheet.facing, "frames": []}
        for i, (small, anc) in enumerate(entries):
            packed.append((sheet.anim, i, small, anc))
        if debug:
            contact(debug, sheet.anim, entries)
    atlas, places = pack([p[2] for p in packed])
    for (anim, i, small, (ax, ay)), (x, y) in zip(packed, places):
        anims[anim]["frames"].append(
            [x, y, small.width, small.height, round(ax, 1), round(ay, 1)])
    # Lossy colour, lossless alpha: about a third of a PNG and invisible at her size.
    atlas.save(OUT_IMAGE, "WEBP", quality=90, alpha_quality=100, method=6)
    data = {"version": 1, "stand_height": STAND_HEIGHT, "anims": anims}
    OUT_JSON.write_text(json.dumps(data, indent=1), encoding="utf-8")
    if debug:
        lineup(debug, packed)
    return data


def pack(images: List[Image.Image], width: int = 2048) -> Tuple[Image.Image, List[Tuple[int, int]]]:
    """Shelf packing, tallest first."""
    order = sorted(range(len(images)), key=lambda i: -images[i].height)
    places: List[Tuple[int, int]] = [(0, 0)] * len(images)
    x = y = shelf = 0
    for i in order:
        im = images[i]
        if x + im.width > width:
            x, y, shelf = 0, y + shelf + 1, 0
        places[i] = (x, y)
        x += im.width + 1
        shelf = max(shelf, im.height)
    atlas = Image.new("RGBA", (width, y + shelf), (0, 0, 0, 0))
    for im, (px, py) in zip(images, places):
        atlas.paste(im, (px, py))
    return atlas, places


def contact(debug: Path, anim: str, entries) -> None:
    debug.mkdir(parents=True, exist_ok=True)
    pad = 20
    cell_w = max(im.width for im, _ in entries) + pad * 2
    top = max(ay for _, (_, ay) in entries) + pad
    bottom = max(im.height - ay for im, (_, ay) in entries) + pad
    sheet = Image.new("RGBA", (cell_w * len(entries), int(top + bottom)), (70, 120, 80, 255))
    d = ImageDraw.Draw(sheet)
    for i, (im, (ax, ay)) in enumerate(entries):
        ox = int(i * cell_w + cell_w / 2 - ax)
        oy = int(top - ay)
        sheet.alpha_composite(im, (ox, oy))
        cx, cy = i * cell_w + cell_w / 2, top
        d.line([(cx - 8, cy), (cx + 8, cy)], fill=(255, 40, 40, 255), width=2)
        d.line([(cx, cy - 8), (cx, cy + 8)], fill=(255, 40, 40, 255), width=2)
    sheet.save(debug / f"anim_{anim}.png")


def lineup(debug: Path, packed) -> None:
    firsts = {}
    for anim, i, im, anc in packed:
        firsts.setdefault(anim, (im, anc))
    pad = 12
    width = sum(im.width + pad for im, _ in firsts.values()) + pad
    top = max(ay for _, (_, ay) in firsts.values()) + pad
    bottom = max(im.height - ay for im, (_, ay) in firsts.values()) + pad
    canvas = Image.new("RGBA", (int(width), int(top + bottom)), (70, 120, 80, 255))
    d = ImageDraw.Draw(canvas)
    d.line([(0, top), (width, top)], fill=(255, 40, 40, 255))
    d.line([(0, top - STAND_HEIGHT), (width, top - STAND_HEIGHT)], fill=(255, 255, 0, 255))
    x = pad
    for anim, (im, (ax, ay)) in firsts.items():
        canvas.alpha_composite(im, (int(x), int(top - ay)))
        d.text((x, top + 4), anim, fill=(255, 255, 255, 255))
        x += im.width + pad
    canvas.save(debug / "lineup.png")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--debug", type=Path, help="write contact sheets to this folder")
    parser.add_argument("--source", type=Path,
                        help="folder with sheets made by postprocess_sprites.py")
    args = parser.parse_args(argv)
    if args.source:
        global SOURCE, PREPARED
        SOURCE, PREPARED = args.source.resolve(), True
    data = build(args.debug)
    total = sum(len(a["frames"]) for a in data["anims"].values())
    print(f"{len(data['anims'])} animações, {total} quadros -> {OUT_IMAGE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
