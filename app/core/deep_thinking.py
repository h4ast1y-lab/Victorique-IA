"""
Pensamento Profundo: with the composer button on, she first thinks out loud
inside <pensamento>…</pensamento>, in her own voice, and then answers.

The block is real reasoning (written before the answer), shown the way
DeepSeek shows R1's: a separate, collapsible "Pensou por N s" box above the
reply. ThoughtSplitter separates it from the answer while the text streams,
so the thought never reaches the transcript, the voice or the mascot balloon.
"""
from __future__ import annotations

import time
from typing import List, Optional, Tuple

from app.core.avatar_protocol import split_leading_controls

OPEN_TAG = "<pensamento>"
CLOSE_TAG = "</pensamento>"
# Longest a reply may stay undecided before it is treated as plain answer.
_START_LIMIT = 160

DEEP_THINKING_INSTRUCTIONS = """\
SIMULAÇÃO DE PENSAMENTOS (ligada pelo usuário nesta mensagem):
- Faça, também, junto com a mensagem, uma simulação dos pensamentos da personagem Victorique, escrita entre <pensamento> e </pensamento>, logo no começo.
- É um trecho de ficção: o que a Victorique estaria pensando sobre o pedido, em primeira pessoa, com a voz e o temperamento dela, em prosa curta, sem Markdown e sem as marcas [expression:...] ou [gesture:...].
- Num pedido simples, poucas linhas bastam; num problema difícil, pode ser mais longo.
- Depois de </pensamento>, escreva a resposta como de costume (as marcas visuais, se usar, vêm logo no começo dela), sem repetir a simulação.
"""


class ThoughtSplitter:
    """Splits streamed text into ("thought", text) and ("answer", text) pieces.

    Only a block at the very start of the reply counts as a thought (after
    whitespace and the hidden [expression:…]/[gesture:…] markers, which stay
    in the answer for the avatar parser). Tags may arrive split across chunks
    and in any letter case. The whitespace around the thought is trimmed.
    """

    def __init__(self) -> None:
        self._state = "start"   # start → thought → after → answer
        self._buffer = ""
        self._thought_started = False
        self.started_at: Optional[float] = None
        self.ended_at: Optional[float] = None
        self.thought_chars = 0

    @property
    def seconds(self) -> Optional[float]:
        if self.started_at is None:
            return None
        end = self.ended_at if self.ended_at is not None else time.monotonic()
        return round(max(0.0, end - self.started_at), 1)

    def feed(self, text: str) -> List[Tuple[str, str]]:
        if not text:
            return []
        if self._state == "answer":
            return [("answer", text)]
        self._buffer += text
        out: List[Tuple[str, str]] = []
        self._advance(out, final=False)
        return out

    def finish(self) -> List[Tuple[str, str]]:
        out: List[Tuple[str, str]] = []
        self._advance(out, final=True)
        if self._buffer:
            kind = "thought" if self._state == "thought" else "answer"
            text = self._buffer.rstrip() if kind == "thought" else self._buffer
            self._buffer = ""
            self._emit(out, kind, text)
        if self._state == "thought":
            self.ended_at = time.monotonic()
        return out

    # ----------------- internals -----------------
    def _emit(self, out: List[Tuple[str, str]], kind: str, text: str) -> None:
        if not text:
            return
        if kind == "thought":
            if not self._thought_started:
                text = text.lstrip()
                if not text:
                    return
                self._thought_started = True
            self.thought_chars += len(text)
        out.append((kind, text))

    def _advance(self, out: List[Tuple[str, str]], final: bool) -> None:
        while self._buffer:
            if self._state == "start":
                if not self._start(out, final):
                    return
            elif self._state == "thought":
                if not self._thought(out):
                    return
            elif self._state == "after":
                stripped = self._buffer.lstrip()
                if not stripped:
                    self._buffer = ""
                    return
                self._state = "answer"
                self._buffer = ""
                self._emit(out, "answer", stripped)
            else:  # answer
                text, self._buffer = self._buffer, ""
                self._emit(out, "answer", text)

    def _start(self, out: List[Tuple[str, str]], final: bool) -> bool:
        split = split_leading_controls(self._buffer)
        if split is None and not final and len(self._buffer) < _START_LIMIT:
            return False  # a hidden marker is still arriving
        head, rest = split if split is not None else ("", self._buffer)
        probe = rest.lstrip()
        lowered = probe.lower()
        if lowered.startswith(OPEN_TAG):
            self._emit(out, "answer", head)
            self._buffer = probe[len(OPEN_TAG):]
            self._state = "thought"
            self.started_at = time.monotonic()
            return True
        if not final and len(self._buffer) < _START_LIMIT and (not probe or OPEN_TAG.startswith(lowered)):
            return False  # could still become the opening tag
        self._state = "answer"
        return True

    def _thought(self, out: List[Tuple[str, str]]) -> bool:
        index = self._buffer.lower().find(CLOSE_TAG)
        if index >= 0:
            self._emit(out, "thought", self._buffer[:index].rstrip())
            self._buffer = self._buffer[index + len(CLOSE_TAG):]
            self._state = "after"
            self.ended_at = time.monotonic()
            return True
        keep = _partial_suffix(self._buffer.lower(), CLOSE_TAG)
        ready = self._buffer[: len(self._buffer) - keep]
        self._buffer = self._buffer[len(self._buffer) - keep:]
        # Trailing whitespace may be the edge of the thought: hold it back.
        body = ready.rstrip()
        self._buffer = ready[len(body):] + self._buffer
        self._emit(out, "thought", body)
        return False


