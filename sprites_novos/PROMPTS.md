# Prompts para recriar os sprites da Victorique

Gerado por `scripts/sprite_prompts.py` (edite o personagem e o estilo lá e rode de novo).

## Passo a passo

1. **Folha mestra (prompt 00).** Anexe a sua imagem de referência e gere até ficar do jeito que você quer: é ela que fixa rosto, cabelo, roupa e paleta de todas as outras. Salve como `sprites_novos/gerado/00-mestre.png`.
2. **Paleta.** Rode `.venv\Scripts\python.exe scripts\postprocess_sprites.py paleta`. Ela tira ~36 cores da mestra, e todos os sprites serão forçados a usar só essas cores (é isso que une o estilo).
3. **Cada imagem abaixo.** Abra um chat novo no ChatGPT (chats longos fazem o desenho derivar), anexe o que o item pede, cole o prompt e escolha formato horizontal 3:2 se o ChatGPT oferecer. Salve em `sprites_novos/gerado/` com o nome indicado. Gere de novo só as imagens que saírem ruins.
4. **Conferir o andamento.** `scripts\postprocess_sprites.py status` mostra o que falta.
5. **Pós-processar.** `scripts\postprocess_sprites.py processar` limpa o fundo, alinha a grade de pixels, aplica a paleta, junta as partes e grava as folhas prontas no lugar das antigas, em `app/mascot/assets/source/` (prévias em `sprites_novos/previa/`).
6. **Montar o atlas do mascote.** `scripts\build_mascot_sprites.py --debug sprites_novos\debug`.

## Dicas

