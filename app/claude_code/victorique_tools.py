"""
Ferramentas MCP em processo: dão ao Claude Code acesso só de leitura às memórias
e aos documentos indexados da Victorique, respeitando o projeto da conversa.
"""
import logging
from typing import Any, Dict, Optional

from claude_agent_sdk import create_sdk_mcp_server, tool

from app.memory.memory_store import memory_store
from app.rag.vector_store import vector_store

logger = logging.getLogger("claude_code.victorique_tools")

SERVER_NAME = "victorique"
VICTORIQUE_TOOL_NAMES = [
    f"mcp__{SERVER_NAME}__buscar_memorias",
    f"mcp__{SERVER_NAME}__buscar_documentos",
]
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

    return create_sdk_mcp_server(name=SERVER_NAME, version="1.0.0", tools=[_memorias, _documentos])
