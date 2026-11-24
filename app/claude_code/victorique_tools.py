"""
Ferramentas MCP em processo: dão ao Claude Code acesso só de leitura às memórias
e aos documentos indexados da Victorique, respeitando o projeto da conversa, as
ferramentas de organização (mover, renomear, mandar para a Reserva) e as de
documentos de escritório (ler e editar Word, Excel, PowerPoint e PDF).

As de organização e as de edição ficam FORA de ``allowed_tools``: cada chamada
passa pelo ``can_use_tool`` e abre a barra de autorização (as de edição são
aprovadas sozinhas no modo turbo, porque o original sempre vai para a Reserva).
"""
import asyncio
import json
import logging
from typing import Any, Dict, Optional

from claude_agent_sdk import create_sdk_mcp_server, tool

from app.memory.memory_store import memory_store
from app.tools import file_tools, office, organizer
from app.rag.vector_store import vector_store

logger = logging.getLogger("claude_code.victorique_tools")

SERVER_NAME = "victorique"
VICTORIQUE_TOOL_NAMES = [
    f"mcp__{SERVER_NAME}__buscar_memorias",
    f"mcp__{SERVER_NAME}__buscar_documentos",
    f"mcp__{SERVER_NAME}__ler_documento",
]
# Asked in the authorization bar (auto-approved in turbo: originals go to the Reserva).
DOCUMENT_TOOL_NAMES = [
    f"mcp__{SERVER_NAME}__editar_word",
    f"mcp__{SERVER_NAME}__editar_planilha",
    f"mcp__{SERVER_NAME}__editar_pdf",
    f"mcp__{SERVER_NAME}__criar_documento",
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
READ_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Caminho completo do arquivo."},
        "start_page": {"type": "integer", "description": "Parte inicial (página, seção, planilha ou slide). Padrão 1."},
        "end_page": {"type": "integer", "description": "Parte final. Padrão: início + 2."},
        "query": {"type": "string", "description": "Opcional: buscar só os trechos com este termo."},
    },
    "required": ["path"],
}
OPS_PROPERTY = {
    "type": "array",
    "items": {"type": "object"},
    "description": "Lista de operações, aplicadas em ordem.",
}
OUTPUT_PROPERTY = {"type": "string", "description": "Opcional: salvar a versão editada em outro arquivo."}
EDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Caminho do arquivo a editar."},
        "operations": OPS_PROPERTY,
        "output_path": OUTPUT_PROPERTY,
    },
    "required": ["path", "operations"],
}
CREATE_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Caminho do arquivo novo; a extensão define o tipo."},
        "content": {"type": "string", "description": "Texto estilo Markdown (docx, pptx, md, txt)."},
        "title": {"type": "string", "description": "Título opcional."},
        "rows": {"type": "array", "items": {"type": "array"}, "description": "Linhas (xlsx, csv)."},
        "sheets": {"type": "object", "description": "Para .xlsx com várias planilhas: {nome: [[linhas]]}."},
        "overwrite": {"type": "boolean", "description": "Substituir um arquivo existente (o antigo vai para a Reserva)."},
    },
    "required": ["path"],
}
DOCUMENT_TOP_K = 4


