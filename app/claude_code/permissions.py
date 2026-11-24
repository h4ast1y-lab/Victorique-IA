"""
Ponte de permissões: o callback ``can_use_tool`` do Claude Code vira um pedido
na barra de autorização do app e espera a decisão do usuário.
"""
import asyncio
import json
import logging
from typing import Any, Callable, Dict, Optional, Set

from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

from app.config import settings
from app.security.path_guard import path_guard
from app.security.permissions import ActionCategory, security_manager

logger = logging.getLogger("claude_code.permissions")

# Tools that write to a file given in file_path / notebook_path.
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
TARGET_KEYS = ("file_path", "notebook_path", "command", "url", "query", "path", "pattern")
MAX_TARGET_CHARS = 200


# Friendly names for the authorization bar.
FRIENDLY_TOOLS = {
    "mcp__victorique__mover_arquivos": "mover arquivos (plano em lote)",
    "mcp__victorique__renomear": "renomear um item",
    "mcp__victorique__mandar_para_reserva": "mandar itens para a Reserva (_Quarentena)",
}


def describe_target(tool_name: str, input_data: Dict[str, Any]) -> str:
    """What the tool acts on, as shown in the authorization bar."""
    moves = input_data.get("moves")
    if isinstance(moves, list):
        return f"{len(moves)} item(ns) no plano"
    paths = input_data.get("paths")
    if isinstance(paths, list):
        return f"{len(paths)} item(ns) para a Reserva"
    for key in TARGET_KEYS:
        value = input_data.get(key)
        if value:
            return str(value)[:MAX_TARGET_CHARS]
    return json.dumps(input_data, ensure_ascii=False, default=str)[:MAX_TARGET_CHARS]


class PermissionBridge:
    """One per Claude Code turn; ``emit`` puts SSE payloads in the turn's queue."""

    def __init__(
        self,
        emit: Callable[[Dict[str, Any]], None],
        conversation_id: str,
        ttl: Optional[float] = None,
    ):
        self.emit = emit
        self.conversation_id = conversation_id
        self.ttl = float(ttl if ttl is not None else settings.authorization_ttl_seconds)
        self._pending: Set[str] = set()

    async def can_use_tool(self, tool_name: str, input_data: Dict[str, Any], context: Any):
        target = describe_target(tool_name, input_data)

        if tool_name in WRITE_TOOLS:
            path = input_data.get("file_path") or input_data.get("notebook_path")
            if path and path_guard.is_protected(str(path)):
                security_manager.log_action(
                    action_type=tool_name,
                    category=ActionCategory.REQUIRES_AUTH,
                    resource=target,
                    authorized=False,
                    details="Claude Code: caminho protegido; negado sem perguntar",
                )
                return PermissionResultDeny(
                    message=(
                        "Caminho protegido (código, banco ou backups do app). "
                        "Não é permitido alterá-lo."
                    )
                )
            if settings.turbo_mode:
                # Turbo = acceptEdits semantics. Done here instead of via
                # permission_mode="acceptEdits", which would bypass this callback
                # and with it the protected-path guard above.
                security_manager.log_action(
                    action_type=tool_name,
                    category=ActionCategory.REQUIRES_AUTH,
                    resource=target,
                    authorized=True,
                    details="Claude Code: aprovado automaticamente (modo turbo)",
                )
                return PermissionResultAllow(updated_input=input_data)

        friendly = FRIENDLY_TOOLS.get(tool_name)
        description = f"Victorique quer {friendly}." if friendly else f"Claude Code quer usar {tool_name}."
        action_id, future = security_manager.create_waiting_request(
            action_type=tool_name,
            resource=target,
            description=description,
            payload=input_data,
            context={"conversation_id": self.conversation_id},
        )
        self._pending.add(action_id)
        self.emit({
            "type": "authorization_required",
            "action_id": action_id,
            "tool_name": tool_name,
            "category": "claude_code",
            "resource": target,
            "description": description,
            "parameters": input_data,
        })

        try:
            approved = await asyncio.wait_for(asyncio.shield(future), self.ttl)
        except asyncio.TimeoutError:
            security_manager.cancel_action(action_id, "Claude Code: autorização expirou sem resposta")
            approved = False
        finally:
            self._pending.discard(action_id)

        if approved:
            return PermissionResultAllow(updated_input=input_data)
        return PermissionResultDeny(
            message=f"O usuário não autorizou {tool_name} em {target}. Não tente de novo sem pedir."
        )

    def cancel_pending(self) -> None:
        """Denies every request still waiting (the user stopped the turn)."""
        for action_id in list(self._pending):
            security_manager.cancel_action(action_id, "Claude Code: turno interrompido pelo usuário")
