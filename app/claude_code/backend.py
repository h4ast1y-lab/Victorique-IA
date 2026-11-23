"""
Um turno no modo Claude Code: abre um ClaudeSDKClient (retomando a sessão da
conversa), traduz as mensagens do SDK para os eventos SSE que a interface já
entende e grava a resposta, as ferramentas usadas e o session_id.
"""
import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKClient,
    CLINotFoundError,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from app.claude_code.options import build_options
from app.claude_code.permissions import PermissionBridge
from app.config import settings
from app.core.personality import personality_manager
from app.core.sse import CANCELLED_MARKER, NO_TEXT_FALLBACK, sse_event, truncate
from app.memory.conversation_store import conversation_store
from app.memory.project_store import project_store
from app.voice import tts_engine

logger = logging.getLogger("claude_code.backend")

TRACE_RESULT_CHARS = 1500
INTERRUPT_SECONDS = 5.0
DRAIN_SECONDS = 10.0
_END = object()

LOGIN_HELP = (
    "O Claude Code não está com login válido nesta máquina. Abra um terminal e rode "
    "`claude auth login` (sem o Claude Code instalado, use o executável que vem com o app: "
    "`.venv\\Lib\\site-packages\\claude_agent_sdk\\_bundled\\claude.exe auth login`). "
    "Depois tente de novo."
)
LOGIN_HINTS = ("login", "authenticat", "api key", "auth", "credential")
RESUME_NOTICE = (
    "Não deu para retomar a sessão anterior do Claude Code; comecei uma nova. "
    "O Claude não verá as mensagens anteriores desta conversa."
)
TOOLS_NOTE = (
    "FERRAMENTAS DA VICTORIQUE: use buscar_memorias para as preferências e fatos que o "
    "usuário salvou no app, e buscar_documentos para os documentos que ele indexou. "
    "Responda sempre em português do Brasil."
)


def friendly_error(error: Any) -> str:
    if isinstance(error, CLINotFoundError):
        return (
            "Claude Code não encontrado. Reinstale as dependências com "
            "`pip install -r requirements.txt`."
        )
    text = str(error).strip() or error.__class__.__name__
    if any(hint in text.lower() for hint in LOGIN_HINTS):
        return f"{LOGIN_HELP} (Detalhe: {text[:300]})"
    return f"Erro no Claude Code: {text[:500]}"


def build_append_prompt(project_id: Optional[str], personality_id: Optional[str]) -> str:
    personality = personality_manager.get_personality(personality_id) if personality_id else None
    parts = [personality_manager.build_system_prompt(personality, mode="claude-code")]
    if project_id:
        project = project_store.get_project(project_id)
        if project:
            parts.append(
                f"PROJETO ATIVO: '{project['name']}'\n"
                f"Descrição: {project.get('description', '')}\n"
                f"Diretrizes do Projeto: {project.get('instructions', '')}"
            )
    parts.append(TOOLS_NOTE)
    return "\n\n".join(parts)


def _result_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                pieces.append(str(item.get("text", "")))
            else:
                pieces.append(json.dumps(item, ensure_ascii=False, default=str))
        return "\n".join(pieces)
    return json.dumps(content, ensure_ascii=False, default=str)


