"""
Limpa as folhas de sprite geradas no ChatGPT e as deixa no formato que
build_mascot_sprites.py espera.

    .venv\\Scripts\\python.exe scripts\\postprocess_sprites.py paleta [--cores 32]
    .venv\\Scripts\\python.exe scripts\\postprocess_sprites.py status
    .venv\\Scripts\\python.exe scripts\\postprocess_sprites.py processar [--so 01 12 ...]

Pastas: sprites_novos/gerado/ (suas imagens), sprites_novos/paleta.json e
sprites_novos/previa/ (prévias); as folhas prontas substituem as do mascote em
app/mascot/assets/source/, listadas em novos.json para o montador do atlas.
Os nomes esperados estão em PROMPTS.md (ou em `status`).

O que `processar` faz com cada folha:
  1. tira o fundo (magenta chapado; branco/cinza também servem) e as sobras de
     antialiasing roxas na borda;
  2. corta os quadros (nos vãos entre eles) e confere se cada um coube;
  3. põe a Victorique na mesma escala de pixels em todas as folhas: mede a
     altura dos quadros de referência e reduz até ela ter 120 pixels "lógicos"
     em pé (as outras poses mantêm as proporções do atlas atual);
  4. força todas as cores para a paleta compartilhada (paleta.json) e deixa a
     transparência só 0 ou 255: nenhum pixel meio-transparente;
  5. alinha todos os quadros pela base, monta a grade (juntando as partes _a,
     _b... e as linhas) e amplia 2x com pixels exatos (NEAREST), de modo que
     ela fique com 240 px em pé, a altura do atlas.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

import build_mascot_sprites as B
import sprite_plan as P

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "sprites_novos"
GERADO = BASE / "gerado"
PRONTO = B.SOURCE                   # as folhas do mascote (app/mascot/assets/source)
PREVIA = BASE / "previa"
PALETA = BASE / "paleta.json"

LOGICAL = 120       # altura dela em pé, em pixels de arte
SCALE = 2           # ampliação final (120 * 2 = STAND_HEIGHT = 240)
PAD = 6             # margem de cada célula, em pixels de arte
EXTRAS = ("#ffffff", "#14121a", "#e8a33d")   # cursor/baforada, contorno, faíscas
EXTS = ("png", "webp", "jpg", "jpeg")


# ----------------- Entrada -----------------
def find_input(name: str) -> Optional[Path]:
    for ext in EXTS:
        path = GERADO / f"{name}.{ext}"
        if path.exists():
            return path
    return None


def estimate_background(rgb: np.ndarray) -> np.ndarray:
    h, w, _ = rgb.shape
    r = max(4, min(h, w) // 100)
    ring = np.concatenate([rgb[:r].reshape(-1, 3), rgb[-r:].reshape(-1, 3),
                           rgb[:, :r].reshape(-1, 3), rgb[:, -r:].reshape(-1, 3)])
    return np.median(ring, axis=0)


def border_connected(bgish: np.ndarray) -> np.ndarray:
    """The part of `bgish` reachable from the image border."""
    im = Image.fromarray(np.where(bgish, 255, 0).astype("uint8")).copy()
    h, w = bgish.shape
    seeds = [(x, 0) for x in range(0, w, 16)] + [(x, h - 1) for x in range(0, w, 16)]
    seeds += [(0, y) for y in range(0, h, 16)] + [(w - 1, y) for y in range(0, h, 16)]
    for seed in seeds:
        if im.getpixel(seed) == 255:
            ImageDraw.floodfill(im, seed, 128)
    return np.asarray(im) == 128


def foreground(path: Path, tol: float, erode: int) -> Tuple[np.ndarray, np.ndarray, str]:
    """(mask, rgb, note) of the figure in a generated image."""
    arr = np.asarray(Image.open(path).convert("RGBA")).astype(np.int16)
    rgb = arr[..., :3]
    if arr[..., 3].min() < 250:                  # the image already has transparency
        mask, note = arr[..., 3] > 128, "transparência original"
    else:
        bg = estimate_background(rgb)
        dist = np.sqrt(((rgb - bg) ** 2).sum(-1))
        bgish = dist < tol
        if bg[0] > 180 and bg[2] > 180 and bg[1] < 90:       # magenta: nothing of her is
            r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
            mask = ~(bgish | (((r - g) > 70) & ((b - g) > 70)))
            note = "fundo magenta"
        else:
            mask = ~border_connected(bgish)
            note = f"fundo {tuple(int(c) for c in bg)} (não é magenta: confira o recorte)"
    if erode:
        mask = ~B.dilate(~mask, erode)           # eats the antialiased rim
    return B.drop_specks(mask), rgb.astype(np.uint8), note


# ----------------- Quadros -----------------
@dataclass
class Raw:
    rgba: np.ndarray        # cropped, full resolution
    main_h: int             # height of the figure without its loose effect marks


def gap_cuts(profile: np.ndarray, parts: int) -> List[int]:
    """Column boundaries between `parts` frames: the middle of the empty gap
    nearest each even-grid line (the emptiest column when no gap is empty)."""
    size = len(profile)
    window = size // (parts * 3)
    out = [0]
    for k in range(1, parts):
        nominal = round(k * size / parts)
        lo, hi = max(1, nominal - window), min(size - 1, nominal + window)
        empty = np.flatnonzero(profile[lo:hi] == 0) + lo
        if not len(empty):
            out.append(B.cuts(profile, parts, window)[k])
            continue
        runs = np.split(empty, np.flatnonzero(np.diff(empty) > 1) + 1)
        mids = [int(r[len(r) // 2]) for r in runs]
        out.append(min(mids, key=lambda m: abs(m - nominal)))
    out.append(size)
    return out


def cut_frames(mask: np.ndarray, rgb: np.ndarray, count: int, label: str,
               warn: List[str]) -> List[Raw]:
    h, w = mask.shape
    profile = mask.sum(axis=0)
    cuts = gap_cuts(profile, count)
    for k in range(1, count):
        if profile[cuts[k]]:
            warn.append(f"{label}: os quadros {k} e {k + 1} se tocam (cortei no ponto mais vazio)")
    frames: List[Raw] = []
    for i in range(count):
        x0, x1 = cuts[i], cuts[i + 1]
        cell = mask[:, x0:x1]
        ys, xs = np.nonzero(cell)
        if not len(ys):
            raise SystemExit(f"{label}: quadro {i + 1} vazio (esperava {count} quadros)")
        crop = cell[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        px = rgb[ys.min():ys.max() + 1, x0 + xs.min():x0 + xs.max() + 1]
        rgba = np.dstack([px, np.where(crop, 255, 0).astype("uint8")])
        main = B.biggest_part(crop)
        mys = np.nonzero(main.any(axis=1))[0]
        frames.append(Raw(rgba, int(mys.max() - mys.min() + 1) if len(mys) else crop.shape[0]))
    return frames


def strip_fringe(rgba: np.ndarray, rounds: int = 2) -> None:
    """Drops edge pixels still tinted by the magenta background."""
    for _ in range(rounds):
        alpha = np.pad(rgba[..., 3] > 0, 1)
        inner = alpha[1:-1, 1:-1]
        edge = inner & ~(alpha[:-2, 1:-1] & alpha[2:, 1:-1] & alpha[1:-1, :-2] & alpha[1:-1, 2:])
        r, g, b = (rgba[..., i].astype(int) for i in range(3))
        rgba[..., 3][edge & ((r - g) > 25) & ((b - g) > 25)] = 0


def load_palette() -> np.ndarray:
    if not PALETA.exists():
        raise SystemExit("Falta sprites_novos/paleta.json: rode `postprocess_sprites.py paleta` "
                         "com sprites_novos/gerado/00-mestre.png pronto.")
    colors = json.loads(PALETA.read_text(encoding="utf-8"))
    return np.array([[int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in colors], dtype=np.int32)


def to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB (0-255) to CIELAB, so "nearest colour" means nearest to the eye
    (in plain RGB a dark grey can land on a dark teal)."""
    c = rgb.astype(float) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ np.array([[0.4124, 0.3576, 0.1805],
                        [0.2126, 0.7152, 0.0722],
                        [0.0193, 0.1192, 0.9505]]).T
    xyz /= np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], axis=-1)