- O fundo precisa sair magenta chapado (#FF00FF). Se vier branco, cinza ou com sombra no chão, gere de novo (branco ainda funciona, sombra não).
- Se o ChatGPT recusar por causa do personagem, não cite nome: os prompts já descrevem o visual por inteiro.
- Se um quadro sair com a figura cortada ou encostando no vizinho, o `processar` avisa.
- Frase do prompt que não colar bem (ex.: pose errada)? Reescreva só aquele quadro no prompt e gere de novo.


---

## 00 · Folha mestra

Anexe a sua imagem de referência. Salve o resultado como `sprites_novos/gerado/00-mestre.png`.

```text
Using the attached reference image as the exact design source, create a pixel-art CHARACTER MASTER SHEET for a 2D game sprite.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

This image has exactly 4 poses in a row, left to right:
1. Front view, standing relaxed, arms hanging at her sides, neutral calm face, mouth closed.
2. Three-quarter view facing the viewer's right, standing relaxed (the ribbon bow trails behind her head on the viewer's left).
3. Three-quarter view facing the viewer's left, standing relaxed (the ribbon bow is on the viewer's right).
4. Back view, standing relaxed, showing the long hair falling down her back and the back of the bonnet with the bow.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 4 frames, left to right = frame 1 to frame 4. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 45% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
All 4 poses are the same standing relaxed character at the same scale on the same baseline.
```


---

## 01 · Walk cycle

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/01-andar.png` (6 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Walk cycle". A looping side-walk. She faces the viewer's LEFT in three-quarter side view and walks to the left; the ribbon bow and the long hair trail behind her on the right.
Exactly 6 frames:
1. Contact pose: the front foot (viewer's left) reaches forward, the back foot is behind, arms swing lightly, hair trailing behind.
2. Down pose: weight lands on the front foot, body at its lowest, skirt sways.
3. Passing pose: back foot passes under the skirt, legs together, body at its highest, hair lifts a little.
4. Contact pose with the opposite foot forward.
5. Down pose on that foot, body lowest.
6. Passing pose again on the other side, body highest (loops back to frame 1).

NOTES: Feet are mostly hidden by the skirt: show the skirt hem swaying and only the toes peeking out.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 6 frames, left to right = frame 1 to frame 6. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 40% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 02 · Mood faces

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/02-humores.png` (6 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Mood faces". Standing idle. ONLY the face changes (and tiny effect marks); the body is frozen and identical in all frames.
Exactly 6 frames:
1. Calm neutral face, mouth closed.
2. Annoyed: eyes narrowed, one brow lowered, two tiny black tick marks beside the head on the viewer's right.
3. Sulky: eyes narrowed and looking aside, mouth slightly pursed.
4. Bored: half-lidded eyes, flat mouth.
5. Eyes closed, a smug little sigh with a tiny white puff next to her cheek on the viewer's right.
6. Calm neutral face again, identical to frame 1.

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 6 frames, left to right = frame 1 to frame 6. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 41% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 03 · Talking

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/03-falar.png` (6 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Talking". Standing idle while talking. Mouth shapes cycle; one hand rises to her chest.
Exactly 6 frames:
1. Neutral, mouth closed, both arms hanging.
2. Mouth slightly open (small oval), her right hand (viewer's left) lifts to her chest.
3. Mouth open wider mid-speech, eyes closed for a moment, hand at her chin.
4. Mouth closed, eyes closed, hand at her chin.
5. Mouth small open, eyes open, hand at her chest.
6. Mouth closed, hand lowered back to her side, neutral (loops back to frame 1).

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 6 frames, left to right = frame 1 to frame 6. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 40% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 04 · Blink

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/04-piscar.png` (6 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Blink". Standing idle: a blink with a very slight breathing bob.
Exactly 6 frames:
1. Eyes fully open, neutral.
2. Eyelids half lowered.
3. Eyes closed.
4. Eyes closed, head dips one pixel.
5. Eyes half open.
6. Eyes fully open, identical to frame 1.

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 6 frames, left to right = frame 1 to frame 6. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 41% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 05 · Sitting down

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/05-sentar.png` (6 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Sitting down". She sits down on the floor gracefully, ending in a neat seated pose with the skirt fanned out.
Exactly 6 frames:
1. Standing relaxed, front view, neutral.
2. Knees bend slightly, hands move down to the skirt.
3. Crouching lower, skirt starts to puff outward, hands on the skirt.
4. Almost down, skirt spreading wide around her.
5. Seated on the floor, skirt fanned out in a wide round shape, hands resting on her lap.
6. Settled seated pose, hands neatly folded on her lap, calm face.

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes. In frames 5-6 the bottom of the spread skirt touches the baseline.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 6 frames, left to right = frame 1 to frame 6. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 37% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 06 · Sitting idle (parte A de 2)

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/06-sentada_a.png` (3 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Sitting idle". Seated on the floor, front view, skirt fanned out in a wide round shape, hands folded on her lap. A subtle idle loop.
This image is part 1 of 2 of ONE animation (frames 1 to 3 of 6). Frame numbers below restart at 1 for this image.

Exactly 3 frames:
1. Calm face, eyes open.
2. Body one pixel higher (inhale), eyes open.
3. Eyes closed (blink).

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes. The bottom of the skirt rests on the baseline.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 3 frames, left to right = frame 1 to frame 3. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 45% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 06 · Sitting idle (parte B de 2)

Anexar: referência + `00-mestre.png` + a parte anterior. Salvar como `sprites_novos/gerado/06-sentada_b.png` (3 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Sitting idle". Seated on the floor, front view, skirt fanned out in a wide round shape, hands folded on her lap. A subtle idle loop.
This image is part 2 of 2 of ONE animation (frames 4 to 6 of 6). The previous part is attached: keep exactly the same character, pixel size, scale, camera, baseline and colours, and continue the motion seamlessly. Frame numbers below restart at 1 for this image.

Exactly 3 frames:
1. Eyes open, head tilted very slightly toward the viewer's right.
2. Head back to centre, eyes open.
3. Calm face, identical to frame 1.

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes. The bottom of the skirt rests on the baseline.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 3 frames, left to right = frame 1 to frame 3. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 45% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 07 · Turning

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/07-virar.png` (6 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Turning". She turns in place between facing the camera and a three-quarter side view, standing relaxed.
Exactly 6 frames:
1. Three-quarter view facing the viewer's right (the bow trails behind her head on the viewer's left).
2. Turning: head and body closer to the front, still slightly to the viewer's right.
3. Full front view, neutral, arms at her sides.
4. Turning: slightly toward the viewer's left.
5. Three-quarter view facing the viewer's left (the bow is on the viewer's right behind the head).
6. Same three-quarter view facing the viewer's left, hair swaying a tiny bit differently.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 6 frames, left to right = frame 1 to frame 6. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 38% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 08 · Standing up (parte A de 2)

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/08-levantar_a.png` (3 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Standing up". She gets up from sitting on the floor to a relaxed standing pose (the reverse of sitting down).
This image is part 1 of 2 of ONE animation (frames 1 to 3 of 6). Frame numbers below restart at 1 for this image.

Exactly 3 frames:
1. Seated on the floor, skirt fanned out, hands on her lap.
2. Hands press on the floor and skirt, body leans slightly forward.
3. Rising onto her knees, skirt still wide.

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes. The lowest point of the figure rests on the baseline in every frame.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 3 frames, left to right = frame 1 to frame 3. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 45% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 08 · Standing up (parte B de 2)

Anexar: referência + `00-mestre.png` + a parte anterior. Salvar como `sprites_novos/gerado/08-levantar_b.png` (3 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Standing up". She gets up from sitting on the floor to a relaxed standing pose (the reverse of sitting down).
This image is part 2 of 2 of ONE animation (frames 4 to 6 of 6). The previous part is attached: keep exactly the same character, pixel size, scale, camera, baseline and colours, and continue the motion seamlessly. Frame numbers below restart at 1 for this image.

Exactly 3 frames:
1. Half standing, skirt gathering downward.
2. Almost upright, small skirt sway.
3. Standing upright, relaxed, neutral calm face.

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes. The lowest point of the figure rests on the baseline in every frame.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 3 frames, left to right = frame 1 to frame 3. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 45% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 09 · Dragged by the mouse cursor (parte A de 4)

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/09-arrastada_a.png` (3 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Dragged by the mouse cursor". She is grabbed and dragged by a mouse-pointer arrow, and dangles from it while swinging. Facing the viewer's RIGHT (three-quarter view).
This image is part 1 of 4 of ONE animation (frames 1 to 3 of 12). Frame numbers below restart at 1 for this image.

Exactly 3 frames:
1. Hanging straight down from the cursor, feet dangling, calm face.
2. Hanging, surprised face (wide eyes), two tiny black tick marks near her head.
3. Body swings a little to the viewer's left, feet lift, hair starts to trail left.

NOTES: THE CURSOR: a classic white mouse-pointer arrow (pure white fill #FFFFFF with a thin black outline, tip pointing up and to the left) drawn at the upper right of her. Her stretched right arm holds the lower-left edge of the arrow. The arrow is the same size and in the exact same spot of its cell in every frame; only she moves. The arrow is the ONLY pure white thing on the right side of the cell. Her cuffs and bow stay cream, not pure white.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 3 frames, left to right = frame 1 to frame 3. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 36% of the image height. The tip of the mouse cursor is at exactly the same position inside its cell in every frame. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 09 · Dragged by the mouse cursor (parte B de 4)

Anexar: referência + `00-mestre.png` + a parte anterior. Salvar como `sprites_novos/gerado/09-arrastada_b.png` (3 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Dragged by the mouse cursor". She is grabbed and dragged by a mouse-pointer arrow, and dangles from it while swinging. Facing the viewer's RIGHT (three-quarter view).
This image is part 2 of 4 of ONE animation (frames 4 to 6 of 12). The previous part is attached: keep exactly the same character, pixel size, scale, camera, baseline and colours, and continue the motion seamlessly. Frame numbers below restart at 1 for this image.

Exactly 3 frames:
1. Legs bent, skirt flaring, hair trailing left, slightly worried face.
2. Body swings more toward horizontal to the viewer's left, hair streaming left.
3. Almost horizontal like a flag, hair and skirt flying left, annoyed face.

NOTES: THE CURSOR: a classic white mouse-pointer arrow (pure white fill #FFFFFF with a thin black outline, tip pointing up and to the left) drawn at the upper right of her. Her stretched right arm holds the lower-left edge of the arrow. The arrow is the same size and in the exact same spot of its cell in every frame; only she moves. The arrow is the ONLY pure white thing on the right side of the cell. Her cuffs and bow stay cream, not pure white.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 3 frames, left to right = frame 1 to frame 3. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 36% of the image height. The tip of the mouse cursor is at exactly the same position inside its cell in every frame. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 09 · Dragged by the mouse cursor (parte C de 4)

Anexar: referência + `00-mestre.png` + a parte anterior. Salvar como `sprites_novos/gerado/09-arrastada_c.png` (3 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Dragged by the mouse cursor". She is grabbed and dragged by a mouse-pointer arrow, and dangles from it while swinging. Facing the viewer's RIGHT (three-quarter view).
This image is part 3 of 4 of ONE animation (frames 7 to 9 of 12). The previous part is attached: keep exactly the same character, pixel size, scale, camera, baseline and colours, and continue the motion seamlessly. Frame numbers below restart at 1 for this image.

Exactly 3 frames:
1. Horizontal, eyes squeezed shut, hair and skirt flying left.
2. Horizontal, eyes squeezed shut in an angry '> <' look.
3. Swinging back, small impact tick marks near her head.

NOTES: THE CURSOR: a classic white mouse-pointer arrow (pure white fill #FFFFFF with a thin black outline, tip pointing up and to the left) drawn at the upper right of her. Her stretched right arm holds the lower-left edge of the arrow. The arrow is the same size and in the exact same spot of its cell in every frame; only she moves. The arrow is the ONLY pure white thing on the right side of the cell. Her cuffs and bow stay cream, not pure white.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 3 frames, left to right = frame 1 to frame 3. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 36% of the image height. The tip of the mouse cursor is at exactly the same position inside its cell in every frame. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 09 · Dragged by the mouse cursor (parte D de 4)

Anexar: referência + `00-mestre.png` + a parte anterior. Salvar como `sprites_novos/gerado/09-arrastada_d.png` (3 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Dragged by the mouse cursor". She is grabbed and dragged by a mouse-pointer arrow, and dangles from it while swinging. Facing the viewer's RIGHT (three-quarter view).
This image is part 4 of 4 of ONE animation (frames 10 to 12 of 12). The previous part is attached: keep exactly the same character, pixel size, scale, camera, baseline and colours, and continue the motion seamlessly. Frame numbers below restart at 1 for this image.

Exactly 3 frames:
1. Swinging back toward hanging, hair swaying.
2. Hanging again, legs swaying, slight frown.
3. Hanging almost straight, calm, looking toward the viewer.

NOTES: THE CURSOR: a classic white mouse-pointer arrow (pure white fill #FFFFFF with a thin black outline, tip pointing up and to the left) drawn at the upper right of her. Her stretched right arm holds the lower-left edge of the arrow. The arrow is the same size and in the exact same spot of its cell in every frame; only she moves. The arrow is the ONLY pure white thing on the right side of the cell. Her cuffs and bow stay cream, not pure white.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 3 frames, left to right = frame 1 to frame 3. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 36% of the image height. The tip of the mouse cursor is at exactly the same position inside its cell in every frame. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 10 · Jump (parte A de 2)

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/10-pular_a.png` (4 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Jump". A jump from standing to landing, facing the viewer's RIGHT (three-quarter view), skirt and hair reacting to the motion.
This image is part 1 of 2 of ONE animation (frames 1 to 4 of 8). Frame numbers below restart at 1 for this image.

Exactly 4 frames:
1. Standing three-quarter right, about to crouch, knees just starting to bend.
2. Crouching, knees bent, body lowered, arms pulled back.
3. Deepest crouch, skirt compressed, hair settling.
4. Take-off: legs extending, feet leaving the ground, arms swinging up.

NOTES: NO shadow on the floor under her, even when airborne.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 4 frames, left to right = frame 1 to frame 4. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 44% of the image height. On the ground, the lowest point of the figure rests on one invisible horizontal baseline near the lower third of the image (the same in every frame); in airborne frames she floats above that baseline. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 10 · Jump (parte B de 2)

Anexar: referência + `00-mestre.png` + a parte anterior. Salvar como `sprites_novos/gerado/10-pular_b.png` (4 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Jump". A jump from standing to landing, facing the viewer's RIGHT (three-quarter view), skirt and hair reacting to the motion.
This image is part 2 of 2 of ONE animation (frames 5 to 8 of 8). The previous part is attached: keep exactly the same character, pixel size, scale, camera, baseline and colours, and continue the motion seamlessly. Frame numbers below restart at 1 for this image.

Exactly 4 frames:
1. Rising: body stretched, feet off the ground, hair streaming down and back.
2. Apex: knees tucked, skirt billowing, arms up.
3. Descending: legs extending down, skirt rising, hair floating up.
4. Landing: knees bent absorbing the impact, a few tiny grey dust ticks at her feet.

NOTES: NO shadow on the floor under her, even when airborne.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 4 frames, left to right = frame 1 to frame 4. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 44% of the image height. On the ground, the lowest point of the figure rests on one invisible horizontal baseline near the lower third of the image (the same in every frame); in airborne frames she floats above that baseline. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 11 · Fall and recovery (parte A de 2)

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/11-cair_a.png` (4 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Fall and recovery". She falls through the air, hits the floor and gets back up. Facing the viewer's RIGHT (three-quarter view).
This image is part 1 of 2 of ONE animation (frames 1 to 4 of 8). Frame numbers below restart at 1 for this image.

Exactly 4 frames:
1. Falling: arms flailing, hair streaming upward, legs dangling, eyes wide.
2. Falling faster: hair straight up, skirt billowing, mouth open.
3. About to land: legs bent, arms out.
4. Impact: crouched flat on the floor, hands down, eyes shut tight, a few small grey-white dust puffs around her.

NOTES: NO shadow on the floor under her.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 4 frames, left to right = frame 1 to frame 4. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 45% of the image height. On the ground, the lowest point of the figure rests on one invisible horizontal baseline near the lower third of the image (the same in every frame); in airborne frames she floats above that baseline. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 11 · Fall and recovery (parte B de 2)

Anexar: referência + `00-mestre.png` + a parte anterior. Salvar como `sprites_novos/gerado/11-cair_b.png` (4 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Fall and recovery". She falls through the air, hits the floor and gets back up. Facing the viewer's RIGHT (three-quarter view).
This image is part 2 of 2 of ONE animation (frames 5 to 8 of 8). The previous part is attached: keep exactly the same character, pixel size, scale, camera, baseline and colours, and continue the motion seamlessly. Frame numbers below restart at 1 for this image.

Exactly 4 frames:
1. Dazed on the floor on hands and knees.
2. Rising to a crouch, one hand on the floor.
3. Half standing, brushing herself off.
4. Standing upright, composed, neutral face.

NOTES: NO shadow on the floor under her.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 4 frames, left to right = frame 1 to frame 4. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 45% of the image height. On the ground, the lowest point of the figure rests on one invisible horizontal baseline near the lower third of the image (the same in every frame); in airborne frames she floats above that baseline. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 12 · Climbing a wall (parte A de 4)

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/12-escalar_a.png` (3 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Climbing a wall". She climbs up the face of a vertical wall that is on her RIGHT (the wall is invisible: do not draw it). Three-quarter back/side view facing the viewer's right, hands reaching up and to the right.
This image is part 1 of 4 of ONE animation (frames 1 to 3 of 12). Frame numbers below restart at 1 for this image.

Exactly 3 frames:
1. Standing three-quarter facing right, looking at the wall.
2. Raises her right hand up toward the wall, body leaning to the right.
3. Climb cycle step 1: right hand high, left knee raised, body stretched up along the wall.

NOTES: Frames 3-10 are one 8-step looping cycle: frame 10 must lead smoothly back into frame 3. Keep the rightmost edge of her hand/arm roughly at the same distance from the wall line in every frame.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 3 frames, left to right = frame 1 to frame 3. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 45% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 12 · Climbing a wall (parte B de 4)

Anexar: referência + `00-mestre.png` + a parte anterior. Salvar como `sprites_novos/gerado/12-escalar_b.png` (3 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Climbing a wall". She climbs up the face of a vertical wall that is on her RIGHT (the wall is invisible: do not draw it). Three-quarter back/side view facing the viewer's right, hands reaching up and to the right.
This image is part 2 of 4 of ONE animation (frames 4 to 6 of 12). The previous part is attached: keep exactly the same character, pixel size, scale, camera, baseline and colours, and continue the motion seamlessly. Frame numbers below restart at 1 for this image.

Exactly 3 frames:
1. Climb cycle step 2: pulling up with the right arm, body rising.
2. Climb cycle step 3: left hand reaches higher, right knee raised.
3. Climb cycle step 4: pulling up with the left arm.

NOTES: Frames 3-10 are one 8-step looping cycle: frame 10 must lead smoothly back into frame 3. Keep the rightmost edge of her hand/arm roughly at the same distance from the wall line in every frame.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 3 frames, left to right = frame 1 to frame 3. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 45% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 12 · Climbing a wall (parte C de 4)

Anexar: referência + `00-mestre.png` + a parte anterior. Salvar como `sprites_novos/gerado/12-escalar_c.png` (3 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Climbing a wall". She climbs up the face of a vertical wall that is on her RIGHT (the wall is invisible: do not draw it). Three-quarter back/side view facing the viewer's right, hands reaching up and to the right.
This image is part 3 of 4 of ONE animation (frames 7 to 9 of 12). The previous part is attached: keep exactly the same character, pixel size, scale, camera, baseline and colours, and continue the motion seamlessly. Frame numbers below restart at 1 for this image.

Exactly 3 frames:
1. Climb cycle step 5: right hand high again, left knee raised, hair hanging down her back.
2. Climb cycle step 6: pulling up with the right arm.
3. Climb cycle step 7: left hand high, right knee raised.

NOTES: Frames 3-10 are one 8-step looping cycle: frame 10 must lead smoothly back into frame 3. Keep the rightmost edge of her hand/arm roughly at the same distance from the wall line in every frame.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 3 frames, left to right = frame 1 to frame 3. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 45% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 12 · Climbing a wall (parte D de 4)

Anexar: referência + `00-mestre.png` + a parte anterior. Salvar como `sprites_novos/gerado/12-escalar_d.png` (3 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Climbing a wall". She climbs up the face of a vertical wall that is on her RIGHT (the wall is invisible: do not draw it). Three-quarter back/side view facing the viewer's right, hands reaching up and to the right.
This image is part 4 of 4 of ONE animation (frames 10 to 12 of 12). The previous part is attached: keep exactly the same character, pixel size, scale, camera, baseline and colours, and continue the motion seamlessly. Frame numbers below restart at 1 for this image.

Exactly 3 frames:
1. Climb cycle step 8: pulling up with the left arm (the cycle then repeats from step 1).
2. Reaching the top: leaning forward over the ledge, one knee up.
3. Standing upright on top, three-quarter facing right, relaxed.

NOTES: Frames 3-10 are one 8-step looping cycle: frame 10 must lead smoothly back into frame 3. Keep the rightmost edge of her hand/arm roughly at the same distance from the wall line in every frame.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 3 frames, left to right = frame 1 to frame 3. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 45% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 13 · Sitting on a ledge (parte A de 2)

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/13-beirada_a.png` (6 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Sitting on a ledge". She sits on the edge of a window frame (an invisible ledge: do not draw it), front view, legs dangling and swinging gently. A 12-frame loop.
This image is part 1 of 2 of ONE animation (frames 1 to 6 of 12). Frame numbers below restart at 1 for this image.

Exactly 6 frames:
1. Both legs dangling straight down together, hands resting at her sides on the ledge.
2. Her left leg (viewer's right) lifts slightly forward.
3. Left leg swings further forward.
4. Left leg at its highest swing, head tilts a hair.
5. Left leg swinging back down.
6. Both legs together again.

NOTES: Seated on a ledge: the bunched skirt rests at the seat line and her lower legs in black stockings with small black shoes dangle below it.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 6 frames, left to right = frame 1 to frame 6. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 40% of the image height. The seat line (where the skirt rests on the ledge) is at exactly the same height in every frame, near the middle of the image; the legs dangle below it. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 13 · Sitting on a ledge (parte B de 2)

Anexar: referência + `00-mestre.png` + a parte anterior. Salvar como `sprites_novos/gerado/13-beirada_b.png` (6 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Sitting on a ledge". She sits on the edge of a window frame (an invisible ledge: do not draw it), front view, legs dangling and swinging gently. A 12-frame loop.
This image is part 2 of 2 of ONE animation (frames 7 to 12 of 12). The previous part is attached: keep exactly the same character, pixel size, scale, camera, baseline and colours, and continue the motion seamlessly. Frame numbers below restart at 1 for this image.

Exactly 6 frames:
1. Her right leg (viewer's left) lifts slightly forward, eyes blink.
2. Right leg swings further forward.
3. Right leg at its highest swing.
4. Right leg swinging back down.
5. Right leg nearly together with the left.
6. Both legs together, identical to frame 1 (loops).

NOTES: Seated on a ledge: the bunched skirt rests at the seat line and her lower legs in black stockings with small black shoes dangle below it.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 6 frames, left to right = frame 1 to frame 6. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 40% of the image height. The seat line (where the skirt rests on the ledge) is at exactly the same height in every frame, near the middle of the image; the legs dangle below it. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 14 · Peeking from behind a wall (parte A de 2)

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/14-espiar_a.png` (5 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Peeking from behind a wall". She hides behind a vertical wall edge and peeks out. The wall is on the LEFT of each cell and is invisible: every frame is cut by a perfectly straight vertical line at its LEFT side, and whatever is behind that line is simply missing. Only the part of her to the right of that line is drawn. She leans out toward the viewer's right.
This image is part 1 of 2 of ONE animation (frames 1 to 5 of 9). Frame numbers below restart at 1 for this image.

Exactly 5 frames:
1. Almost hidden: only a thin sliver of the bonnet edge and hair is visible at the cut line.
2. A bit more: bonnet edge and one eye.
3. Head half out: half of the face, the bonnet and part of the bow.
4. Face about two thirds out, curious look.
5. Face almost fully out, looking at the viewer.

NOTES: In every frame the straight cut line is at the same x position inside its cell and runs the full height of the figure. The bottom of the visible part rests on the baseline.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 5 frames, left to right = frame 1 to frame 5. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 45% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 14 · Peeking from behind a wall (parte B de 2)

Anexar: referência + `00-mestre.png` + a parte anterior. Salvar como `sprites_novos/gerado/14-espiar_b.png` (4 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Peeking from behind a wall". She hides behind a vertical wall edge and peeks out. The wall is on the LEFT of each cell and is invisible: every frame is cut by a perfectly straight vertical line at its LEFT side, and whatever is behind that line is simply missing. Only the part of her to the right of that line is drawn. She leans out toward the viewer's right.
This image is part 2 of 2 of ONE animation (frames 6 to 9 of 9). The previous part is attached: keep exactly the same character, pixel size, scale, camera, baseline and colours, and continue the motion seamlessly. Frame numbers below restart at 1 for this image.

Exactly 4 frames:
1. Fully out: face, shoulder and long hair hanging.
2. Fully out with a small hand gripping the wall edge, slight smile.
3. Same as frame 7 but eyes closed (blink).
4. Retreating: sliver of bonnet and hair again, eyes closed.

NOTES: In every frame the straight cut line is at the same x position inside its cell and runs the full height of the figure. The bottom of the visible part rests on the baseline.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 4 frames, left to right = frame 1 to frame 4. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 45% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 15 · Drinking tea (parte A de 2)

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/15-cha_a.png` (6 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Drinking tea". Standing, front view, holding a small white porcelain teacup on a saucer in both hands. A looping sip.
This image is part 1 of 2 of ONE animation (frames 1 to 6 of 12). Frame numbers below restart at 1 for this image.

Exactly 6 frames:
1. Holding the cup and saucer at waist height, calm face.
2. Cup lifted slightly.
3. Cup lifted to chest height.
4. Cup at chin height, eyes starting to close.
5. Cup at her lips, eyes closed.
6. Sipping, cup tilted, eyes closed.

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 6 frames, left to right = frame 1 to frame 6. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 45% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 15 · Drinking tea (parte B de 2)

Anexar: referência + `00-mestre.png` + a parte anterior. Salvar como `sprites_novos/gerado/15-cha_b.png` (6 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Drinking tea". Standing, front view, holding a small white porcelain teacup on a saucer in both hands. A looping sip.
This image is part 2 of 2 of ONE animation (frames 7 to 12 of 12). The previous part is attached: keep exactly the same character, pixel size, scale, camera, baseline and colours, and continue the motion seamlessly. Frame numbers below restart at 1 for this image.

Exactly 6 frames:
1. Still sipping, cup tilted.
2. Lowering the cup, eyes half open.
3. Cup at chin height, eyes open.
4. Cup at chest height, small contented face.
5. Cup lower, near waist.
6. Cup at waist height, identical to frame 1 (loops).

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 6 frames, left to right = frame 1 to frame 6. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 45% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 16 · Reading a book (parte A de 2)

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/16-ler_a.png` (6 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Reading a book". Standing, front view, holding an open brown leather book in both hands at chest height, eyes looking down at it. A looping page turn.
This image is part 1 of 2 of ONE animation (frames 1 to 6 of 12). Frame numbers below restart at 1 for this image.

Exactly 6 frames:
1. Holding the open book, eyes down on the pages.
2. Head tilts very slightly.
3. Blink (eyes closed).
4. Eyes down, reading.
5. Eyes down, her right hand starts to lift a page corner.
6. Page lifting.

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 6 frames, left to right = frame 1 to frame 6. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 39% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 16 · Reading a book (parte B de 2)

Anexar: referência + `00-mestre.png` + a parte anterior. Salvar como `sprites_novos/gerado/16-ler_b.png` (6 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Reading a book". Standing, front view, holding an open brown leather book in both hands at chest height, eyes looking down at it. A looping page turn.
This image is part 2 of 2 of ONE animation (frames 7 to 12 of 12). The previous part is attached: keep exactly the same character, pixel size, scale, camera, baseline and colours, and continue the motion seamlessly. Frame numbers below restart at 1 for this image.

Exactly 6 frames:
1. Page half turned (curved page).
2. Page turned over, hand returning.
3. Eyes down, reading the new page.
4. Eyes shift a little to the side, still reading.
5. Blink (eyes closed).
6. Eyes down, identical to frame 1 (loops).

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 6 frames, left to right = frame 1 to frame 6. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 39% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 17 · Closing the book

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/17-fechar-livro.png` (6 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Closing the book". Standing, front view. She finishes reading, closes the book and lets it go.
Exactly 6 frames:
1. Holding an open brown book at chest height, eyes down.
2. Eyes drooping, half-lidded.
3. Eyes closed, the book half closed between her hands.
4. Book closed, held against her chest.
5. Book held low at her hip with one hand, the other arm relaxing.
6. No book anymore, both arms relaxed at her sides, neutral face.

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 6 frames, left to right = frame 1 to frame 6. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 41% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 18 · Glancing around

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/18-olhar.png` (6 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Glancing around". Standing idle, front view, she looks around with a skeptical air. Mostly eyes and a slight head turn.
Exactly 6 frames:
1. Neutral, looking at the camera.
2. Eyes shift to the viewer's left.
3. Head turns slightly to the viewer's left, eyes left.
4. Head turned a bit more, half-lidded skeptical eyes.
5. Head back to centre, eyes shift to the viewer's right.
6. Back to neutral, looking at the camera.

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 6 frames, left to right = frame 1 to frame 6. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 40% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 19 · Thinking

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/19-pensar.png` (6 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Thinking". Standing, front view, thoughtful pose with a hand to her chin.
Exactly 6 frames:
1. Neutral, arms at her sides.
2. Her right hand (viewer's left) rises toward her chin.
3. Hand at her chin, eyes looking up and aside.
4. Hand at her chin, eyes closed, thinking.
5. Hand at her chin, eyes open looking up to the viewer's left.
6. Hand at her chin, eyes open and focused on the camera.

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 6 frames, left to right = frame 1 to frame 6. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 41% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 20 · Dozing off

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/20-cochilar.png` (6 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Dozing off". Standing, front view, she gets sleepy and nods off while standing; the head droops progressively and the body slouches slightly. Do NOT draw any letters such as Z.
Exactly 6 frames:
1. Eyes open, slightly sleepy.
2. Eyes half closed, head dips a little.
3. Eyes closed, head tilts down.
4. Eyes closed, head lower, body swaying.
5. Head at its lowest, eyes closed.
6. Head rising slowly back up, eyes closed.

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes. The soles stay on the baseline; only the upper body slouches.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 6 frames, left to right = frame 1 to frame 6. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 41% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 21 · Happy

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/21-feliz.png` (6 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Happy". Standing, front view, her face gets happier step by step. Effect marks are tiny orange-gold ticks (#e8a33d).
Exactly 6 frames:
1. A gentle small smile.
2. A bigger smile.
3. Eyes closed in a '^ ^' smile, rosy cheeks.
4. Wide happy smile with eyes closed.
5. Same wide smile, three tiny orange-gold sparkle ticks above her head on the viewer's right.
6. Same, with the sparkle ticks slightly bigger.

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 6 frames, left to right = frame 1 to frame 6. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 40% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 22 · Deduction pointing

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/22-apontar.png` (6 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Deduction pointing". Standing, front view, she makes a deduction and points. Effect marks are tiny orange-gold ticks (#e8a33d).
Exactly 6 frames:
1. Neutral, arms at her sides.
2. Eyes closed, the arm on the viewer's right side starts to lift, forearm rising.
3. Hand at chest, mouth slightly open.
4. Arm extended, pointing with the index finger toward the viewer's right, mouth open.
5. Same pointing pose, three tiny orange-gold emphasis ticks near her head.
6. Arm fully extended pointing to the viewer's right, confident face.

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes. Only the arm on the viewer's RIGHT side moves; it points to the viewer's right.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 6 frames, left to right = frame 1 to frame 6. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 35% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 23 · Confused

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/23-confusa.png` (6 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Confused". Standing, front view, she gets confused. Effect marks (question marks, ticks) are drawn in near-black #1b1a1f.
Exactly 6 frames:
1. Neutral.
2. Eyes wide, small shake ticks on both sides of her head.
3. Head tilted, mouth a small 'o'.
4. Hand at her chin, one small question mark above her head on the viewer's right.
5. Brow furrowed, two small question marks above her head.
6. One hand palm-up in a shrug, one small question mark.

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 6 frames, left to right = frame 1 to frame 6. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 40% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 24 · Surprised

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/24-surpresa.png` (6 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Surprised". Standing, front view, she gets startled. Effect marks are short near-black ticks (#1b1a1f).
Exactly 6 frames:
1. Neutral.
2. Eyes widen, short startle ticks above her head.
3. Mouth a small 'o', hands tighten into fists at her chest.
4. Hands raised to her chest, wide eyes.
5. Both hands cover her mouth, wide eyes, startle ticks on both sides of her head.
6. Same, ticks slightly bigger.

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 6 frames, left to right = frame 1 to frame 6. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 41% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 25 · Sighing (parte A de 2)

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/25-suspirar_a.png` (4 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Sighing". Standing, front view, she sighs and crosses her arms, annoyed. The small puff of breath is white-grey.
This image is part 1 of 2 of ONE animation (frames 1 to 4 of 8). Frame numbers below restart at 1 for this image.

Exactly 4 frames:
1. Neutral, arms at her sides.
2. Slight frown, eyes looking down.
3. Mouth a small 'o', shoulders rise.
4. Eyes closed, exhaling a small white puff beside her cheek, shoulders drop.

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 4 frames, left to right = frame 1 to frame 4. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 45% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 25 · Sighing (parte B de 2)

Anexar: referência + `00-mestre.png` + a parte anterior. Salvar como `sprites_novos/gerado/25-suspirar_b.png` (4 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Sighing". Standing, front view, she sighs and crosses her arms, annoyed. The small puff of breath is white-grey.
This image is part 2 of 2 of ONE animation (frames 5 to 8 of 8). The previous part is attached: keep exactly the same character, pixel size, scale, camera, baseline and colours, and continue the motion seamlessly. Frame numbers below restart at 1 for this image.

Exactly 4 frames:
1. Eyes closed, arms start to cross.
2. Arms crossed over her chest, eyes closed.
3. Arms crossed, eyes half open looking aside, annoyed.
4. Arms crossed, eyes open, annoyed look at the camera.

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 4 frames, left to right = frame 1 to frame 4. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 45% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 26 · Waking up (parte A de 2)

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/26-despertar_a.png` (4 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Waking up". Standing, front view, she wakes up: yawns, rubs her eye and becomes alert. Effect marks are tiny and near-black or white.
This image is part 1 of 2 of ONE animation (frames 1 to 4 of 8). Frame numbers below restart at 1 for this image.

Exactly 4 frames:
1. Eyes closed, asleep on her feet, head slightly down.
2. Eyes closed, a tiny white bubble at her nose.
3. Yawning: her hand covers her mouth, eyes closed.
4. Hand lowered to her chin, eyes squinting.

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 4 frames, left to right = frame 1 to frame 4. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 45% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 26 · Waking up (parte B de 2)

Anexar: referência + `00-mestre.png` + a parte anterior. Salvar como `sprites_novos/gerado/26-despertar_b.png` (4 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Waking up". Standing, front view, she wakes up: yawns, rubs her eye and becomes alert. Effect marks are tiny and near-black or white.
This image is part 2 of 2 of ONE animation (frames 5 to 8 of 8). The previous part is attached: keep exactly the same character, pixel size, scale, camera, baseline and colours, and continue the motion seamlessly. Frame numbers below restart at 1 for this image.

Exactly 4 frames:
1. Fist rubbing her eye.
2. Eyes open wide, alert, two small startle ticks above her head.
3. Eyes open, neutral.
4. Eyes open, calm, one tiny white sparkle at the top right of the cell.

NOTES: Front view (facing the camera) in every frame unless a frame says otherwise. Body, dress, hair and bonnet stay identical from frame to frame; only what the frame says changes.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 4 frames, left to right = frame 1 to frame 4. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 45% of the image height. The lowest point of the figure (soles, hem or seat) rests on the same invisible horizontal baseline in every frame, near the lower third of the image. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 27 · Stamping her feet (parte A de 2)

Anexar: referência + `00-mestre.png`. Salvar como `sprites_novos/gerado/27-birra_a.png` (4 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Stamping her feet". A little tantrum: she stamps her feet and shouts. Three-quarter view facing the viewer's RIGHT. Effect marks are short near-black ticks.
This image is part 1 of 2 of ONE animation (frames 1 to 4 of 8). Frame numbers below restart at 1 for this image.

Exactly 4 frames:
1. Standing, eyes narrowed, two angry ticks beside her head.
2. Fists clenched at her chest, a small angry mark above her head.
3. Hops up slightly with both fists raised, mouth open shouting.
4. Higher in the air, fists up, mouth open, tiny motion ticks under her feet.

NOTES: NO shadow on the floor.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 4 frames, left to right = frame 1 to frame 4. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 45% of the image height. On the ground, the lowest point of the figure rests on one invisible horizontal baseline near the lower third of the image (the same in every frame); in airborne frames she floats above that baseline. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

## 27 · Stamping her feet (parte B de 2)

Anexar: referência + `00-mestre.png` + a parte anterior. Salvar como `sprites_novos/gerado/27-birra_b.png` (4 quadros).

```text
Using the attached reference images (the original design and the approved master sheet) as the exact design source, create a pixel-art sprite sheet for a 2D desktop mascot.

STYLE: high-quality pixel-art game sprite, in the style of the attached reference: chunky, clearly visible square pixels placed by hand, a dark selective outline hugging the silhouette, 3 to 5 flat shading tones per material, crisp hard edges. NO anti-aliasing, NO blur, NO gradients, NO soft or painterly shading, NO glow, NO 3D render, NO photo texture. The pixel size is the same everywhere in the image (about 4x4 image pixels per art pixel) and identical in every frame.

CHARACTER (must match the attached reference images exactly: same face, hair, outfit, colours):
a young girl with a doll-like, pale, calm and slightly aloof face; large teal-green eyes with a small white highlight; tiny nose and mouth; straight blunt bangs; extremely long, wavy, pale golden-blonde hair that reaches her ankles (warm darker-gold shadows, slightly curled ends). On her head: a black gothic bonnet with a ruffled cream-white lace trim around the brim, and one large cream-white ribbon bow with several loops fixed to the side of the bonnet (on the viewer's right side when she faces the camera). Outfit: black Victorian gothic-lolita dress: fitted black bodice with subtle vertical pleats, long black sleeves ending in tiered cream-white frilled cuffs, a small ruffled cream-white collar with a big cream-white bow at the neck/chest, a black open overskirt over a charcoal-grey multi-tiered ruffled skirt that falls to the ankles, small black shoes.
PROPORTIONS: cute chibi-leaning game-sprite proportions: the head (with bonnet) is about 30% of her full standing height; slim small body, small hands, legs mostly hidden by the long skirt. Same proportions in every frame.
COLOURS (stay inside these families): near-black #1b1a1f; charcoal grey #4a4650 and #35323b; cream white #ece3d1 (shadow #b9ad96); pale golden blonde #e6c97c (shadow #b8934e, deep shadow #8a6a36); skin #f4dcc8 (shadow #d9b49c); teal-green eyes #2a7f73 (dark #14423d).

ANIMATION: "Stamping her feet". A little tantrum: she stamps her feet and shouts. Three-quarter view facing the viewer's RIGHT. Effect marks are short near-black ticks.
This image is part 2 of 2 of ONE animation (frames 5 to 8 of 8). The previous part is attached: keep exactly the same character, pixel size, scale, camera, baseline and colours, and continue the motion seamlessly. Frame numbers below restart at 1 for this image.

Exactly 4 frames:
1. Still airborne, arms up, eyes shut tight.
2. Coming down, stomping, motion ticks.
3. Landing stamp, eyes squeezed, ticks around her feet.
4. Standing and pouting, looking down, hands clasped in front, one small droop mark beside her head.

NOTES: NO shadow on the floor.

LAYOUT: ONE image, landscape 3:2, containing a single horizontal row of exactly 4 frames, left to right = frame 1 to frame 4. Each frame sits in its own equal-width invisible cell with wide empty space between frames: nothing may touch, overlap or cross into a neighbouring cell, and each frame is exactly one pose (never two characters in a cell). The character has exactly the same scale and the same straight-on camera (no perspective change) in every frame; the figure is about 45% of the image height. On the ground, the lowest point of the figure rests on one invisible horizontal baseline near the lower third of the image (the same in every frame); in airborne frames she floats above that baseline. Background: one perfectly flat solid pure magenta (#FF00FF) everywhere, with no floor, no ground line, no cast shadow, no gradient, no vignette, no texture, no border, no frame lines, no grid, no numbers, no text, no watermark. Do not use magenta, pink or purple anywhere on the character or effects.
```


---

Total: 1 folha mestra + 44 imagens.