class _Turn:
    """State of one turn, fed by the SDK messages."""

    def __init__(self, emit: Callable[[Any], None]):
        self.emit = emit
        self.parts: List[str] = []
        self.tool_trace: List[Dict[str, Any]] = []
        self.tools: Dict[str, Dict[str, Any]] = {}
        self.session_id: Optional[str] = None
        self.error: Optional[str] = None
        self.got_output = False
        self.delta_since_message = False
        self.separate = False
        self.client: Any = None
        self.cancelled = False

    def text(self) -> str:
        return "".join(self.parts)

    def _out(self, payload: Dict[str, Any]) -> None:
        self.got_output = True
        self.emit(payload)

    def _start_text_block(self) -> None:
        """A new text block after earlier text (e.g. after a tool) starts a new paragraph."""
        self.separate = bool(self.parts)

    def _add_text(self, text: str) -> None:
        if self.separate:
            self.separate = False
            if not self.text().endswith("\n"):
                text = "\n\n" + text.lstrip("\n")
        self.parts.append(text)
        self._out({"type": "token", "content": text})

    def handle(self, message: Any) -> None:
        if isinstance(message, StreamEvent):
            self._stream_event(message)
        elif isinstance(message, AssistantMessage):
            self._assistant(message)
        elif isinstance(message, UserMessage):
            self._user(message)
        elif isinstance(message, ResultMessage):
            self.session_id = message.session_id or self.session_id
            if message.is_error and not self.cancelled:
                detail = message.result or "; ".join(message.errors or []) or message.subtype
                self.error = friendly_error(detail)

    def _stream_event(self, message: StreamEvent) -> None:
        if message.parent_tool_use_id:  # subagent output stays out of the answer
            return
        event = message.event or {}
        if event.get("type") == "content_block_start":
            if (event.get("content_block") or {}).get("type") == "text":
                self._start_text_block()
            return
        if event.get("type") != "content_block_delta":
            return
        delta = event.get("delta") or {}
        if delta.get("type") == "text_delta" and delta.get("text"):
            self.delta_since_message = True
            self._add_text(delta["text"])
        elif delta.get("type") == "thinking_delta" and delta.get("thinking"):
            self._out({"type": "reasoning", "content": delta["thinking"]})

    def _assistant(self, message: AssistantMessage) -> None:
        if message.error:
            self.error = friendly_error(message.error)
        for block in message.content:
            if isinstance(block, ToolUseBlock):
                self.tools[block.id] = {"tool": block.name, "arguments": block.input}
                self._out({"type": "tool_call", "tool": block.name, "arguments": block.input})
            elif (
                isinstance(block, TextBlock)
                and not self.delta_since_message
                and not message.parent_tool_use_id
                and not message.error
                and block.text
            ):
                # Partial messages missing: the full block is the only source.
                self._start_text_block()
                self._add_text(block.text)
        self.delta_since_message = False

    def _user(self, message: UserMessage) -> None:
        if not isinstance(message.content, list):
            return
        for block in message.content:
            if not isinstance(block, ToolResultBlock):
                continue
            call = self.tools.get(block.tool_use_id, {"tool": "ferramenta", "arguments": {}})
            status = "error" if block.is_error else "success"
            output = truncate(_result_text(block.content), TRACE_RESULT_CHARS)
            self.tool_trace.append({
                "tool": call["tool"],
                "arguments": call["arguments"],
                "status": status,
                "result": output,
            })
            self._out({
                "type": "tool_result",
                "tool": call["tool"],
                "status": status,
                "result": {"status": status, "result": output},
            })


