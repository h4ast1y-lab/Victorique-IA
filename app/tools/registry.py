import inspect
from typing import Dict, Any, Callable, List, Optional

from app.config import settings
from app.security.permissions import ActionCategory, security_manager
from app.tools.file_tools import (
    list_directory, read_file, search_files, write_file, create_directory, delete_file
)
from app.tools.organizer import move_files, rename_file
from app.tools.system_tools import calculate, get_system_info, get_system_metrics
from app.tools.web_search import search_web, read_url


def _schema(properties: Dict[str, Any], required: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


class ToolDefinition:
    def __init__(
        self,
        name: str,
        description: str,
        category: ActionCategory,
        func: Callable,
        risk_description: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        always_confirm: bool = False,
    ):
        self.name = name
        self.description = description
        self.category = category
        self.func = func
        self.risk_description = risk_description
        self.parameters = parameters or _schema({})
        # Destructive tools ask for approval even when turbo mode is on.
        self.always_confirm = always_confirm

    @property
    def is_protected(self) -> bool:
        """Category-based: true for tools that normally need user approval."""
        return self.category in (ActionCategory.REQUIRES_AUTH, ActionCategory.EXTERNAL)

    @property
    def needs_approval(self) -> bool:
        if self.always_confirm:
            return True
        if getattr(settings, "turbo_mode", False):
            # Turbo (opt-in): escrita e internet rodam sem interromper o fluxo.
            return False
        return self.is_protected


class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, ToolDefinition] = {}
        self._register_default_tools()

    def register(self, tool: ToolDefinition):
        self.tools[tool.name] = tool

    def _register_default_tools(self):
        # Category 1: Free (acesso livre para leitura e exploração no computador)
        self.register(ToolDefinition(
            name="list_directory",
            description="Lista arquivos e pastas em qualquer diretório ou disco do computador (ex.: 'C:\\', 'D:\\', 'C:\\Users\\Usuário\\Downloads').",
            category=ActionCategory.FREE,
            func=list_directory,
            parameters=_schema({
                "path": {
                    "type": "string",
                    "description": "Caminho do diretório a listar (ex.: 'C:\\', 'D:\\Livros', 'C:\\Users\\Usuário\\Documents'). Use '.' para a pasta de dados.",
                },
            }),
        ))
        self.register(ToolDefinition(
            name="read_file",
            description="Lê o conteúdo em texto de qualquer arquivo no computador.",
            category=ActionCategory.FREE,
            func=read_file,
            parameters=_schema({
                "path": {"type": "string", "description": "Caminho completo do arquivo a ler (ex.: 'C:\\caminho\\arquivo.txt')."},
                "max_chars": {
                    "type": "integer",
                    "description": "Máximo de caracteres retornados (padrão 15000).",
                },
            }, required=["path"]),
        ))
        self.register(ToolDefinition(
            name="search_files",
            description="Busca arquivos por nome ou padrão glob em qualquer pasta ou disco do computador.",
            category=ActionCategory.FREE,
            func=search_files,
            parameters=_schema({
                "path": {"type": "string", "description": "Diretório base da busca (ex.: 'C:\\Users\\Usuário', 'D:\\')."},
                "pattern": {
                    "type": "string",
                    "description": "Padrão glob, por exemplo '*.txt', '*.pdf', '*.py'.",
                },
            }),
        ))
        self.register(ToolDefinition(
            name="calculate",
            description="Executa cálculos matemáticos seguros (+, -, *, /, //, %, **).",
            category=ActionCategory.FREE,
            func=calculate,
            parameters=_schema({
                "expression": {
                    "type": "string",
                    "description": "Expressão matemática, por exemplo '(144 ** 0.5) * 15'.",
                },
            }, required=["expression"]),
        ))
        self.register(ToolDefinition(
            name="get_system_info",
            description="Obtém informações do sistema operacional e armazenamento.",
            category=ActionCategory.FREE,
            func=get_system_info,
        ))
        self.register(ToolDefinition(
            name="get_system_metrics",
            description="Obtém métricas em tempo real de hardware: RAM (usada/total), VRAM/GPU (temperatura e uso da placa de vídeo) e CPU.",
            category=ActionCategory.FREE,
            func=get_system_metrics,
        ))

        # Category 2: Requires explicit user authorization
        self.register(ToolDefinition(
            name="write_file",
            description="Cria ou sobrescreve um arquivo em diretório autorizado.",
            category=ActionCategory.REQUIRES_AUTH,
            func=write_file,
            risk_description="Esta ação irá criar ou modificar um arquivo no seu computador.",
            parameters=_schema({
                "path": {"type": "string", "description": "Caminho do arquivo a criar/sobrescrever."},
                "content": {"type": "string", "description": "Conteúdo textual completo do arquivo."},
                "overwrite": {
                    "type": "boolean",
                    "description": "Se falso, recusa sobrescrever um arquivo existente.",
                },
            }, required=["path", "content"]),
        ))
        self.register(ToolDefinition(
            name="create_directory",
            description="Cria uma nova pasta em diretório autorizado.",
            category=ActionCategory.REQUIRES_AUTH,
            func=create_directory,
            risk_description="Esta ação criará um novo diretório no sistema.",
            parameters=_schema({
                "path": {"type": "string", "description": "Caminho da pasta a criar."},
            }, required=["path"]),
        ))
        self.register(ToolDefinition(
            name="delete_file",
            description=(
                "Descarta um arquivo ou pasta: o item vai para a Reserva (_Quarentena) dentro da "
                "pasta autorizada. Nada é apagado de verdade, e o usuário pode desfazer."
            ),
            category=ActionCategory.REQUIRES_AUTH,
            func=delete_file,
            risk_description="O item sairá do lugar e irá para a Reserva (_Quarentena). Pode ser desfeito.",
            always_confirm=True,
            parameters=_schema({
                "path": {"type": "string", "description": "Caminho do arquivo/pasta a descartar."},
                "recursive": {
                    "type": "boolean",
                    "description": "Necessário para enviar uma pasta não vazia à Reserva.",
                },
            }, required=["path"]),
        ))
        self.register(ToolDefinition(
            name="move_files",
            description=(
                "Move vários arquivos/pastas de uma vez, segundo um plano origem → destino "
                "(caminhos completos). O usuário vê o plano inteiro antes de aprovar; tudo fica "
                "no histórico e pode ser desfeito. Destinos existentes nunca são sobrescritos."
            ),
            category=ActionCategory.REQUIRES_AUTH,
            func=move_files,
            risk_description="Os itens listados mudarão de pasta conforme o plano. Pode ser desfeito.",
            always_confirm=True,
            parameters=_schema({
                "moves": {
                    "type": "array",
                    "description": "Plano: lista de {origem, destino}, ambos caminhos completos.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "origem": {"type": "string"},
                            "destino": {"type": "string"},
                        },
                        "required": ["origem", "destino"],
                    },
                },
                "descricao": {"type": "string", "description": "Resumo do plano (ex.: 'Separar PDFs por ano')."},
            }, required=["moves"]),
        ))
        self.register(ToolDefinition(
            name="rename_file",
            description="Renomeia um arquivo ou pasta na mesma pasta (sem sobrescrever). Pode ser desfeito.",
            category=ActionCategory.REQUIRES_AUTH,
            func=rename_file,
            risk_description="O item será renomeado. Pode ser desfeito.",
            always_confirm=True,
            parameters=_schema({
                "path": {"type": "string", "description": "Caminho atual do arquivo/pasta."},
                "new_name": {"type": "string", "description": "Novo nome, sem pastas."},
            }, required=["path", "new_name"]),
        ))

        # Category 3: External (Internet)
        self.register(ToolDefinition(
            name="search_web",
            description="Realiza pesquisa de informações na internet.",
            category=ActionCategory.EXTERNAL,
            func=search_web,
            risk_description="Esta ação conectará à internet para buscar informações externas.",
            parameters=_schema({
                "query": {"type": "string", "description": "Consulta de pesquisa."},
                "max_results": {
                    "type": "integer",
                    "description": "Número máximo de resultados (1 a 10).",
                },
            }, required=["query"]),
        ))
        self.register(ToolDefinition(
            name="read_url",
            description="Acessa e lê o conteúdo textual de uma página da web pública a partir de sua URL.",
            category=ActionCategory.EXTERNAL,
            func=read_url,
            risk_description="Esta ação conectará à internet para ler o conteúdo da página web informada.",
            parameters=_schema({
                "url": {"type": "string", "description": "URL completa da página web (ex.: 'https://exemplo.com/artigo')."},
                "max_chars": {
                    "type": "integer",
                    "description": "Limite máximo de caracteres a extrair (padrão 6000).",
                },
            }, required=["url"]),
        ))

    @staticmethod
    def _resource_target(params: Dict[str, Any]) -> str:
        for key in ("path", "query", "expression", "url"):
            if params.get(key) is not None:
                return str(params.get(key))
        moves = params.get("moves")
        if isinstance(moves, list):
            return f"{len(moves)} item(ns) no plano"
        return "local"

    @staticmethod
    def _normalize_params(tool: ToolDefinition, params: Dict[str, Any]) -> Dict[str, Any]:
        """Drops unknown keys and checks required fields before execution."""
        schema = tool.parameters or {}
        properties = schema.get("properties") or {}
        cleaned = {k: v for k, v in params.items() if k in properties}
        missing = [k for k in schema.get("required", []) if k not in cleaned]
        if missing:
            raise ValueError(
                "Parâmetros obrigatórios ausentes: " + ", ".join(missing)
            )
        return cleaned

    async def _run_tool(self, tool: ToolDefinition, params: Dict[str, Any]) -> Dict[str, Any]:
        """Executes an already-authorized/free tool. Internal use only."""
        resource_target = self._resource_target(params)
        try:
            params = self._normalize_params(tool, params)
            if inspect.iscoroutinefunction(tool.func):
                result = await tool.func(**params)
            else:
                result = tool.func(**params)

            security_manager.log_action(
                action_type=tool.name,
                category=tool.category,
                resource=resource_target,
                authorized=True,
                details="Executed successfully"
            )
            return {"status": "success", "result": result}
        except Exception as e:
            security_manager.log_action(
                action_type=tool.name,
                category=tool.category,
                resource=resource_target,
                authorized=True,
                details=f"Execution error: {str(e)}"
            )
            return {"status": "error", "error": str(e)}

    async def execute_tool(
        self,
        name: str,
        params: Dict[str, Any],
        authorized: bool = False,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Public entry point used by the HTTP API and by the model tool-calling
        loop.

        `authorized` is accepted only for backward compatibility and is NEVER
        trusted: protected and external tools always create a pending
        authorization request, resolved server-side by the user.
        """
        tool = self.tools.get(name)
        if not tool:
            return {"error": f"Ferramenta desconhecida: '{name}'", "status": "error"}
        if not isinstance(params, dict):
            return {"error": "Parâmetros inválidos: esperado um objeto JSON.", "status": "error"}

        try:
            params = self._normalize_params(tool, params)
        except ValueError as e:
            return {"status": "error", "error": str(e)}

        resource_target = self._resource_target(params)

        if tool.needs_approval:
            action_id = security_manager.create_authorization_request(
                action_type=tool.name,
                category=tool.category,
                resource=resource_target,
                description=tool.risk_description,
                payload=params,
                context=context,
            )
            return {
                "status": "requires_authorization",
                "action_id": action_id,
                "tool_name": tool.name,
                "category": tool.category.value,
                "resource": resource_target,
                "description": tool.risk_description,
                "parameters": params
            }

        return await self._run_tool(tool, params)

    async def execute_approved_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a pending action previously approved by the user.
        Only called by the authorization endpoint with the server-stored payload.
        """
        tool = self.tools.get(action.get("action_type"))
        if not tool:
            return {"status": "error", "error": "Ferramenta da autorização não existe mais."}
        if not (tool.is_protected or tool.always_confirm):
            return {"status": "error", "error": "Ação livre não deveria exigir autorização."}
        params = action.get("payload", {})
        return await self._run_tool(tool, params)

    def get_ollama_tools(self) -> List[Dict[str, Any]]:
        """Tool schemas in the format expected by Ollama /api/chat."""
        tools = []
        for tool in self.tools.values():
            description = tool.description
            if tool.needs_approval:
                description += (
                    " IMPORTANTE: esta ferramenta exige aprovação explícita do "
                    "usuário; o resultado pode vir como 'requires_authorization'."
                )
            tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": description,
                    "parameters": tool.parameters,
                },
            })
        return tools

    def get_tool_schemas_for_prompt(self) -> str:
        """Fallback catalog used when the model cannot emit tool calls."""
        lines = [
            "FERRAMENTAS DISPONÍVEIS (o backend executa ferramentas pedidas pelo "
            "modelo; ações protegidas sempre exigem aprovação explícita do usuário):"
        ]
        for t in self.tools.values():
            req = (
                "(Requer autorização explícita do usuário)"
                if t.needs_approval
                else "(Acesso livre, limitado aos diretórios autorizados)"
            )
            lines.append(f"- `{t.name}`: {t.description} {req}")
        return "\n".join(lines)


tool_registry = ToolRegistry()
