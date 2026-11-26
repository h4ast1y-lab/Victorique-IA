"""
Gera sprites_novos/PROMPTS.md: um prompt pronto para colar no ChatGPT por
imagem a gerar (folha mestra + cada parte de cada folha do mascote).

    .venv\\Scripts\\python.exe scripts\\sprite_prompts.py

Para mudar o visual da Victorique, edite CHARACTER / STYLE aqui e rode de novo.
Os prompts ficam em inglês (o gerador de imagem obedece melhor); as instruções
em volta ficam em português.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

import sprite_plan as P
from build_mascot_sprites import SHEETS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "sprites_novos" / "PROMPTS.md"

CHARACTER = """\
CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).\
"""

STYLE = """\
STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.\
"""


BASELINE = {
    "feet": "The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image.",
    "air": "On the ground, the lowest point of the figure rests on one invisible horizontal baseline near the lower third of the image (the same in every frame); in airborne frames she floats above that baseline.",
    "cursor": "The tip of the mouse cursor is at exactly the same position inside its cell in every frame.",
    "seat": "The seat line (where the skirt rests on the ledge) is at exactly the same height in every frame, near the middle of the image; the legs dangle below it.",
}


def layout(count: int, pct: int, base: str = "feet") -> str:
    return f"""\
LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly {count} frames, left to right = frame 1 to frame {count}. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about {pct}% of the image height. {BASELINE[base]} Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.\
"""


# --------------------------------------------------------------------------
# Folha mestra (passo 1)
# --------------------------------------------------------------------------
MASTER_FRAMES = [
    "Front view, standing relaxed, arms hanging at her sides, neutral calm face, mouth closed.",
    "Three-quarter view facing the viewer's right, standing relaxed (the ribbon bow trails behind her head on the viewer's left).",
    "Three-quarter view facing the viewer's left, standing relaxed (the ribbon bow is on the viewer's right).",
    "Back view, standing relaxed, showing the long hair falling down her back and the back of the bonnet with the bow.",
]

# --------------------------------------------------------------------------
# Folhas do jogo: titulo, descricao, frases por quadro (na ordem da folha,
# linha por linha) e notas especificas.
# --------------------------------------------------------------------------
FRONT = "Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes."

ANIMS: Dict[str, dict] = {}


BASE_OF = {"held": "cursor", "jump": "air", "fall": "air", "tantrum": "air", "edge": "seat"}


def anim(key: str, title: str, intro: str, frames: List[str], note: str = "") -> None:
    ANIMS[key] = {"title": title, "intro": intro, "frames": frames, "note": note,
                  "base": BASE_OF.get(key, "feet")}


anim("walk", "Walk cycle", "A looping side-walk. She faces the viewer's LEFT in three-quarter side view and walks to the left; the ribbon bow and the long hair trail behind her on the right.", [
    "Contact pose: the front foot (viewer's left) reaches forward, the back foot is behind, arms swing lightly, hair trailing behind.",
    "Down pose: weight lands on the front foot, body at its lowest, skirt sways.",
    "Passing pose: back foot passes under the skirt, legs together, body at its highest, hair lifts a little.",
    "Contact pose with the opposite foot forward.",
    "Down pose on that foot, body lowest.",
    "Passing pose again on the other side, body highest (loops back to frame 1).",
], "Feet are mostly hidden by the skirt: show the skirt hem swaying and only the toes peeking out.")

anim("moods", "Mood faces", "Standing idle. ONLY the face changes (and tiny effect marks); the body is frozen and identical in all frames.", [
    "Calm neutral face, mouth closed.",
    "Annoyed: eyes narrowed, one brow lowered, two tiny black tick marks beside the head on the viewer's right.",
    "Sulky: eyes narrowed and looking aside, mouth slightly pursed.",
    "Bored: half-lidded eyes, flat mouth.",
    "Eyes closed, a smug little sigh with a tiny white puff next to her cheek on the viewer's right.",
    "Calm neutral face again, identical to frame 1.",
], FRONT)

anim("talk", "Talking", "Standing idle while talking. Mouth shapes cycle; one hand rises to her chest.", [
    "Neutral, mouth closed, both arms hanging.",
    "Mouth slightly open (small oval), her right hand (viewer's left) lifts to her chest.",
    "Mouth open wider mid-speech, eyes closed for a moment, hand at her chin.",
    "Mouth closed, eyes closed, hand at her chin.",
    "Mouth small open, eyes open, hand at her chest.",
    "Mouth closed, hand lowered back to her side, neutral (loops back to frame 1).",
], FRONT)

anim("blink", "Blink", "Standing idle: a blink with a very slight breathing bob.", [
    "Eyes fully open, neutral.",
    "Eyelids half lowered.",
    "Eyes closed.",
    "Eyes closed, head dips one pixel.",
    "Eyes half open.",
    "Eyes fully open, identical to frame 1.",
], FRONT)

anim("sit_down", "Sitting down", "She sits down on the floor gracefully, ending in a neat seated pose with the skirt fanned out.", [
    "Standing relaxed, front view, neutral.",
    "Knees bend slightly, hands move down to the skirt.",
    "Crouching lower, skirt starts to puff outward, hands on the skirt.",
    "Almost down, skirt spreading wide around her.",
    "Seated on the floor, skirt fanned out in a wide round shape, hands resting on her lap.",
    "Settled seated pose, hands neatly folded on her lap, calm face.",
], FRONT + " In frames 5-6 the bottom of the spread skirt touches the baseline.")

anim("sitting", "Sitting idle", "Seated on the floor, front view, skirt fanned out in a wide round shape, hands folded on her lap. A subtle idle loop.", [
    "Calm face, eyes open.",
    "Body one pixel higher (inhale), eyes open.",
    "Eyes closed (blink).",
    "Eyes open, head tilted very slightly toward the viewer's right.",
    "Head back to centre, eyes open.",
    "Calm face, identical to frame 1.",
], FRONT + " The bottom of the skirt rests on the baseline.")

anim("turn", "Turning", "She turns in place between facing the camera and a three-quarter side view, standing relaxed.", [
    "Three-quarter view facing the viewer's right (the bow trails behind her head on the viewer's left).",
    "Turning: head and body closer to the front, still slightly to the viewer's right.",
    "Full front view, neutral, arms at her sides.",
    "Turning: slightly toward the viewer's left.",
    "Three-quarter view facing the viewer's left (the bow is on the viewer's right behind the head).",
    "Same three-quarter view facing the viewer's left, hair swaying a tiny bit differently.",
])

anim("stand_up", "Standing up", "She gets up from sitting on the floor to a relaxed standing pose (the reverse of sitting down).", [
    "Seated on the floor, skirt fanned out, hands on her lap.",
    "Hands press on the floor and skirt, body leans slightly forward.",
    "Rising onto her knees, skirt still wide.",
    "Half standing, skirt gathering downward.",
    "Almost upright, small skirt sway.",
    "Standing upright, relaxed, neutral calm face.",
], FRONT + " The lowest point of the figure rests on the baseline in every frame.")

anim("held", "Dragged by the mouse cursor", "She is grabbed and dragged by a mouse-pointer arrow, and dangles from it while swinging. Facing the viewer's RIGHT (three-quarter view).", [
    "Hanging straight down from the cursor, feet dangling, calm face.",
    "Hanging, surprised face (wide eyes), two tiny black tick marks near her head.",
    "Body swings a little to the viewer's left, feet lift, hair starts to trail left.",
    "Legs bent, skirt flaring, hair trailing left, slightly worried face.",
    "Body swings more toward horizontal to the viewer's left, hair streaming left.",
    "Almost horizontal like a flag, hair and skirt flying left, annoyed face.",
    "Horizontal, eyes squeezed shut, hair and skirt flying left.",
    "Horizontal, eyes squeezed shut in an angry '> <' look.",
    "Swinging back, small impact tick marks near her head.",
    "Swinging back toward hanging, hair swaying.",
    "Hanging again, legs swaying, slight frown.",
    "Hanging almost straight, calm, looking toward the viewer.",
], "THE CURSOR: a classic white mouse-pointer arrow (pure white fill #FFFFFF with a thin black outline, tip pointing up and to the left) drawn at the upper right of her. Her stretched right arm holds the lower-left edge of the arrow. The arrow is the same size and in the exact same spot of its cell in every frame; only she moves. The arrow is the ONLY pure white thing on the right side of the cell. Her cuffs and bow stay cream, not pure white.")

anim("jump", "Jump", "A jump from standing to landing, facing the viewer's RIGHT (three-quarter view), skirt and hair reacting to the motion.", [
    "Standing three-quarter right, about to crouch, knees just starting to bend.",
    "Crouching, knees bent, body lowered, arms pulled back.",
    "Deepest crouch, skirt compressed, hair settling.",
    "Take-off: legs extending, feet leaving the ground, arms swinging up.",
    "Rising: body stretched, feet off the ground, hair streaming down and back.",
    "Apex: knees tucked, skirt billowing, arms up.",
    "Descending: legs extending down, skirt rising, hair floating up.",
    "Landing: knees bent absorbing the impact, a few tiny grey dust ticks at her feet.",
], "NO shadow on the floor under her, even when airborne.")

anim("fall", "Fall and recovery", "She falls through the air, hits the floor and gets back up. Facing the viewer's RIGHT (three-quarter view).", [
    "Falling: arms flailing, hair streaming upward, legs dangling, eyes wide.",
    "Falling faster: hair straight up, skirt billowing, mouth open.",
    "About to land: legs bent, arms out.",
    "Impact: crouched flat on the floor, hands down, eyes shut tight, a few small grey-white dust puffs around her.",
    "Dazed on the floor on hands and knees.",
    "Rising to a crouch, one hand on the floor.",
    "Half standing, brushing herself off.",
    "Standing upright, composed, neutral face.",
], "NO shadow on the floor under her.")

anim("climb", "Climbing a wall", "She climbs up the face of a vertical wall that is on her RIGHT (the wall is invisible: do not draw it). Three-quarter back/side view facing the viewer's right, hands reaching up and to the right.", [
    "Standing three-quarter facing right, looking at the wall.",
    "Raises her right hand up toward the wall, body leaning to the right.",
    "Climb cycle step 1: right hand high, left knee raised, body stretched up along the wall.",
    "Climb cycle step 2: pulling up with the right arm, body rising.",
    "Climb cycle step 3: left hand reaches higher, right knee raised.",
    "Climb cycle step 4: pulling up with the left arm.",
    "Climb cycle step 5: right hand high again, left knee raised, hair hanging down her back.",
    "Climb cycle step 6: pulling up with the right arm.",
    "Climb cycle step 7: left hand high, right knee raised.",
    "Climb cycle step 8: pulling up with the left arm (the cycle then repeats from step 1).",
    "Reaching the top: leaning forward over the ledge, one knee up.",
    "Standing upright on top, three-quarter facing right, relaxed.",
], "Frames 3-10 are one 8-step looping cycle: frame 10 must lead smoothly back into frame 3. Keep the rightmost edge of her hand/arm roughly at the same distance from the wall line in every frame.")

anim("edge", "Sitting on a ledge", "She sits on the edge of a window frame (an invisible ledge: do not draw it), front view, legs dangling and swinging gently. A 12-frame loop.", [
    "Both legs dangling straight down together, hands resting at her sides on the ledge.",
    "Her left leg (viewer's right) lifts slightly forward.",
    "Left leg swings further forward.",
    "Left leg at its highest swing, head tilts a hair.",
    "Left leg swinging back down.",
    "Both legs together again.",
    "Her right leg (viewer's left) lifts slightly forward, eyes blink.",
    "Right leg swings further forward.",
    "Right leg at its highest swing.",
    "Right leg swinging back down.",
    "Right leg nearly together with the left.",
    "Both legs together, identical to frame 1 (loops).",
], "Seated on a ledge: the bunched skirt rests at the seat line and her lower legs in black stockings with small black shoes dangle below it.")

anim("peek", "Peeking from behind a wall", "She hides behind a vertical wall edge and peeks out. The wall is on the LEFT of each cell and is invisible: every frame is cut by a perfectly straight vertical line at its LEFT side, and whatever is behind that line is simply missing. Only the part of her to the right of that line is drawn. She leans out toward the viewer's right.", [
    "Almost hidden: only a thin sliver of the bonnet edge and hair is visible at the cut line.",
    "A bit more: bonnet edge and one eye.",
    "Head half out: half of the face, the bonnet and part of the bow.",
    "Face about two thirds out, curious look.",
    "Face almost fully out, looking at the viewer.",
    "Fully out: face, shoulder and long hair hanging.",
    "Fully out with a small hand gripping the wall edge, slight smile.",
    "Same as frame 7 but eyes closed (blink).",
    "Retreating: sliver of bonnet and hair again, eyes closed.",
], "In every frame the straight cut line is at the same x position inside its cell and runs the full height of the figure. The bottom of the visible part rests on the baseline.")

anim("tea", "Drinking tea", "Standing, front view, holding a small white porcelain teacup on a saucer in both hands. A looping sip.", [
    "Holding the cup and saucer at waist height, calm face.",
    "Cup lifted slightly.",
    "Cup lifted to chest height.",
    "Cup at chin height, eyes starting to close.",
    "Cup at her lips, eyes closed.",
    "Sipping, cup tilted, eyes closed.",
    "Still sipping, cup tilted.",
    "Lowering the cup, eyes half open.",
    "Cup at chin height, eyes open.",
    "Cup at chest height, small contented face.",
    "Cup lower, near waist.",
    "Cup at waist height, identical to frame 1 (loops).",
], FRONT)

anim("read", "Reading a book", "Standing, front view, holding an open brown leather book in both hands at chest height, eyes looking down at it. A looping page turn.", [
    "Holding the open book, eyes down on the pages.",
    "Head tilts very slightly.",
    "Blink (eyes closed).",
    "Eyes down, reading.",
    "Eyes down, her right hand starts to lift a page corner.",
    "Page lifting.",
    "Page half turned (curved page).",
    "Page turned over, hand returning.",
    "Eyes down, reading the new page.",
    "Eyes shift a little to the side, still reading.",
    "Blink (eyes closed).",
    "Eyes down, identical to frame 1 (loops).",
], FRONT)

anim("close_book", "Closing the book", "Standing, front view. She finishes reading, closes the book and lets it go.", [
    "Holding an open brown book at chest height, eyes down.",
    "Eyes drooping, half-lidded.",
    "Eyes closed, the book half closed between her hands.",
    "Book closed, held against her chest.",
    "Book held low at her hip with one hand, the other arm relaxing.",
    "No book anymore, both arms relaxed at her sides, neutral face.",
], FRONT)

anim("glance", "Glancing around", "Standing idle, front view, she looks around with a skeptical air. Mostly eyes and a slight head turn.", [
    "Neutral, looking at the camera.",
    "Eyes shift to the viewer's left.",
    "Head turns slightly to the viewer's left, eyes left.",
    "Head turned a bit more, half-lidded skeptical eyes.",
    "Head back to centre, eyes shift to the viewer's right.",
    "Back to neutral, looking at the camera.",
], FRONT)

anim("think", "Thinking", "Standing, front view, thoughtful pose with a hand to her chin.", [
    "Neutral, arms at her sides.",
    "Her right hand (viewer's left) rises toward her chin.",
    "Hand at her chin, eyes looking up and aside.",
    "Hand at her chin, eyes closed, thinking.",
    "Hand at her chin, eyes open looking up to the viewer's left.",
    "Hand at her chin, eyes open and focused on the camera.",
], FRONT)

anim("doze", "Dozing off", "Standing, front view, she gets sleepy and nods off while standing; the head droops progressively and the body slouches slightly. Do NOT draw any letters such as Z.", [
    "Eyes open, slightly sleepy.",
    "Eyes half closed, head dips a little.",
    "Eyes closed, head tilts down.",
    "Eyes closed, head lower, body swaying.",
    "Head at its lowest, eyes closed.",
    "Head rising slowly back up, eyes closed.",
], FRONT + " The soles stay on the baseline; only the upper body slouches.")

anim("happy", "Happy", "Standing, front view, her face gets happier step by step. Effect marks are tiny orange-gold ticks (#e8a33d).", [
    "A gentle small smile.",
    "A bigger smile.",
    "Eyes closed in a '^ ^' smile, rosy cheeks.",
    "Wide happy smile with eyes closed.",
    "Same wide smile, three tiny orange-gold sparkle ticks above her head on the viewer's right.",
    "Same, with the sparkle ticks slightly bigger.",
], FRONT)

anim("point", "Deduction pointing", "Standing, front view, she makes a deduction and points. Effect marks are tiny orange-gold ticks (#e8a33d).", [
    "Neutral, arms at her sides.",
    "Eyes closed, the arm on the viewer's right side starts to lift, forearm rising.",
    "Hand at chest, mouth slightly open.",
    "Arm extended, pointing with the index finger toward the viewer's right, mouth open.",
    "Same pointing pose, three tiny orange-gold emphasis ticks near her head.",
    "Arm fully extended pointing to the viewer's right, confident face.",
], FRONT + " Only the arm on the viewer's RIGHT side moves; it points to the viewer's right.")

anim("confused", "Confused", "Standing, front view, she gets confused. Effect marks (question marks, ticks) are drawn in near-black #1b1a1f.", [
    "Neutral.",
    "Eyes wide, small shake ticks on both sides of her head.",
    "Head tilted, mouth a small 'o'.",
    "Hand at her chin, one small question mark above her head on the viewer's right.",
    "Brow furrowed, two small question marks above her head.",
    "One hand palm-up in a shrug, one small question mark.",
], FRONT)

anim("surprised", "Surprised", "Standing, front view, she gets startled. Effect marks are short near-black ticks (#1b1a1f).", [
    "Neutral.",
    "Eyes widen, short startle ticks above her head.",
    "Mouth a small 'o', hands tighten into fists at her chest.",
    "Hands raised to her chest, wide eyes.",
    "Both hands cover her mouth, wide eyes, startle ticks on both sides of her head.",
    "Same, ticks slightly bigger.",
], FRONT)

anim("sigh", "Sighing", "Standing, front view, she sighs and crosses her arms, annoyed. The small puff of breath is white-grey.", [
    "Neutral, arms at her sides.",
    "Slight frown, eyes looking down.",
    "Mouth a small 'o', shoulders rise.",
    "Eyes closed, exhaling a small white puff beside her cheek, shoulders drop.",
    "Eyes closed, arms start to cross.",
    "Arms crossed over her chest, eyes closed.",
    "Arms crossed, eyes half open looking aside, annoyed.",
    "Arms crossed, eyes open, annoyed look at the camera.",
], FRONT)

anim("wake", "Waking up", "Standing, front view, she wakes up: yawns, rubs her eye and becomes alert. Effect marks are tiny and near-black or white.", [
    "Eyes closed, asleep on her feet, head slightly down.",
    "Eyes closed, a tiny white bubble at her nose.",
    "Yawning: her hand covers her mouth, eyes closed.",
    "Hand lowered to her chin, eyes squinting.",
    "Fist rubbing her eye.",
    "Eyes open wide, alert, two small startle ticks above her head.",
    "Eyes open, neutral.",
    "Eyes open, calm, one tiny white sparkle at the top right of the cell.",
], FRONT)

anim("tantrum", "Stamping her feet", "A little tantrum: she stamps her feet and shouts. Three-quarter view facing the viewer's RIGHT. Effect marks are short near-black ticks.", [
    "Standing, eyes narrowed, two angry ticks beside her head.",
    "Fists clenched at her chest, a small angry mark above her head.",
    "Hops up slightly with both fists raised, mouth open shouting.",
    "Higher in the air, fists up, mouth open, tiny motion ticks under her feet.",
    "Still airborne, arms up, eyes shut tight.",
    "Coming down, stomping, motion ticks.",
    "Landing stamp, eyes squeezed, ticks around her feet.",
    "Standing and pouting, looking down, hands clasped in front, one small droop mark beside her head.",
], "NO shadow on the floor.")


# --------------------------------------------------------------------------
def master_prompt() -> str:
    return f"""\
