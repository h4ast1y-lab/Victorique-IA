"""
Plano das folhas de sprite da Victorique, compartilhado por
sprite_prompts.py (gera os prompts) e postprocess_sprites.py (limpa as imagens).

Cada folha do jogo (build_mascot_sprites.SHEETS) vira uma ou mais IMAGENS
geradas: o ChatGPT desenha bem poucos quadros por imagem, então folhas largas
são divididas em partes (`_a`, `_b`...) e remontadas pelo pós-processamento.
Quantos quadros cabem por imagem depende da proporção largura/altura da pose.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from build_mascot_sprites import SHEETS, Sheet

# anim -> (quadros que medem a altura dela, altura desses quadros / altura em pé,
#          maior largura / maior altura dos quadros)
# Os números vêm do atlas atual, para os sprites novos manterem as mesmas
# proporções entre as poses (sentada é menor que em pé etc.) que o
# comportamento do mascote já espera.
_ALL6 = (0, 1, 2, 3, 4, 5)
REF: Dict[str, Tuple[Tuple[int, ...], float, float]] = {
    "walk": (_ALL6, 1.00, 0.50),
    "moods": (_ALL6, 1.00, 0.48),
    "talk": (_ALL6, 1.00, 0.50),
    "blink": (_ALL6, 1.00, 0.48),
    "sit_down": ((0,), 1.00, 0.54),
    "sitting": (_ALL6, 0.85, 0.68),
    "turn": ((2,), 1.00, 0.52),
    "stand_up": ((5,), 1.00, 0.60),
    "held": ((0,), 1.00, 1.10),
    "jump": ((0,), 1.00, 0.67),
    "fall": ((7,), 1.00, 0.61),
    "climb": ((11,), 0.90, 0.71),
    "edge": (tuple(range(12)), 0.94, 0.50),
    "peek": (tuple(range(9)), 0.84, 0.47),
    "tea": (tuple(range(12)), 1.00, 0.43),
    "read": (tuple(range(12)), 1.00, 0.51),
    "close_book": ((0,), 1.00, 0.48),
    "glance": (_ALL6, 1.00, 0.49),
    "think": ((0,), 1.00, 0.48),
    "doze": ((0,), 1.00, 0.48),
    "happy": (_ALL6, 1.00, 0.50),
    "point": ((0,), 1.00, 0.57),
    "confused": ((0,), 1.00, 0.50),
    "surprised": (_ALL6, 1.00, 0.48),
    "sigh": (tuple(range(8)), 1.00, 0.41),
    "wake": ((0,), 1.00, 0.44),
    "tantrum": ((0,), 1.00, 0.61),
}

IMAGE_W, IMAGE_H = 1536, 1024      # tamanho pedido ao ChatGPT (3:2)


def per_image(ar: float) -> int:
    """Quadros por imagem para uma pose de proporção `ar` (largura/altura)."""
    if ar <= 0.58:
        return 6
    if ar <= 0.86:
        return 4
    if ar <= 1.16:
        return 3
    return 2


def fit_percent(anim: str, count: int) -> int:
    """Altura (em % da imagem) que a figura deve ter para caber na célula."""
    ar = REF[anim][2]
    cell = IMAGE_W / count
    return max(20, min(45, int(0.8 * cell / ar / IMAGE_H * 100)))


@dataclass(frozen=True)
class Part:
    row: int          # linha da folha final
    first: int        # índice global do primeiro quadro (linha * colunas + coluna)
    count: int
    suffix: str       # "" quando a folha toda cabe numa imagem, senão "_a", "_b"...


def sheet_by_anim(anim: str) -> Sheet:
    for sheet in SHEETS:
        if sheet.anim == anim:
            return sheet
    raise KeyError(anim)


def parts_of(sheet: Sheet) -> List[Part]:
    n = per_image(REF[sheet.anim][2])
    pieces = -(-sheet.cols // n)                 # partes por linha (teto)
    base, extra = divmod(sheet.cols, pieces)
    raw: List[Tuple[int, int, int]] = []
    for row in range(sheet.rows):
        col = 0
        for k in range(pieces):
            count = base + (1 if k < extra else 0)
            raw.append((row, row * sheet.cols + col, count))
            col += count
    if len(raw) == 1:
        return [Part(*raw[0], "")]
    return [Part(r, f, c, "_" + chr(ord("a") + i)) for i, (r, f, c) in enumerate(raw)]


def stem(sheet: Sheet) -> str:
    return sheet.file.rsplit(".", 1)[0]
