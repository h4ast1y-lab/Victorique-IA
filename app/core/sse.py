"""Server-sent events shared by the local engine and the Claude Code backend."""
import json
from typing import Any, Dict

CANCELLED_MARKER = "\n\n_[Geração interrompida pelo usuário.]_"
NO_TEXT_FALLBACK = "_(O modelo não retornou texto nesta resposta.)_"


def sse_event(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncado; {len(text)} caracteres no total]"
