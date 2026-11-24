/*
 * Caixa de pensamento no estilo do DeepSeek ("Pensando…" com o cachimbo,
 * depois "Pensou por N s", recolhível) e o cachimbo animado.
 * Compartilhado pela janela grande (app.js) e pela conversa rápida (mini.js).
 */
const PIPE_SVG = `<svg class="pipe" viewBox="0 0 48 48" aria-hidden="true">
  <path class="pipe-smoke s1" d="M31 21c-3-3 3-5 0-8s3-5 0-8"/>
  <path class="pipe-smoke s2" d="M35 22c-2-3 2-4 0-7s2-4 0-6"/>
  <path class="pipe-smoke s3" d="M27 22c-2-2 2-4 0-6s2-4 0-5"/>
  <path class="pipe-stem" d="M3 29c9 0 15 1 21 3"/>
  <path class="pipe-bowl" d="M23 24h14v8a7 7 0 0 1-14 0z"/></svg>`;

function thoughtIcon(name) {
  return `<svg class="ic ic-sm"><use href="#i-${name}"/></svg>`;
}

function thoughtEscape(text) {
  return window.escapeHtml ? window.escapeHtml(text) : String(text || '');
}

function thoughtLabel(seconds) {
  const s = Number(seconds);
  if (!Number.isFinite(s) || s <= 0) return 'Pensou por alguns segundos';
  if (s < 1) return 'Pensou por menos de 1 s';
  if (s < 60) return `Pensou por ${Math.round(s)} s`;
  const min = Math.floor(s / 60), rest = Math.round(s % 60);
  return `Pensou por ${min} min${rest ? ` ${rest} s` : ''}`;
}

// voice=true: o pensamento dela (Pensamento profundo), sempre visível.
// voice=false: o raciocínio interno do modelo, que a preferência pode ocultar.
function createThoughtBox(voice, { live = false, text = '', seconds = null } = {}) {
  const details = document.createElement('details');
  details.className = voice ? 'reasoning-box thought-box' : 'reasoning-box';
  const summary = document.createElement('summary');
  const body = document.createElement('div');
  body.className = 'reasoning-body';
  body.textContent = text;
  details.append(summary, body);
  let startedAt = null;
  let spent = 0;  // segundos já pensados em trechos anteriores

  const box = {
    el: details,
    append(chunk) {
      if (!chunk) return;
      if (voice && !details.classList.contains('live')) box.setLive(true);
      const stick = body.scrollTop + body.clientHeight >= body.scrollHeight - 24;
      body.textContent += chunk;
      if (stick) body.scrollTop = body.scrollHeight;
    },
    setLive(on) {
      if (!voice) return;
      if (on) {
        startedAt = performance.now();
        details.classList.add('live');
        details.open = true;
        summary.innerHTML = `${PIPE_SVG}<span>Pensando…</span>`;
      } else if (details.classList.contains('live')) {
        spent += (performance.now() - startedAt) / 1000;
        details.classList.remove('live');
        box.setLabel(spent);
      }
    },
    setLabel(secs) {
      summary.innerHTML = voice
        ? `${thoughtIcon('bulb')}<span>${thoughtEscape(thoughtLabel(secs))}</span>`
        : `${thoughtIcon('sparkle')}<span>Raciocínio</span>`;
    },
    finish(secs) {
      box.setLive(false);
      if (voice) {
        box.setLabel(secs ?? spent);
        details.open = false;
      }
    },
  };
  if (live && voice) box.setLive(true);
  else box.setLabel(seconds);
  return box;
}
