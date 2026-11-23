"""
Ferramentas MCP em processo: dão ao Claude Code acesso só de leitura às memórias
e aos documentos indexados da Victorique, respeitando o projeto da conversa, e as
ferramentas de organização (mover, renomear, mandar para a Reserva).

As de organização ficam FORA de ``allowed_tools``: cada chamada passa pelo
``can_use_tool`` e abre a barra de autorização com o plano origem → destino.
"""
import asyncio
import json
import logging
from typing import Any, Dict, Optional

from claude_agent_sdk import create_sdk_mcp_server, tool

from app.memory.memory_store import memory_store
from app.tools import organizer
from app.rag.vector_store import vector_store

logger = logging.getLogger("claude_code.victorique_tools")

SERVER_NAME = "victorique"
VICTORIQUE_TOOL_NAMES = [
    f"mcp__{SERVER_NAME}__buscar_memorias",
    f"mcp__{SERVER_NAME}__buscar_documentos",
]
# Never auto-approved: the user confirms every call in the authorization bar.
ORGANIZER_TOOL_NAMES = [
    f"mcp__{SERVER_NAME}__mover_arquivos",
    f"mcp__{SERVER_NAME}__renomear",
    f"mcp__{SERVER_NAME}__mandar_para_reserva",
]
MOVE_SCHEMA = {
    "type": "object",
    "properties": {
        "moves": {
            "type": "array",
            "description": "Plano: lista de {origem, destino}, caminhos completos.",
            "items": {
                "type": "object",
                "properties": {"origem": {"type": "string"}, "destino": {"type": "string"}},
                "required": ["origem", "destino"],
            },
        },
        "descricao": {"type": "string", "description": "Resumo do plano."},
    },
    "required": ["moves"],
}
RENAME_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Caminho atual."},
        "new_name": {"type": "string", "description": "Novo nome, sem pastas."},
    },
    "required": ["path", "new_name"],
}
RESERVE_SCHEMA = {
    "type": "object",
    "properties": {
        "paths": {"type": "array", "items": {"type": "string"}, "description": "Caminhos a descartar."},
        "descricao": {"type": "string", "description": "Motivo do descarte."},
    },
    "required": ["paths"],
}
QUERY_SCHEMA = {
    "type": "object",
    "properties": {"consulta": {"type": "string", "description": "O que procurar."}},
    "required": ["consulta"],
}
DOCUMENT_TOP_K = 4


def _content(text: str) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _query(args: Dict[str, Any]) -> str:
    return str(args.get("consulta") or "").strip()


async def buscar_memorias(args: Dict[str, Any], project_id: Optional[str]) -> Dict[str, Any]:
    context = memory_store.get_context_for_prompt(project_id=project_id, user_query=_query(args))
    return _content(context or "Nenhuma memória salva sobre isso.")


async def buscar_documentos(args: Dict[str, Any], project_id: Optional[str]) -> Dict[str, Any]:
    query = _query(args)
    if not query:
        return _content("Informe o que procurar nos documentos.")
    try:
        chunks = await vector_store.search(query=query, project_id=project_id, top_k=DOCUMENT_TOP_K)
    except Exception as exc:  # Ollama embeddings offline, DB error, etc.
        logger.warning("buscar_documentos falhou: %s", exc)
        return _content(
            "Busca nos documentos indisponível agora (o Ollama, que gera os embeddings, "
            "não respondeu). Diga isso ao usuário em vez de inventar o conteúdo."
        )
    if not chunks:
        return _content("Nenhum trecho relevante encontrado nos documentos indexados.")
    parts = [
        f"--- {ch['document_title']}, página {ch['page']}:\n{ch['content']}" for ch in chunks
    ]
    parts.append("Cite documento e página ao usar estes trechos; não invente o que não está aqui.")
    return _content("\n".join(parts))


async def _organize(func, *args) -> Dict[str, Any]:
    """Runs an organizer operation off the event loop; errors go back as text."""
    try:
        result = await asyncio.to_thread(func, *args)
    except Exception as exc:
        return _content(f"Nada foi alterado. Motivo: {exc}")
    return _content(json.dumps(result, ensure_ascii=False, indent=1))


async def mover_arquivos(args: Dict[str, Any]) -> Dict[str, Any]:
    return await _organize(organizer.move_files, args.get("moves") or [], str(args.get("descricao") or ""))


async def renomear(args: Dict[str, Any]) -> Dict[str, Any]:
    return await _organize(organizer.rename_file, str(args.get("path") or ""), str(args.get("new_name") or ""))


async def mandar_para_reserva(args: Dict[str, Any]) -> Dict[str, Any]:
    return await _organize(organizer.send_to_reserve, args.get("paths") or [], str(args.get("descricao") or ""))


def create_victorique_server(project_id: Optional[str]):
    """One server per turn, bound to the conversation's project."""

    @tool(
        "buscar_memorias",
        "Lê as memórias que o usuário autorizou (preferências, decisões, fatos).",
        QUERY_SCHEMA,
    )
    async def _memorias(args):
        return await buscar_memorias(args, project_id)

    @tool(
        "buscar_documentos",
        "Busca trechos nos documentos que o usuário indexou na Victorique (PDFs, textos).",
        QUERY_SCHEMA,
    )
    async def _documentos(args):
        return await buscar_documentos(args, project_id)

    @tool(
        "mover_arquivos",
        "Move arquivos/pastas em lote segundo um plano origem → destino (caminhos completos). "
        "O usuário aprova o plano inteiro antes; destinos existentes nunca são sobrescritos; "
        "tudo vai para o histórico e pode ser desfeito.",
        MOVE_SCHEMA,
    )
    async def _mover(args):
        return await mover_arquivos(args)

    @tool("renomear", "Renomeia um arquivo ou pasta na mesma pasta, sem sobrescrever.", RENAME_SCHEMA)
    async def _renomear(args):
        return await renomear(args)

    @tool(
        "mandar_para_reserva",
        "Descarta itens movendo-os para a Reserva (_Quarentena) da pasta autorizada. Nunca apaga.",
        RESERVE_SCHEMA,
    )
    async def _reserva(args):
        return await mandar_para_reserva(args)

    return create_sdk_mcp_server(
        name=SERVER_NAME, version="1.0.0",
        tools=[_memorias, _documentos, _mover, _renomear, _reserva],
    )