Using the attached reference image as the exact design source, create a pixel-art CHARACTER MASTER SHEET for a 2D game sprite.

{STYLE}

{CHARACTER}

This image has exactly 4 poses in a row, left to right:
""" + "\n".join(f"{i}. {t}" for i, t in enumerate(MASTER_FRAMES, 1)) + f"""

{layout(4, 45)}
All 4 poses are the same standing relaxed character at the same scale on the same baseline."""


def part_prompt(sheet, plan_part, parts) -> str:
    key = sheet.anim
    d = ANIMS[key]
    total = sheet.rows * sheet.cols
    frames = d["frames"]
    assert len(frames) == total, f"{key}: {len(frames)} frases para {total} quadros"
    lo, hi = plan_part.first, plan_part.first + plan_part.count
    lines = [f"{i + 1}. {frames[g]}" for i, g in enumerate(range(lo, hi))]
    extra = ""
    if len(parts) > 1:
        idx = parts.index(plan_part)
        extra = (f"\nThis image is part {idx + 1} of {len(parts)} of ONE animation (frames {lo + 1} to {hi} of {total}). "
                 + ("" if idx == 0 else "The previous part is attached: keep exactly the same character, pixel size, scale, camera, baseline and colours, and continue the motion seamlessly. ")
                 + "Frame numbers below restart at 1 for this image.\n")
    pct = P.fit_percent(key, plan_part.count)
    note = f"\nNOTES: {d['note']}\n" if d["note"] else ""
    return f"""\
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