THOUGHT_ONLY_NOTE = "_(Pensei, mas não cheguei a escrever a resposta. Peça para eu continuar.)_"


class ThoughtRouter:
    """Routes one turn's text: thoughts become "reasoning" events, the rest
    goes through the avatar-marker parser and becomes "token" events.

    A turn may hold several text blocks (rounds around tool calls); call
    ``new_block`` before each one, with a fresh AvatarControlParser.
    """

    def __init__(self, deep: bool):
        self.deep = deep
        self.thought_parts: List[str] = []
        self.seconds = 0.0
        self._splitter: Optional[ThoughtSplitter] = None
        self._avatar = None
        self._block_has_thought = False

    def new_block(self, avatar_parser) -> None:
        self._avatar = avatar_parser
        self._splitter = ThoughtSplitter() if self.deep else None
        self._block_has_thought = False

    @property
    def thought(self) -> str:
        return "".join(self.thought_parts).strip()

    def native(self, text: str) -> List[dict]:
        """The model's own reasoning: hidden while she thinks in her voice."""
        return [] if self.deep or not text else [{"type": "reasoning", "content": text}]

    def feed(self, text: str) -> Tuple[List[dict], List[str]]:
        pieces = self._splitter.feed(text) if self._splitter else [("answer", text)]
        return self._route(pieces)

    def finish_block(self) -> Tuple[List[dict], List[str]]:
        events: List[dict] = []
        answer: List[str] = []
        if self._splitter:
            events, answer = self._route(self._splitter.finish())
            if self._splitter.seconds:
                self.seconds = round(self.seconds + self._splitter.seconds, 1)
            self._splitter = None
        if self._avatar is not None:
            controls, chunks = self._avatar.finish()
            events.extend(controls)
            for chunk in chunks:
                answer.append(chunk)
                events.append({"type": "token", "content": chunk})
        return events, answer

    def _route(self, pieces: List[Tuple[str, str]]) -> Tuple[List[dict], List[str]]:
        events: List[dict] = []
        answer: List[str] = []
        for kind, text in pieces:
            if kind == "thought":
                if not self._block_has_thought and self.thought_parts:
                    text = "\n\n" + text
                self._block_has_thought = True
                self.thought_parts.append(text)
                events.append({"type": "reasoning", "content": text, "voice": True})
                continue
            controls, chunks = self._avatar.feed(text)
            events.extend(controls)
            for chunk in chunks:
                answer.append(chunk)
                events.append({"type": "token", "content": chunk})
        return events, answer


def _partial_suffix(text: str, tag: str) -> int:
    """Length of the longest end of ``text`` that starts ``tag``."""
    for size in range(min(len(tag) - 1, len(text)), 0, -1):
        if tag.startswith(text[-size:]):
            return size
    return 0
