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
from app.core import attachments as chat_attachments
from app.library import activity
from app.core.avatar_protocol import AVATAR_INSTRUCTIONS, AvatarControlParser
from app.core.deep_thinking import DEEP_THINKING_INSTRUCTIONS, THOUGHT_ONLY_NOTE, ThoughtRouter
from app.core.dialogue_style import style_note
from app.core.personality import personality_manager
from app.core.sse import CANCELLED_MARKER, NO_TEXT_FALLBACK, sse_event, truncate
from app.core.transcript import recent_transcript, wrap_with_transcript
from app.memory.conversation_store import conversation_store
from app.memory.memory_store import memory_store
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
    "Não deu para retomar a sessão anterior do Claude Code; comecei uma nova, com um resumo "
    "das últimas mensagens desta conversa."
)
TOOLS_NOTE = (
    "FERRAMENTAS DA VICTORIQUE: as memórias principais que o usuário salvou no app já vêm "
    "acima; use buscar_memorias para procurar outras e buscar_documentos para os documentos "
    "que ele indexou.\n"
    "ORGANIZAR ARQUIVOS (a Biblioteca): para mover, renomear ou descartar arquivos do usuário, "
    "use SEMPRE mover_arquivos, renomear e mandar_para_reserva, nunca Bash, Write ou comandos "
    "de apagar. Antes, leia as pastas (Read, Glob, Grep), monte o plano completo origem → "
    "destino e mostre-o ao usuário; depois chame mover_arquivos com o plano inteiro de uma vez "
    "(o usuário aprova na barra de autorização). Nada se apaga: descartes vão para a Reserva "
    "(_Quarentena) e o usuário pode desfazer pelo Organizador. Pastas do sistema (Windows, "
    "Program Files, AppData) são proibidas.\n"
    "DOCUMENTOS (Word, Excel, PowerPoint, PDF, CSV): para ler, use ler_documento (paginado; "
    "[¶n] numera parágrafos do Word, planilhas aparecem com colunas em letras). Para alterar, "
    "use editar_word, editar_planilha, editar_pdf ou criar_documento, nunca Bash, scripts ou "
    "Write em arquivos binários. O original sempre vai para a Reserva antes; diga ao usuário "
    "onde ficou a versão nova. Anexos do chat ficam nos dados do app e não são alterados: a "
    "versão editada vai para Documentos\\Victorique.\n"
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


def build_append_prompt(
    project_id: Optional[str],
    personality_id: Optional[str],
    history: Optional[List[Dict[str, Any]]] = None,
) -> str:
    personality = personality_manager.get_personality(personality_id) if personality_id else None
    parts = [personality_manager.build_system_prompt(personality, mode="claude-code")]
    if project_id:
        project = project_store.get_project(project_id)
        if project:
            parts.append(
                f"CASO ATIVO: '{project['name']}'\n"
                f"Descrição: {project.get('description', '')}\n"
                f"Dossiê do caso (instruções): {project.get('instructions', '')}"
            )
    # Saved memories ride in the system prompt. Ranked without the message text
    # on purpose: the prompt stays identical between turns (cache-friendly) and
    # buscar_memorias finds the rest on demand.
    memories = memory_store.get_context_for_prompt(project_id=project_id)
    if memories:
        parts.append(memories)
    parts.extend([AVATAR_INSTRUCTIONS, TOOLS_NOTE])
    note = style_note(history or [])
    if note:
        parts.append(note)
    return "\n\n".join(parts)


def build_user_content(user_message: str, attachments: Optional[List[Dict[str, Any]]]) -> Any:
    """The prompt: plain text, or content blocks when images go along."""
    files = list(attachments or [])
    if not files:
        return user_message
    pictures = chat_attachments.images(files)
    blocks: List[Dict[str, Any]] = []
    for row in pictures:
        try:
            media, data = chat_attachments.image_base64(row)
        except Exception as exc:
            logger.warning("anexo %s não pôde ser lido: %s", row.get("name"), exc)
            continue
        blocks.append({"type": "image", "source": {"type": "base64", "media_type": media, "data": data}})
    note = chat_attachments.prompt_note(files, images_inline=bool(blocks))
    text = ((user_message or "").strip() + "\n\n" + note).strip()
    if not blocks:
        return text
    blocks.append({"type": "text", "text": text})
    return blocks


def with_transcript(content: Any, transcript: str) -> Any:
    """The prompt of a NEW session on a conversation that already has messages."""
    if not transcript:
        return content
    if isinstance(content, str):
        return wrap_with_transcript(transcript, content)
    blocks = list(content)
    for index in range(len(blocks) - 1, -1, -1):
        if blocks[index].get("type") == "text":
            blocks[index] = {"type": "text", "text": wrap_with_transcript(transcript, blocks[index]["text"])}
            return blocks
    blocks.append({"type": "text", "text": wrap_with_transcript(transcript, "")})
    return blocks


async def _single_message(content: List[Dict[str, Any]]):
    """client.query() with content blocks takes an async iterable of messages."""
    yield {
        "type": "user",
        "message": {"role": "user", "content": content},
        "parent_tool_use_id": None,
    }


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

    def __init__(self, emit: Callable[[Any], None], deep_thinking: bool = False):
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
        # Splits her <pensamento> block (Pensamento Profundo) and the hidden
        # avatar markers out of the answer text.
        self.router = ThoughtRouter(deep_thinking)
        self.router.new_block(AvatarControlParser())

    def text(self) -> str:
        return "".join(self.parts)

    def _out(self, payload: Dict[str, Any]) -> None:
        self.got_output = True
        self.emit(payload)

    def _start_text_block(self) -> None:
        """A new text block after earlier text (e.g. after a tool) starts a new paragraph."""
        if self.parts or self.tools or self.router.thought:
            # The final answer (after tools) may pick its own expression and think again.
            self.finish_text()
            self.router.new_block(AvatarControlParser())
        self.separate = bool(self.parts)

    def _emit_routed(self, events: List[Dict[str, Any]]) -> None:
        for event in events:
            if event.get("type") != "token":
                self._out(event)
                continue
            chunk = event["content"]
            if self.separate:
                self.separate = False
                if not self.text().endswith("\n"):
                    chunk = "\n\n" + chunk.lstrip("\n")
            self.parts.append(chunk)
            self._out({"type": "token", "content": chunk})

    def _add_text(self, text: str) -> None:
        events, _chunks = self.router.feed(text)
        self._emit_routed(events)

    def finish_text(self) -> None:
        """Releases text held back (a lone "[", an unfinished thought)."""
        events, _chunks = self.router.finish_block()
        self._emit_routed(events)

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
            for payload in self.router.native(delta["thinking"]):
                self._out(payload)

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
            if status == "success":
                activity.record_tool(call["tool"], call["arguments"])
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

    async def _attempt(self, turn: _Turn, prompt: Any, options: Any) -> None:
        client = self.client_factory(options)
        turn.client = client
        try:
            await client.connect()
            # A fresh iterable per attempt: a resumed session may be retried.
            await client.query(prompt if isinstance(prompt, str) else _single_message(prompt))
            async for message in client.receive_response():
                turn.handle(message)
        finally:
            try:
                await client.disconnect()
            except Exception as exc:  # never mask the turn's own outcome
                logger.debug("disconnect failed: %s", exc)
            turn.client = None

    async def _consume(self, turn: _Turn, make_prompt, make_options, resume: Optional[str]) -> None:
        try:
            failure: Optional[BaseException] = None
            try:
                await self._attempt(turn, make_prompt(resume), make_options(resume))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                failure = exc
            if resume and (failure or turn.error) and not turn.got_output and not turn.cancelled:
                logger.warning("resume %s failed (%s); starting a new session", resume, failure or turn.error)
                turn.error = None
                turn.emit({"type": "notice", "message": RESUME_NOTICE})
                await self._attempt(turn, make_prompt(None), make_options(None))
            elif failure:
                raise failure
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Claude Code turn failed: %s", exc)
            if not turn.cancelled:
                turn.error = friendly_error(exc)
        finally:
            turn.finish_text()
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
                reasoning=turn.router.thought or None,
                reasoning_seconds=turn.router.seconds,
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
        deep_thinking: bool = False,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[str, None]:
        """Yields SSE strings. The caller has already saved the user message."""
        queue: asyncio.Queue = asyncio.Queue()
        bridge = PermissionBridge(emit=queue.put_nowait, conversation_id=conversation_id)
        turn = _Turn(queue.put_nowait, deep_thinking=deep_thinking)
        resume = conversation_store.get_claude_session(conversation_id)
        history = conversation_store.get_messages(conversation_id, limit=30)
        append_prompt = build_append_prompt(project_id, personality_id, history)
        # A new session (first Claude turn after chatting in another mode, or a
        # lost session) gets the conversation so far; a resumed one has it.
        transcript = recent_transcript(history, user_message)
        if deep_thinking:
            append_prompt += "\n\n" + DEEP_THINKING_INSTRUCTIONS

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
            prompt = await asyncio.to_thread(build_user_content, user_message, attachments)

            def make_prompt(resume_id: Optional[str]) -> Any:
                return prompt if resume_id else with_transcript(prompt, transcript)

            consumer = asyncio.create_task(
                self._consume(turn, make_prompt, make_options, resume)
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
                    content = THOUGHT_ONLY_NOTE if turn.router.thought else NO_TEXT_FALLBACK
                if settings.tts_enabled and settings.tts_speak_responses and tts_engine.available:
                    tts_engine.speak_async(content)

            saved = self._save(conversation_id, content, turn)
            finished = True
            done = {
                "type": "done",
                "conversation_id": conversation_id,
                "message_id": saved["id"] if saved else None,
                "content": content,
                "tool_calls": len(turn.tool_trace),
                "backend": "claude-code",
            }
            if turn.router.thought:
                done["reasoning_seconds"] = turn.router.seconds
            yield sse_event(done)
        except (GeneratorExit, asyncio.CancelledError):
            if not finished:
                turn.cancelled = True
                bridge.cancel_pending()
                partial = turn.text().strip()
                if partial or turn.router.thought:
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