{STYLE}

{CHARACTER}

ANIMATION: "{d['title']}". {d['intro']}{extra}
Exactly {plan_part.count} frames:
""" + "\n".join(lines) + f"""
{note}
{layout(plan_part.count, pct, d["base"])}"""


def build() -> str:
    out: List[str] = []
    out.append(HOWTO)
    out.append("\n---\n\n## 00 · Folha mestra\n")
    out.append("Anexe a sua imagem de referência. Salve o resultado como `sprites_novos/gerado/00-mestre.png`.\n")
    out.append("```text\n" + master_prompt() + "\n```\n")
    n = 0
    for sheet in SHEETS:
        parts = P.parts_of(sheet)
        for part in parts:
            n += 1
            name = P.stem(sheet) + part.suffix
            attach = "referência + `00-mestre.png`" + (" + a parte anterior" if part.suffix not in ("", "_a") else "")
            out.append(f"\n---\n\n## {P.stem(sheet).split('-')[0]} · {ANIMS[sheet.anim]['title']}"
                       + (f" (parte {part.suffix[1:].upper()} de {len(parts)})" if part.suffix else "") + "\n")
            out.append(f"Anexar: {attach}. Salvar como `sprites_novos/gerado/{name}.png` ({part.count} quadros).\n")
            out.append("```text\n" + part_prompt(sheet, part, parts) + "\n```\n")
    out.append(f"\n---\n\nTotal: 1 folha mestra + {n} imagens.\n")
    return "\n".join(out)


HOWTO = """\
# Prompts para recriar os sprites da Victorique

