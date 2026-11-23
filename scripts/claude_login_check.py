"""
Verifica se o Claude Code (empacotado no claude-agent-sdk) consegue
responder com o login desta máquina. Consome um pouco da cota.

Uso:  .venv\\Scripts\\python.exe scripts\\claude_login_check.py
"""
import asyncio
import sys

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKError,
    ResultMessage,
    TextBlock,
    query,
)


async def main() -> int:
    options = ClaudeAgentOptions(setting_sources=[], max_turns=1, allowed_tools=[])
    text = []
    result = None
    try:
        async for message in query(prompt="Responda apenas: OK", options=options):
            if isinstance(message, AssistantMessage):
                text.extend(b.text for b in message.content if isinstance(b, TextBlock))
            elif isinstance(message, ResultMessage):
                result = message
    except ClaudeSDKError as exc:
        # The SDK raises ResultError for error results (e.g. expired login).
        print("ERRO:", exc)
        return 1
    print("texto:", "".join(text).strip())
    if result is None:
        print("sem ResultMessage")
        return 1
    print("session_id:", result.session_id)
    print("is_error:", result.is_error, "| subtype:", result.subtype)
    print("result:", (result.result or "")[:300])
    print("total_cost_usd:", result.total_cost_usd)
    return 1 if result.is_error else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
