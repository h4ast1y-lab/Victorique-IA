"""
The last messages of a conversation as plain text.

Claude Code and Codex keep their own sessions. Whenever the app has to start
a new one on a conversation that already has messages (the first turn in that
mode after chatting in another, or a session that could not be resumed), this
summary goes along so she does not lose the thread of the conversation.
"""
from typing import Any, Dict, List

from app.core import attachments as chat_attachments
from app.core.sse import truncate

HISTORY_MESSAGES = 12
HISTORY_CHARS = 1200


def recent_transcript(
    history: List[Dict[str, Any]],
    user_message: str,
    max_messages: int = HISTORY_MESSAGES,
    max_chars: int = HISTORY_CHARS,
) -> str:
    """Messages before ``user_message`` (already saved by the caller), oldest first."""
    prior = list(history)
    if prior and prior[-1].get("role") == "user" and prior[-1].get("content") == user_message:
        prior = prior[:-1]
    lines = []
    for message in prior[-max_messages:]:
        who = "Usuário" if message.get("role") == "user" else "Você"
        text = truncate(str(message.get("content") or ""), max_chars)
        if message.get("attachments"):
            text = (text + " " + chat_attachments.history_note(message["attachments"])).strip()
        lines.append(f"{who}: {text}")
    return "\n\n".join(lines)


def wrap_with_transcript(transcript: str, user_message: str) -> str:
    """The user's message preceded by the conversation so far (when there is one)."""
    if not transcript:
        return user_message
    return (
        f"<conversa_ate_aqui>\n{transcript}\n</conversa_ate_aqui>\n\n"
        f"MENSAGEM DO USUÁRIO:\n{user_message}"
    )