def _content(text: str) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _failure(text: str) -> Dict[str, Any]:
    """An error result: the turn's trace shows it and the Biblioteca does not stage it."""
    return {"content": [{"type": "text", "text": text}], "is_error": True}


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
    except Exception as exc:  # DB error etc. (no Ollama -> keyword search, no error)
        logger.warning("buscar_documentos falhou: %s", exc)
        return _content(
            "Busca nos documentos indisponível agora (erro ao ler o índice). "
            "Diga isso ao usuário em vez de inventar o conteúdo."
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


async def ler_documento(args: Dict[str, Any]) -> Dict[str, Any]:
    kwargs = {k: args[k] for k in ("start_page", "end_page", "query") if args.get(k) not in (None, "")}
    try:
        result = await asyncio.to_thread(
            file_tools.read_file, str(args.get("path") or ""), 12000, **kwargs
        )
    except Exception as exc:
        return _failure(f"Não consegui ler o arquivo: {exc}")
    return _content(json.dumps(result, ensure_ascii=False, indent=1))


async def _edit_document(func, **kwargs) -> Dict[str, Any]:
    """Runs an office edit off the event loop (the backend records the scene on success)."""
    try:
        result = await asyncio.to_thread(func, **kwargs)
    except Exception as exc:
        return _failure(f"Nada foi alterado. Motivo: {exc}")
    return _content(json.dumps(result, ensure_ascii=False, indent=1))


def _edit_args(args: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "path": str(args.get("path") or ""),
        "operations": args.get("operations") or [],
        "output_path": args.get("output_path") or None,
    }


async def editar_word(args: Dict[str, Any]) -> Dict[str, Any]:
    return await _edit_document(office.edit_word, **_edit_args(args))


async def editar_planilha(args: Dict[str, Any]) -> Dict[str, Any]:
    return await _edit_document(office.edit_spreadsheet, **_edit_args(args))


async def editar_pdf(args: Dict[str, Any]) -> Dict[str, Any]:
    return await _edit_document(office.edit_pdf, **_edit_args(args))


async def criar_documento(args: Dict[str, Any]) -> Dict[str, Any]:
    kwargs = {
        "path": str(args.get("path") or ""),
        "content": str(args.get("content") or ""),
        "title": args.get("title") or None,
        "rows": args.get("rows") or None,
        "sheets": args.get("sheets") or None,
        "overwrite": bool(args.get("overwrite")),
    }
    return await _edit_document(office.create_document, **kwargs)


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

    @tool(
        "ler_documento",
        "Lê Word (.docx), Excel (.xlsx/.xls), PowerPoint (.pptx), CSV, PDF, EPUB e textos, "
        "em partes (páginas, seções, planilhas ou slides), ou busca um termo com 'query'. "
        "No Word, [¶n] numera os parágrafos; nas planilhas, colunas em letras e linhas numeradas. "
        "Use também para os anexos enviados no chat.",
        READ_SCHEMA,
    )
    async def _ler(args):
        return await ler_documento(args)

    @tool(
        "editar_word",
        "Edita um .docx preservando a formatação. Operações: {op:'replace', find, replace, count?}, "
        "{op:'append_paragraph', text, style?}, {op:'append_heading', text, level}, "
        "{op:'append_table', rows}, {op:'insert_paragraph', text, before|after: n}, "
        "{op:'set_paragraph', index: n, text}, {op:'delete_paragraph', index: n} (n = ¶ da leitura). "
        "O original vai para a Reserva; anexos do chat geram cópia em Documentos/Victorique.",
        EDIT_SCHEMA,
    )
    async def _word(args):
        return await editar_word(args)

    @tool(
        "editar_planilha",
        "Edita .xlsx/.xlsm/.csv (um .xls vira .xlsx). Operações: {op:'set_cells', sheet?, "
        "cells:{'A1': valor ou '=FÓRMULA'}}, {op:'append_rows', sheet?, rows}, "
        "{op:'insert_rows', sheet?, at, rows}, {op:'delete_rows', sheet?, start, count}, "
        "{op:'add_sheet', name, rows?}, {op:'rename_sheet', sheet, new_name}, {op:'delete_sheet', sheet}.",
        EDIT_SCHEMA,
    )
    async def _planilha(args):
        return await editar_planilha(args)

    @tool(
        "editar_pdf",
        "Edita páginas de PDF: {op:'keep_pages', pages:'1-3,5'}, {op:'delete_pages', pages}, "
        "{op:'rotate', pages?, degrees}, {op:'merge', paths}, {op:'metadata', title?, author?}. "
        "O texto do PDF não é editável: para reescrever, crie um .docx com criar_documento.",
        EDIT_SCHEMA,
    )
    async def _pdf(args):
        return await editar_pdf(args)

    @tool(
        "criar_documento",
        "Cria .docx ou .pptx a partir de texto estilo Markdown (# títulos, - listas, tabelas "
        "| a | b |; no .pptx cada # é um slide), .xlsx/.csv a partir de 'rows' ou 'sheets', ou .md/.txt.",
        CREATE_SCHEMA,
    )
    async def _criar(args):
        return await criar_documento(args)

    return create_sdk_mcp_server(
        name=SERVER_NAME, version="1.0.0",
        tools=[_memorias, _documentos, _mover, _renomear, _reserva,
               _ler, _word, _planilha, _pdf, _criar],
    )