Gerado por `scripts/sprite_prompts.py` (edite o personagem e o estilo lá e rode de novo).

## Passo a passo

1. **Folha mestra (prompt 00).** Anexe a sua imagem de referência e gere até ficar do jeito que você quer: é ela que fixa rosto, cabelo, roupa e paleta de todas as outras. Salve como `sprites_novos/gerado/00-mestre.png`.
2. **Paleta.** Rode `.venv\\Scripts\\python.exe scripts\\postprocess_sprites.py paleta`. Ela tira ~36 cores da mestra, e todos os sprites serão forçados a usar só essas cores (é isso que une o estilo).
3. **Cada imagem abaixo.** Abra um chat novo no ChatGPT (chats longos fazem o desenho derivar), anexe o que o item pede, cole o prompt e escolha formato horizontal 3:2 se o ChatGPT oferecer. Salve em `sprites_novos/gerado/` com o nome indicado. Gere de novo só as imagens que saírem ruins.
4. **Conferir o andamento.** `scripts\\postprocess_sprites.py status` mostra o que falta.
5. **Pós-processar.** `scripts\\postprocess_sprites.py processar` limpa o fundo, alinha a grade de pixels, aplica a paleta, junta as partes e grava as folhas prontas no lugar das antigas, em `app/mascot/assets/source/` (prévias em `sprites_novos/previa/`).
6. **Montar o atlas do mascote.** `scripts\\build_mascot_sprites.py --debug sprites_novos\\debug`.

## Dicas

- O fundo precisa sair magenta chapado (#FF00FF). Se vier branco, cinza ou com sombra no chão, gere de novo (branco ainda funciona, sombra não).
- Se o ChatGPT recusar por causa do personagem, não cite nome: os prompts já descrevem o visual por inteiro.
- Se um quadro sair com a figura cortada ou encostando no vizinho, o `processar` avisa.
- Frase do prompt que não colar bem (ex.: pose errada)? Reescreva só aquele quadro no prompt e gere de novo.
"""


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(), encoding="utf-8")
    total = 1 + sum(len(P.parts_of(s)) for s in SHEETS)
    print(f"{total} prompts -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
