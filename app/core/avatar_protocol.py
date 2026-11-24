"""Safe, incremental controls for Victorique's procedural figure.

The language model may select only registered expression and gesture IDs. The
markers are removed before text reaches the transcript or TTS and are emitted
to the UI as structured SSE events. They never name files or contain code.

Adapted from Victorique-IA-2 (github.com/Nyzius/Victorique-IA-2), the sibling
project built on this same code base; here the figure is the desktop mascot.
"""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Dict, List, Tuple


EXPRESSIONS = (
    "neutral",
    "skeptical",
    "annoyed",
    "concerned",
    "happy",
    "surprised",
    "embarrassed",
    "focused",
    "sleepy",
    "deduction",
    "confused",
)

GESTURES = (
    "page-turn",
    "pipe",
    "deduction",
    "tea",
    "hair-adjust",
)

STATES = (
    ("acordada", "Acordada"),
    ("dormindo", "Cochilando entre os livros"),
    ("ouvindo", "Ouvindo"),
    ("pensando", "Pensando"),
    ("falando", "Falando"),
    ("erro", "Algo deu errado"),
)

GESTURE_DURATIONS = {
    "page-turn": 1700,
    "pipe": 3200,
    "deduction": 2100,
    "tea": 2600,
    "hair-adjust": 1900,
}

_MANIFEST = {
    "schemaVersion": 1,
    "character": "Victorique",
    "renderer": "desktop-mascot",
    "media": False,
    "defaultState": "acordada",
    "defaultExpression": "neutral",
    "states": [{"id": state, "label": label} for state, label in STATES],
    "expressions": list(EXPRESSIONS),
    "gestures": [
        {"id": gesture, "durationMs": GESTURE_DURATIONS[gesture]}
        for gesture in GESTURES
    ],
}

_CONTROL = re.compile(r"^\[(expression|gesture):([a-z][a-z0-9-]{0,31})\]")
_STARTS = ("[expression:", "[gesture:")
_MAX_CONTROL = 64


AVATAR_INSTRUCTIONS = f"""\
CONTROLE VISUAL DA VICTORIQUE:
- Na resposta final ao usuário, escolha uma expressão visual e coloque exatamente um marcador oculto na primeira linha: [expression:ID].
- IDs de expressão permitidos: {', '.join(EXPRESSIONS)}.
- Opcionalmente, na linha seguinte, escolha um gesto breve com [gesture:ID].
- IDs de gesto permitidos: {', '.join(GESTURES)}.
- Depois dos marcadores, escreva a resposta normalmente. Não explique, repita nem coloque os marcadores em Markdown.
- Use os controles somente na resposta final. Antes de chamar ferramentas, não emita marcador nem preâmbulo.
- A expressão deve acompanhar o sentido real: concerned para preocupação, annoyed para irritação, happy para satisfação, embarrassed para elogio, focused para trabalho técnico, deduction ao concluir um raciocínio, confused quando o pedido for ambíguo ou algo não fizer sentido e neutral quando nenhuma outra se aplicar.
- Gestos são raros. Use deduction apenas para uma conclusão importante, pipe ao refletir, page-turn ao consultar informação, tea em uma pausa tranquila e hair-adjust para leve constrangimento. A interface cuida sozinha de fala, escuta, sono e piscadas.
Exemplo:
[expression:skeptical]
[gesture:page-turn]
Ora, os fragmentos apontam para uma conclusão evidente."""


_LEADING_CONTROLS = re.compile(r"^\s*(?:\[(?:expression|gesture):[a-z0-9-]{0,32}\][ \t]*\r?\n?\s*)+")


def split_leading_controls(text: str) -> Tuple[str, str] | None:
    """Splits ``text`` into (leading markers, rest).

    Returns None while the text could still be an unfinished marker, so a
    caller that buffers output (to spot a JSON tool call) knows to wait.
    """
    match = _LEADING_CONTROLS.match(text)
    head = text[: match.end()] if match else ""
    rest = text[len(head):]
    probe = rest.lstrip()
    if probe and "]" not in probe and any(
        start.startswith(probe) or probe.startswith(start) for start in _STARTS
    ):
        return None
    return head, rest


def avatar_manifest() -> Dict[str, object]:
    """Public, media-free contract shared by the backend and renderer."""
    return deepcopy(_MANIFEST)


class AvatarControlParser:
    """Remove up to one leading expression and gesture across arbitrary chunks."""

    def __init__(self) -> None:
        self._buffer = ""
        self._accepting = True
        self._seen: set[str] = set()
        self._after_control = False
        self._discarding_control = False

    def feed(self, text: str) -> Tuple[List[Dict[str, str]], List[str]]:
        if not text:
            return [], []
        if not self._accepting:
            return [], [text]

        if self._discarding_control:
            end_positions = [position for position in (text.find("]"), text.find("\n")) if position >= 0]
            if not end_positions:
                return [], []
            text = text[min(end_positions) + 1 :]
            self._discarding_control = False
            self._after_control = True
            if not text:
                return [], []

        self._buffer += text
        controls: List[Dict[str, str]] = []
        visible: List[str] = []

        while self._accepting and self._buffer:
            if self._after_control:
                if self._buffer == "\r":
                    break
                if self._buffer.startswith("\r\n"):
                    self._buffer = self._buffer[2:]
                elif self._buffer.startswith("\n"):
                    self._buffer = self._buffer[1:]
                self._after_control = False
                if not self._buffer:
                    break
            match = _CONTROL.match(self._buffer)
            if match:
                end = match.end()
                if end > _MAX_CONTROL:
                    self._buffer = self._buffer[end:]
                    self._after_control = True
                    break
                kind, value = match.groups()
                allowed = EXPRESSIONS if kind == "expression" else GESTURES
                self._buffer = self._buffer[end:]
                self._after_control = True
                if kind in self._seen or value not in allowed:
                    continue
                self._seen.add(kind)
                controls.append({"type": "avatar", kind: value})
                continue

            if len(self._buffer) > _MAX_CONTROL:
                if any(self._buffer.startswith(start) for start in _STARTS):
                    self._buffer = ""
                    self._discarding_control = True
                    break
                self._release(visible)
                break
            if "]" not in self._buffer and any(
                start.startswith(self._buffer) or self._buffer.startswith(start)
                for start in _STARTS
            ):
                break
            if any(self._buffer.startswith(start) for start in _STARTS) and "]" in self._buffer:
                self._buffer = self._buffer[self._buffer.index("]") + 1 :]
                self._after_control = True
                continue
            # A complete but malformed reserved control is ordinary visible
            # text unless it uses one of the protocol's reserved prefixes.
            self._release(visible)

        return controls, visible

    def finish(self) -> Tuple[List[Dict[str, str]], List[str]]:
        if not self._buffer:
            return [], []
        # Do not leak a truncated reserved marker into the answer. Anything
        # else is ordinary prose and must be preserved.
        if self._accepting and "]" not in self._buffer and any(
            start.startswith(self._buffer) or self._buffer.startswith(start)
            for start in _STARTS
        ):
            self._buffer = ""
            return [], []
        visible = [self._buffer]
        self._buffer = ""
        self._accepting = False
        return [], visible

    def _release(self, visible: List[str]) -> None:
        if self._buffer:
            visible.append(self._buffer)
        self._buffer = ""
        self._accepting = False