def to_palette(rgba: np.ndarray, palette: np.ndarray) -> None:
    on = rgba[..., 3] > 0
    if not on.any():
        return
    px = rgba[..., :3][on].astype(np.int32)
    best = ((to_lab(px)[:, None, :] - to_lab(palette)[None, :, :]) ** 2).sum(-1).argmin(1)
    out = palette[best]
    # Near-white stays pure white: the dragged sheet's cursor is found by it,
    # and puffs/sparkles should not turn into the cream of her cuffs.
    white = (px.min(-1) >= 228) & ((px.max(-1) - px.min(-1)) <= 18)
    out[white] = 255
    rgba[..., :3][on] = out


def take_cursor(s: np.ndarray) -> Optional[Tuple[int, int]]:
    """The dragged sheet draws a white arrow cursor at her upper right. Erases it
    (with its dark outline) and returns its tip, which becomes her anchor: in
    the app the real cursor sits there, so the drawn one must go."""
    h, w = s.shape[:2]
    region = np.zeros((h, w), dtype=bool)
    region[: int(h * 0.6), int(w * 0.3):] = True
    # The generator draws it white or cream, the same colour as her cuffs and
    # bows, so it is told apart by place: the highest light piece of the frame.
    light = (s[..., 3] > 0) & (s[..., :3].min(-1) >= 200) & region
    lab, n = B.label(light)
    if not n:
        return None
    sizes = np.bincount(lab.ravel(), minlength=n + 1)
    big = [k for k in range(1, n + 1) if sizes[k] >= 15]
    if not big:
        return None
    tops = {k: (np.nonzero(lab == k)[0].min(), -np.nonzero(lab == k)[1].max()) for k in big}
    main = min(big, key=lambda k: tops[k])
    # The hand can split the arrow in pieces: keep the light pieces touching it.
    zone = B.dilate(lab == main, 3)
    pieces = [k for k in range(1, n + 1) if (zone & (lab == k)).any()]
    arrow = np.isin(lab, pieces)
    ys, xs = np.nonzero(arrow)
    top = int(ys.min())
    tip = (int(xs[ys == top].min()), top - 1)          # the outline above the white
    # Its outline (black or grey) goes too; only the skin of her hand stays.
    rgb = s[..., :3].astype(int)
    skin = (rgb[..., 0] > 170) & (rgb[..., 1] > 130) & (rgb[..., 0] - rgb[..., 2] > 25)
    s[..., 3][B.dilate(arrow, 2) & (arrow | ~skin)] = 0
    # crumbs of the outline left beside the hand
    rest = (s[..., 3] > 0) & B.dilate(arrow, 4)
    lab, n = B.label(rest)
    for k in range(1, n + 1):
        part = lab == k
        if part.sum() < 10 and not (B.dilate(part, 1) & (s[..., 3] > 0) & ~rest).any():
            s[..., 3][part] = 0
    s[..., :3][s[..., 3] == 0] = 0
    # The anchor is her hand: the point of her left nearest to where the drawn
    # tip was (in the app the real cursor's tip sits there).
    ys, xs = np.nonzero(s[..., 3] > 0)
    k = int(np.argmin((xs - tip[0]) ** 2 + (ys - tip[1]) ** 2))
    return int(xs[k]), int(ys[k])