class ClaudeCodeBackend:
    def __init__(self, client_factory: Callable[..., Any] = ClaudeSDKClient):
        self.client_factory = client_factory
        self.last_error: Optional[str] = None
        self._cleanup: Set[asyncio.Task] = set()

    async def _attempt(self, turn: _Turn, prompt: str, options: Any) -> None:
        client = self.client_factory(options)
        turn.client = client
        try:
            await client.connect()
            await client.query(prompt)
            async for message in client.receive_response():
                turn.handle(message)
        finally:
            try:
                await client.disconnect()
            except Exception as exc:  # never mask the turn's own outcome
                logger.debug("disconnect failed: %s", exc)
            turn.client = None

    async def _consume(self, turn: _Turn, prompt: str, make_options, resume: Optional[str]) -> None:
        try:
            failure: Optional[BaseException] = None
            try:
                await self._attempt(turn, prompt, make_options(resume))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                failure = exc
            if resume and (failure or turn.error) and not turn.got_output and not turn.cancelled:
                logger.warning("resume %s failed (%s); starting a new session", resume, failure or turn.error)
                turn.error = None
                turn.emit({"type": "notice", "message": RESUME_NOTICE})
                await self._attempt(turn, prompt, make_options(None))
            elif failure:
                raise failure
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Claude Code turn failed: %s", exc)
            if not turn.cancelled:
                turn.error = friendly_error(exc)
        finally:
            turn.emit(_END)

    async def _stop(self, turn: _Turn, consumer: asyncio.Task, conversation_id: str) -> None:
        """Interrupts the SDK turn and drains it so the CLI process closes cleanly."""
        client = turn.client
        if client is not None:
            try:
                await asyncio.wait_for(client.interrupt(), INTERRUPT_SECONDS)
            except Exception as exc:
                logger.debug("interrupt failed: %s", exc)
        try:
            await asyncio.wait_for(consumer, DRAIN_SECONDS)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception) as exc:
            logger.debug("drain after interrupt ended with %r", exc)
        if turn.session_id:
            conversation_store.set_claude_session(conversation_id, turn.session_id)

    def _save(self, conversation_id: str, content: str, turn: _Turn) -> Optional[Dict[str, Any]]:
        try:
            return conversation_store.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=content,
                tool_trace=turn.tool_trace or None,
            )
        except Exception as exc:
            logger.error("Failed to save Claude Code answer: %s", exc)
            return None

    async def run_turn(
        self,
        conversation_id: str,
        user_message: str,
        project_id: Optional[str],
        personality_id: Optional[str],
    ) -> AsyncGenerator[str, None]:
        """Yields SSE strings. The caller has already saved the user message."""
        queue: asyncio.Queue = asyncio.Queue()
        bridge = PermissionBridge(emit=queue.put_nowait, conversation_id=conversation_id)
        turn = _Turn(queue.put_nowait)
        resume = conversation_store.get_claude_session(conversation_id)
        append_prompt = build_append_prompt(project_id, personality_id)

        def make_options(resume_id: Optional[str]):
            return build_options(
                append_prompt=append_prompt, resume=resume_id, bridge=bridge, project_id=project_id
            )

        consumer: Optional[asyncio.Task] = None
        finished = False
        try:
            yield sse_event({
                "type": "meta", "conversation_id": conversation_id, "backend": "claude-code",
            })
            consumer = asyncio.create_task(
                self._consume(turn, user_message, make_options, resume)
            )
            while True:
                item = await queue.get()
                if item is _END:
                    break
                yield sse_event(item)
            await consumer

            content = turn.text()
            if turn.error:
                self.last_error = turn.error
                yield sse_event({"type": "error", "message": turn.error})
                content = content or f"⚠️ {turn.error}"
            else:
                self.last_error = None
                if turn.session_id:
                    conversation_store.set_claude_session(conversation_id, turn.session_id)
                if not content.strip():
                    content = NO_TEXT_FALLBACK
                if settings.tts_enabled and settings.tts_speak_responses and tts_engine.available:
                    tts_engine.speak_async(content)

            saved = self._save(conversation_id, content, turn)
            finished = True
            yield sse_event({
                "type": "done",
                "conversation_id": conversation_id,
                "message_id": saved["id"] if saved else None,
                "content": content,
                "tool_calls": len(turn.tool_trace),
                "backend": "claude-code",
            })
        except (GeneratorExit, asyncio.CancelledError):
            if not finished:
                turn.cancelled = True
                bridge.cancel_pending()
                partial = turn.text().strip()
                if partial:
                    self._save(conversation_id, partial + CANCELLED_MARKER, turn)
                if consumer is not None and not consumer.done():
                    # Runs outside this generator: the caller's cancel scope
                    # would cancel any await made here.
                    task = asyncio.get_running_loop().create_task(
                        self._stop(turn, consumer, conversation_id)
                    )
                    self._cleanup.add(task)
                    task.add_done_callback(self._cleanup.discard)
                logger.info("Claude Code turn cancelled for conversation %s", conversation_id)
            raise


claude_code_backend = ClaudeCodeBackend()
