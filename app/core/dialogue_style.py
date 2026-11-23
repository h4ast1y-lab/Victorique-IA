"""
Detects repeated delivery in the assistant's recent replies.

A character prompt alone does not stop a model from copying its own earlier
openings: the conversation history keeps showing them. This module counts
repeated openings, italic stage actions and whole sentences in the last
replies and, when it finds any, adds one neutral line to the system prompt.

The repeated text itself is never quoted back to the model: quoting an
unwanted phrase primes it. Nothing is censored, cut or regenerated.
(Idea studied in CapriCore's dialogue-style module; this code is our own.)
"""

import re
from collections import Counter
from typing import Any, Dict, Iterable, List

RECENT_REPLIES = 12
MAX_REPLY_CHARS = 4096
OPENING_WORDS = 3

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_CODE_BLOCK = re.compile(r"```.*?(?:```|$)", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_ACTION = re.compile(r"(?<![*\w])\*([^*\n]{3,120})\*(?![*\w])")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")
# Paths, URLs, e-mails and structured data are factual content, not style.
_FACTUAL = re.compile(r"[:\\/@<>\[\]{}=|]")


def _words(text: str) -> List[str]:
    return _WORD.findall(text.lower())


def _prose(text: str) -> str:
    text = _CODE_BLOCK.sub(" ", text[:MAX_REPLY_CHARS])
    return _INLINE_CODE.sub(" ", text)


def _recent_replies(messages: Iterable[Dict[str, Any]]) -> List[str]:
    replies = [
        str(m.get("content") or "")
        for m in messages
        if m.get("role") == "assistant" and str(m.get("content") or "").strip()
    ]
    return replies[-RECENT_REPLIES:]


def repeated_phrasing(messages: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Counts repeats among the last replies. Returns only counts and phrases
    for tests/diagnostics; the prompt never receives the phrases."""
    replies = _recent_replies(messages)
    openings: Counter = Counter()
    actions: Counter = Counter()
    sentences: Counter = Counter()
    for reply in replies:
        prose = _prose(reply)
        first = _words(prose[:200])
        if len(first) >= OPENING_WORDS:
            openings[" ".join(first[:OPENING_WORDS])] += 1
        # Each distinct phrase counts once per reply.
        actions.update({" ".join(_words(a)) for a in _ACTION.findall(prose) if _words(a)})
        unique = set()
        for sentence in _SENTENCE_SPLIT.split(prose):
            if _FACTUAL.search(sentence):
                continue
            tokens = _words(sentence)
            if 6 <= len(tokens) <= 40:
                unique.add(" ".join(tokens))
        sentences.update(unique)

    def repeated(counter: Counter, limit: int) -> List[Dict[str, Any]]:
        return [
            {"text": text, "count": count}
            for text, count in counter.most_common()
            if count >= 2
        ][:limit]

    return {
        "replies": len(replies),
        "openings": repeated(openings, 3),
        "actions": repeated(actions, 3),
        "sentences": repeated(sentences, 2),
    }


def style_note(messages: Iterable[Dict[str, Any]]) -> str:
    """One system-prompt line when repetition was detected, else ''."""
    found = repeated_phrasing(messages)
    if not (found["openings"] or found["actions"] or found["sentences"]):
        return ""
    kinds = []
    if found["openings"]:
        kinds.append("aberturas")
    if found["actions"]:
        kinds.append("ações em itálico")
    if found["sentences"]:
        kinds.append("frases inteiras")
    return (
        "OBSERVAÇÃO DE ESTILO: nas suas últimas "
        f"{found['replies']} respostas houve repetição de {', '.join(kinds)}. "
        "Na próxima, comece pelo que a última mensagem do usuário pede, com palavras e imagens "
        "novas; se for o caso, sem ação em itálico. Mantenha exatos os fatos, nomes, código e "
        "citações necessários."
    )