def shrink(raw: Raw, factor: float, palette: np.ndarray) -> np.ndarray:
    h, w = raw.rgba.shape[:2]
    size = (max(1, round(w * factor)), max(1, round(h * factor)))
    # premultiplied, so the (arbitrary) colour under transparent pixels does not bleed
    small = Image.fromarray(raw.rgba, "RGBA").convert("RGBa").resize(size, Image.BOX).convert("RGBA")
    out = np.array(small)
    out[..., 3] = np.where(out[..., 3] >= 128, 255, 0)
    out[..., :3][out[..., 3] == 0] = 0
    strip_fringe(out)
    to_palette(out, palette)
    return out


# ----------------- Folha -----------------
def process_sheet(sheet: B.Sheet, palette: np.ndarray, tol: float, erode: int,
                  warn: List[str]) -> Optional[Image.Image]:
    parts = P.parts_of(sheet)
    name = P.stem(sheet)
    files = [find_input(name + part.suffix) for part in parts]
    missing = [name + part.suffix for part, f in zip(parts, files) if f is None]
    if missing:
        print(f"  {name}: faltam {', '.join(missing)}")
        return None
    frames: List[Optional[Raw]] = [None] * (sheet.rows * sheet.cols)
    for part, path in zip(parts, files):
        mask, rgb, _ = foreground(path, tol, erode)
        label = f"{name}{part.suffix}"
        for k, raw in enumerate(cut_frames(mask, rgb, part.count, label, warn)):
            frames[part.first + k] = raw
    ref, ratio, _ = P.REF[sheet.anim]
    heights = [frames[i].main_h for i in ref]           # type: ignore[union-attr]
    factor = LOGICAL * ratio / float(np.median(heights))
    block = 1.0 / factor
    if not 2.2 <= block <= 8:
        warn.append(f"{name}: cada pixel de arte tem ~{block:.1f}px na imagem gerada "
                    f"(ideal 3 a 6): a figura saiu {'pequena' if block < 2.2 else 'grande'} demais")
    small = [shrink(f, factor, palette) for f in frames]    # type: ignore[arg-type]
    tips = [take_cursor(s) for s in small] if sheet.anchor_x == "cursor" else []
    cell_w = max(s.shape[1] for s in small) + 2 * PAD
    cell_h = max(s.shape[0] for s in small) + 2 * PAD
    sheet_img = np.zeros((cell_h * sheet.rows, cell_w * sheet.cols, 4), dtype=np.uint8)
    places = []
    for i, s in enumerate(small):
        row, col = divmod(i, sheet.cols)
        h, w = s.shape[:2]
        y = row * cell_h + cell_h - PAD - h              # all feet / seats on one line
        x = col * cell_w + (cell_w - w) // 2
        sheet_img[y:y + h, x:x + w] = s
        places.append((x, y))
    if tips:
        missing = [i + 1 for i, t in enumerate(tips) if t is None]
        if missing:
            warn.append(f"{name}: não achei o cursor branco nos quadros {missing}: gere de novo")
        else:
            anchors = [[(x + tx) * SCALE, (y + ty) * SCALE] for (x, y), (tx, ty) in zip(places, tips)]
            PRONTO.mkdir(parents=True, exist_ok=True)
            (PRONTO / f"{name}.cursor.json").write_text(json.dumps(anchors), encoding="utf-8")
    out = Image.fromarray(sheet_img, "RGBA")
    out = out.resize((out.width * SCALE, out.height * SCALE), Image.NEAREST)
    print(f"  {name}: {len(small)} quadros, pixel de arte ~{block:.1f}px, folha {out.width}x{out.height}")
    return out


def mark_prepared(file: str) -> None:
    """Lists the sheet in novos.json, so the atlas builder takes it as it is."""
    manifest = PRONTO / B.MANIFEST
    names = set(json.loads(manifest.read_text(encoding="utf-8"))) if manifest.exists() else set()
    names.add(file)
    manifest.write_text(json.dumps(sorted(names), indent=1) + "\n", encoding="utf-8")


def preview(img: Image.Image, path: Path) -> None:
    bg = Image.new("RGBA", img.size, (70, 120, 80, 255))
    bg.alpha_composite(img)
    path.parent.mkdir(parents=True, exist_ok=True)
    bg.convert("RGB").save(path)


# ----------------- Comandos -----------------
def cmd_paleta(args: argparse.Namespace) -> int:
    path = args.mestra or find_input("00-mestre")
    if not path:
        raise SystemExit("Coloque a folha mestra em sprites_novos/gerado/00-mestre.png")
    mask, rgb, note = foreground(Path(path), args.tol, args.erode)
    # Two halves: by pixel count (the big areas: skirt, hair, skin keep their true
    # tones) and by distinct colour (so the few teal pixels of her eyes and other
    # small details still get a colour of their own).
    keep = max(2, args.cores - len(EXTRAS))
    rare = np.unique((rgb[mask] // 8) * 8 + 4, axis=0)
    common = rgb[mask]
    if len(common) > 400_000:
        common = common[np.random.default_rng(0).choice(len(common), 400_000, replace=False)]

    def quant(px: np.ndarray, n: int) -> np.ndarray:
        q = Image.fromarray(px.reshape(-1, 1, 3), "RGB").quantize(n, Image.MEDIANCUT)
        return np.array(q.getpalette()[:n * 3]).reshape(-1, 3)

    pal = np.unique(np.vstack([quant(common, keep * 2 // 3), quant(rare, keep - keep * 2 // 3)]), axis=0)
    colors = [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in pal] + list(EXTRAS)
    PALETA.parent.mkdir(parents=True, exist_ok=True)
    PALETA.write_text(json.dumps(colors, indent=1), encoding="utf-8")
    print(f"{len(colors)} cores ({note}) -> {PALETA.relative_to(ROOT)}")
    swatch = Image.new("RGB", (len(colors) * 24, 24))
    for i, c in enumerate(colors):
        swatch.paste(Image.new("RGB", (24, 24), c), (i * 24, 0))
    swatch.save(BASE / "paleta.png")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    have = total = 0
    print(f"{'00-mestre':32} {'ok' if find_input('00-mestre') else 'FALTA'}")
    for sheet in B.SHEETS:
        for part in P.parts_of(sheet):
            name = P.stem(sheet) + part.suffix
            ok = find_input(name) is not None
            have += ok
            total += 1
            print(f"{name:32} {'ok' if ok else 'FALTA'}  ({part.count} quadros)")
    print(f"\n{have}/{total} imagens")
    return 0


def cmd_processar(args: argparse.Namespace) -> int:
    palette = load_palette()
    wanted = set(args.so or [])
    PRONTO.mkdir(parents=True, exist_ok=True)
    warn: List[str] = []
    done = 0
    for sheet in B.SHEETS:
        if wanted and P.stem(sheet).split("-")[0] not in wanted:
            continue
        img = process_sheet(sheet, palette, args.tol, args.erode, warn)
        if img is None:
            continue
        img.save(PRONTO / sheet.file, "WEBP", lossless=True, method=6)
        preview(img, PREVIA / (P.stem(sheet) + ".png"))
        mark_prepared(sheet.file)
        done += 1
    for line in warn:
        print("AVISO", line)
    print(f"\n{done} folhas -> {PRONTO.relative_to(ROOT)}")
    if done:
        print("Próximo: scripts\\build_mascot_sprites.py --debug sprites_novos\\debug")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--tol", type=float, default=70.0,
                        help="distância de cor até o fundo para contar como fundo (padrão 70)")
    common.add_argument("--erode", type=int, default=1,
                        help="pixels comidos na borda da figura, contra franjas (padrão 1)")
    p = sub.add_parser("paleta", parents=[common], help="tira a paleta da folha mestra")
    p.add_argument("mestra", nargs="?", help="padrão: gerado/00-mestre.*")
    p.add_argument("--cores", type=int, default=36)
    p.set_defaults(fn=cmd_paleta)
    sub.add_parser("status", help="lista as imagens que já existem").set_defaults(fn=cmd_status)
    p = sub.add_parser("processar", parents=[common], help="limpa e monta as folhas")
    p.add_argument("--so", nargs="*", metavar="NN", help="só estas folhas (ex.: 01 12)")
    p.set_defaults(fn=cmd_processar)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
