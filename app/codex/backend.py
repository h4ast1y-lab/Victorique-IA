"""
Um turno no modo Codex: roda `codex exec --json` (o CLI da OpenAI) numa
sandbox somente leitura, retomando a sessão (thread) da conversa, e traduz os
eventos JSONL para os eventos SSE que a interface já entende.

Eventos do Codex: thread.started, turn.started/completed/failed, error e
item.started/updated/completed com itens agent_message, reasoning,
command_execution, file_change, mcp_tool_call, web_search, todo_list e error.

O prompt vai pelo stdin (`-`), nunca pela linha de comando. A persona e as
regras vão no começo de cada sessão nova; nas retomadas, só um lembrete.
Nada é instalado automaticamente: sem o Codex, o chat explica como instalar.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import threading
from collections import deque
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Deque, Dict, List, Optional

from app.config import settings
from app.core import attachments as chat_attachments
from app.core.avatar_protocol import AVATAR_INSTRUCTIONS, AvatarControlParser
from app.core.deep_thinking import DEEP_THINKING_INSTRUCTIONS, THOUGHT_ONLY_NOTE, ThoughtRouter
from app.core.dialogue_style import style_note
from app.core.personality import personality_manager
from app.core.sse import CANCELLED_MARKER, NO_TEXT_FALLBACK, sse_event, truncate
from app.library import activity
from app.memory.conversation_store import conversation_store
from app.memory.project_store import project_store

logger = logging.getLogger("codex.backend")

TRACE_RESULT_CHARS = 1500
HISTORY_MESSAGES = 12
HISTORY_CHARS = 1200
STDERR_LINES = 30
_THREAD_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

INSTALL_STEPS = [
    "Instale o Node.js (https://nodejs.org), se ainda não tiver.",
    "Num terminal, rode: npm install -g @openai/codex",
    "Depois rode: codex login (entra com a sua conta do ChatGPT ou com uma chave da API da OpenAI).",
    "Volte aqui e mande a mensagem de novo.",
]
INSTALL_HELP = (
    "O Codex não está instalado neste computador. Para usar este modo: instale o Node.js "
    "(https://nodejs.org), rode num terminal `npm install -g @openai/codex` e depois "
    "`codex login`. Em seguida, mande a mensagem de novo."
)
LOGIN_HELP = (
    "O Codex não está com login válido nesta máquina. Abra um terminal e rode `codex login`; "
    "depois tente de novo."
)
LOGIN_HINTS = ("login", "unauthorized", "401", "authenticat", "api key", "not logged", "auth")
RESUME_NOTICE = (
    "Não deu para retomar a sessão anterior do Codex; comecei uma nova, com um resumo das "
    "últimas mensagens desta conversa."
)
CODEX_NOTE = (
    "AMBIENTE: você roda numa sandbox somente leitura, na pasta de trabalho do usuário. Pode ler "
    "e listar arquivos com comandos para responder, mas não altera nada no computador. Se o "
    "usuário pedir para mover, renomear, apagar ou criar arquivos, diga que neste modo você só "
    "consulta e que o modo local ou o Claude Code fazem isso, com a aprovação dele.\n"
    "Responda sempre em português do Brasil."
)
REMINDER = (
    "(Lembrete do aplicativo: continue como {name}, em português do Brasil, seguindo as "
    "instruções do início desta sessão.)"
)
NO_THOUGHT_NOTE = "(Pensamento profundo desligado nesta mensagem: responda direto, sem bloco <pensamento>.)"

# Commands that only read: a read or a listing the Biblioteca can show.
_READ_VERBS = {"cat", "type", "get-content", "gc", "head", "tail", "less", "more", "nl", "sed", "bat"}
_LIST_VERBS = {"ls", "dir", "get-childitem", "gci", "tree", "find", "rg", "grep", "select-string", "sls"}
_WRAPPED = re.compile(r"""(?:\s-lc|\s-c|\s-command)\s+(['"])(.*)\1\s*$""", re.IGNORECASE | re.DOTALL)


# ----------------- Finding and calling the CLI -----------------
def find_codex() -> Optional[List[str]]:
    """The command prefix that runs the Codex CLI, or None when it isn't installed."""
    candidates: List[str] = []
    configured = os.environ.get("ASSISTANT_CODEX_PATH", "").strip().strip('"')
    if configured:
        candidates.append(configured)
    found = shutil.which("codex")
    if found:
        candidates.append(found)
    if os.name == "nt" and os.environ.get("APPDATA"):
        candidates.append(str(Path(os.environ["APPDATA"]) / "npm" / "codex.cmd"))
    for candidate in candidates:
        path = Path(candidate)
        if not path.is_file():
            continue
        if path.suffix.lower() in (".cmd", ".bat"):
            # npm's shim: run its script with node directly, without cmd.exe.
            script = path.parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
            node = shutil.which("node")
            if script.is_file() and node:
                return [node, str(script)]
        return [str(path)]
    return None


def build_command(prefix: List[str], workspace: str, thread_id: Optional[str], model: str,
                  images: Optional[List[str]] = None) -> List[str]:
    """`codex exec` in a read-only sandbox; the prompt comes from stdin ("-")."""
    cmd = [*prefix, "exec", "--json", "--skip-git-repo-check", "--sandbox", "read-only", "-C", workspace]
    if model:
        cmd += ["-m", model]
    # "--image=path" (one per file): the flag takes several values, so the "="
    # form keeps it from swallowing the arguments that follow.
    cmd += [f"--image={path}" for path in images or []]
    if thread_id:
        cmd += ["resume", thread_id]
    cmd.append("-")
    return cmd


def _popen(cmd: List[str], cwd: str) -> Any:
    env = dict(os.environ)
    env.setdefault("NO_COLOR", "1")
    return subprocess.Popen(
        cmd, cwd=cwd, env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def friendly_error(error: Any) -> str:
    text = str(error).strip() or error.__class__.__name__
    if any(hint in text.lower() for hint in LOGIN_HINTS):
        return f"{LOGIN_HELP} (Detalhe: {text[:300]})"
    return f"Erro no Codex: {text[:500]}"


def _valid_thread(thread_id: Optional[str]) -> Optional[str]:
    return thread_id if thread_id and _THREAD_RE.match(thread_id) else None


# ----------------- Prompt -----------------
def _instructions(project_id: Optional[str], personality: Optional[Dict[str, Any]],
                  history: List[Dict[str, Any]], deep_thinking: bool) -> str:
    parts = [personality_manager.build_system_prompt(personality, mode="codex")]
    if project_id:
        project = project_store.get_project(project_id)
        if project:
            parts.append(
                f"CASO ATIVO: '{project['name']}'\n"
                f"Descrição: {project.get('description', '')}\n"
                f"Dossiê do caso (instruções): {project.get('instructions', '')}"
            )
    parts.extend([AVATAR_INSTRUCTIONS, CODEX_NOTE])
    note = style_note(history)
    if note:
        parts.append(note)
    if deep_thinking:
        parts.append(DEEP_THINKING_INSTRUCTIONS)
    return "\n\n".join(parts)


def _transcript(history: List[Dict[str, Any]], user_message: str) -> str:
    """The last messages before this one, so a new session isn't blind."""
    prior = list(history)
    if prior and prior[-1].get("role") == "user" and prior[-1].get("content") == user_message:
        prior = prior[:-1]
    lines = []
    for message in prior[-HISTORY_MESSAGES:]:
        who = "Usuário" if message.get("role") == "user" else "Você"
        text = truncate(str(message.get("content") or ""), HISTORY_CHARS)
        if message.get("attachments"):
            text = (text + " " + chat_attachments.history_note(message["attachments"])).strip()
        lines.append(f"{who}: {text}")
    return "\n\n".join(lines)


def build_prompt(user_message: str, project_id: Optional[str], personality_id: Optional[str],
                 history: List[Dict[str, Any]], deep_thinking: bool, resumed: bool,
                 attachments_note: str = "") -> str:
    personality = personality_manager.get_personality(personality_id) if personality_id else None
    tail = f"\n\n{attachments_note}" if attachments_note else ""
    if resumed:
        name = (personality or personality_manager.get_default_personality() or {}).get("name", "Victorique")
        parts = [REMINDER.format(name=name)]
        parts.append(DEEP_THINKING_INSTRUCTIONS if deep_thinking else NO_THOUGHT_NOTE)
        parts.append(f"MENSAGEM DO USUÁRIO:\n{user_message}{tail}")
        return "\n\n".join(parts)
    text = (
        "<instrucoes_do_aplicativo>\n"
        f"{_instructions(project_id, personality, history, deep_thinking)}\n"
        "</instrucoes_do_aplicativo>\n\n"
    )
    transcript = _transcript(history, user_message)
    if transcript:
        text += f"<conversa_ate_aqui>\n{transcript}\n</conversa_ate_aqui>\n\n"
    return text + f"MENSAGEM DO USUÁRIO:\n{user_message}{tail}"


# ----------------- The Biblioteca -----------------
def _command_activity(command: str, workspace: str) -> None:
    """A read-only command that names files or folders becomes a library scene."""
    try:
        inner = command
        wrapped = _WRAPPED.search(" " + command)
        if wrapped:
            inner = wrapped.group(2)
        inner = re.split(r"\s*(?:&&|\|\||\||;)\s*", inner, maxsplit=1)[0]
        tokens = [t.strip("'\"") for t in shlex.split(inner, posix=False)]
        if not tokens:
            return
        verb = Path(tokens[0]).name.lower()
        if verb.endswith(".exe"):
            verb = verb[:-4]
        if verb not in _READ_VERBS and verb not in _LIST_VERBS:
            return
        recorded = 0
        for token in tokens[1:]:
            if not token or token.startswith("-") or recorded >= 3:
                continue
            path = Path(token)
            if not path.is_absolute():
                path = Path(workspace) / path
            if verb in _READ_VERBS and path.is_file():
                activity.record("read", str(path))
                recorded += 1
            elif verb in _LIST_VERBS and path.is_dir():
                activity.record("list", str(path))
                recorded += 1
        if verb in _LIST_VERBS and not recorded and len(tokens) == 1:
            activity.record("list", workspace)
    except Exception:
        logger.debug("Codex: comando não virou cena da Biblioteca", exc_info=True)


# ----------------- One turn -----------------
class _CodexTurn:
    """State of one turn, fed by the JSONL lines of `codex exec --json`."""

    def __init__(self, emit: Callable[[Dict[str, Any]], None], deep_thinking: bool, workspace: str):
        self.emit = emit
        self.workspace = workspace
        self.parts: List[str] = []
        self.tool_trace: List[Dict[str, Any]] = []
        self.started: set = set()
        self.thread_id: Optional[str] = None
        self.error: Optional[str] = None
        self.last_error: Optional[str] = None
        self.completed = False
        self.got_output = False
        self.blocks = 0
        self.separate = False
        self.router = ThoughtRouter(deep_thinking)
        self.router.new_block(AvatarControlParser())

    def reset_for_retry(self) -> None:
        self.error = None
        self.last_error = None
        self.completed = False
        self.thread_id = None

    def text(self) -> str:
        return "".join(self.parts)

    def _out(self, payload: Dict[str, Any]) -> None:
        if payload.get("type") != "notice":
            self.got_output = True
        self.emit(payload)

    # --- text ---
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

    def _message(self, text: str) -> None:
        if self.blocks:
            # Several messages in one turn (before and after commands) are paragraphs.
            self.finish_text()
            self.router.new_block(AvatarControlParser())
        self.separate = bool(self.parts)
        self.blocks += 1
        events, _chunks = self.router.feed(text)
        self._emit_routed(events)

    def finish_text(self) -> None:
        events, _chunks = self.router.finish_block()
        self._emit_routed(events)

    # --- tools ---
    def _tool(self, phase: str, item_id: str, name: str, arguments: Dict[str, Any],
              ok: bool = True, output: str = "") -> None:
        if item_id not in self.started:
            self.started.add(item_id)
            self._out({"type": "tool_call", "tool": name, "arguments": arguments})
        if phase != "completed":
            return
        status = "success" if ok else "error"
        result = truncate(output or "", TRACE_RESULT_CHARS)
        self.tool_trace.append({"tool": name, "arguments": arguments, "status": status, "result": result})
        self._out({"type": "tool_result", "tool": name, "status": status,
                   "result": {"status": status, "result": result}})

    def _item(self, phase: str, item: Dict[str, Any]) -> None:
        kind = item.get("type")
        item_id = str(item.get("id") or id(item))
        if kind == "agent_message":
            if phase == "completed" and item.get("text"):
                self._message(str(item["text"]))
        elif kind == "reasoning":
            if phase == "completed" and item.get("text"):
                for payload in self.router.native(str(item["text"])):
                    self._out(payload)
        elif kind == "command_execution":
            command = str(item.get("command") or "")
            ok = item.get("status") == "completed" and item.get("exit_code") in (0, None)
            self._tool(phase, item_id, "Shell", {"command": command}, ok, str(item.get("aggregated_output") or ""))
            if phase == "completed" and ok:
                _command_activity(command, self.workspace)
        elif kind == "file_change":
            changes = [c for c in (item.get("changes") or []) if isinstance(c, dict)]
            ok = item.get("status") == "completed"
            summary = "\n".join(f"{c.get('kind')}: {c.get('path')}" for c in changes)
            self._tool(phase, item_id, "Edit", {"changes": changes}, ok, summary)
            if phase == "completed" and ok:
                for change in changes:
                    if change.get("kind") in ("add", "update"):
                        activity.record("write", change.get("path"))
        elif kind == "mcp_tool_call":
            name = f"{item.get('server') or 'mcp'}.{item.get('tool') or 'ferramenta'}"
            arguments = item.get("arguments") if isinstance(item.get("arguments"), dict) else {}
            error = (item.get("error") or {}).get("message") if isinstance(item.get("error"), dict) else None
            result = item.get("result")
            output = error or (json.dumps(result.get("content"), ensure_ascii=False, default=str)
                               if isinstance(result, dict) else "")
            self._tool(phase, item_id, name, arguments, item.get("status") == "completed" and not error, output)
        elif kind == "web_search":
            self._tool(phase, item_id, "WebSearch", {"query": str(item.get("query") or "")}, True, "")
        elif kind == "todo_list":
            if phase in ("started", "completed"):
                steps = [f"{'☑' if t.get('completed') else '☐'} {t.get('text', '')}"
                         for t in item.get("items") or [] if isinstance(t, dict)]
                if steps:
                    self._out({"type": "notice", "message": "Plano: " + " · ".join(steps)})
        elif kind == "error":
            if phase == "completed" and item.get("message"):
                self._out({"type": "notice", "message": f"Codex: {item['message']}"})

    def handle_line(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        try:
            event = json.loads(line)
        except ValueError:
            logger.debug("Codex: linha não JSON: %s", line[:200])
            return
        if not isinstance(event, dict):
            return
        kind = event.get("type")
        if kind == "thread.started":
            self.thread_id = _valid_thread(event.get("thread_id")) or self.thread_id
        elif kind == "turn.completed":
            self.completed = True
        elif kind == "turn.failed":
            message = (event.get("error") or {}).get("message") if isinstance(event.get("error"), dict) else None
            self.error = friendly_error(message or self.last_error or "o turno falhou")
        elif kind == "error":
            # Also sent for passing hiccups ("Reconnecting… 1/5"); fatal only with turn.failed.
            self.last_error = str(event.get("message") or "")
        elif kind in ("item.started", "item.updated", "item.completed") and isinstance(event.get("item"), dict):
            self._item(kind.split(".", 1)[1], event["item"])


class CodexBackend:
    def __init__(self, process_factory: Callable[[List[str], str], Any] = _popen,
                 finder: Optional[Callable[[], Optional[List[str]]]] = None):
        self.process_factory = process_factory
        self.finder = finder           # None: find_codex, looked up on each turn
        self.last_error: Optional[str] = None

    @staticmethod
    def _workspace() -> str:
        folder = Path(settings.codex_workspace or Path.home()).expanduser()
        return str(folder if folder.is_dir() else Path.home())

    def _start(self, cmd: List[str], cwd: str, prompt: str, put: Callable[[Any], None]) -> Any:
        """Starts the process; its stdout lines (and the end) arrive through ``put``."""
        process = self.process_factory(cmd, cwd)
        stderr: Deque[str] = deque(maxlen=STDERR_LINES)

        def feed() -> None:
            try:
                process.stdin.write(prompt)
                process.stdin.close()
            except (OSError, ValueError):
                pass
            try:
                for line in process.stderr:
                    stderr.append(line.rstrip())
            except (OSError, ValueError):
                pass

        def pump() -> None:
            code = None
            try:
                for line in process.stdout:
                    put(("line", line))
                code = process.wait()
            except Exception as exc:  # the pipe broke: the turn ends with an error
                logger.debug("Codex: leitura interrompida: %s", exc)
            writer.join(timeout=5)
            put(("end", code, "\n".join(line for line in stderr if line).strip()))

        writer = threading.Thread(target=feed, name="codex-stdin", daemon=True)
        writer.start()
        threading.Thread(target=pump, name="codex-stdout", daemon=True).start()
        return process

    def _save(self, conversation_id: str, content: str, turn: Optional[_CodexTurn]) -> Optional[Dict[str, Any]]:
        try:
            return conversation_store.add_message(
                conversation_id=conversation_id, role="assistant", content=content,
                tool_trace=(turn.tool_trace or None) if turn else None,
                reasoning=(turn.router.thought or None) if turn else None,
                reasoning_seconds=turn.router.seconds if turn else None,
            )
        except Exception as exc:
            logger.error("Failed to save Codex answer: %s", exc)
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
        yield sse_event({"type": "meta", "conversation_id": conversation_id, "backend": "codex"})
        files = list(attachments or [])
        image_paths = [str(chat_attachments.path_of(f)) for f in chat_attachments.images(files)]
        attachments_note = chat_attachments.prompt_note(files, images_inline=bool(image_paths))
        prefix = (self.finder or find_codex)()
        if not prefix:
            self.last_error = INSTALL_HELP
            yield sse_event({"type": "error", "message": INSTALL_HELP})
            content = f"⚠️ {INSTALL_HELP}"
            saved = self._save(conversation_id, content, None)
            yield sse_event({"type": "done", "conversation_id": conversation_id,
                             "message_id": saved["id"] if saved else None, "content": content,
                             "tool_calls": 0, "backend": "codex"})
            return

        workspace = self._workspace()
        resume = _valid_thread(conversation_store.get_codex_thread(conversation_id))
        history = conversation_store.get_messages(conversation_id, limit=HISTORY_MESSAGES + 1)
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        put = lambda item: loop.call_soon_threadsafe(queue.put_nowait, item)  # noqa: E731
        pending: List[Dict[str, Any]] = []
        turn = _CodexTurn(pending.append, deep_thinking, workspace)
        process: Any = None
        finished = False
        try:
            thread_id = resume
            while True:
                prompt = build_prompt(user_message, project_id, personality_id, history,
                                      deep_thinking, resumed=bool(thread_id),
                                      attachments_note=attachments_note)
                cmd = build_command(prefix, workspace, thread_id, settings.codex_model, image_paths)
                code: Optional[int] = None
                stderr = ""
                try:
                    process = self._start(cmd, workspace, prompt, put)
                except OSError as exc:
                    turn.error = friendly_error(exc)
                    break
                while True:
                    item = await queue.get()
                    if item[0] == "line":
                        turn.handle_line(item[1])
                        while pending:
                            yield sse_event(pending.pop(0))
                    else:
                        _, code, stderr = item
                        break
                process = None
                failed = turn.error is not None or (code not in (0, None) and not turn.completed) or code is None
                if thread_id and failed and not turn.got_output:
                    logger.warning("Codex: retomar %s falhou (%s); começando outra sessão",
                                   thread_id, turn.error or stderr or code)
                    turn.reset_for_retry()
                    conversation_store.set_codex_thread(conversation_id, None)
                    thread_id = None
                    yield sse_event({"type": "notice", "message": RESUME_NOTICE})
                    continue
                if turn.error is None and failed:
                    turn.error = friendly_error(turn.last_error or stderr or f"o Codex saiu com o código {code}")
                break

            turn.finish_text()
            while pending:
                yield sse_event(pending.pop(0))

            content = turn.text()
            if turn.error:
                self.last_error = turn.error
                yield sse_event({"type": "error", "message": turn.error})
                content = content or f"⚠️ {turn.error}"
            else:
                self.last_error = None
                if turn.thread_id:
                    conversation_store.set_codex_thread(conversation_id, turn.thread_id)
                if not content.strip():
                    content = THOUGHT_ONLY_NOTE if turn.router.thought else NO_TEXT_FALLBACK
                if settings.tts_enabled and settings.tts_speak_responses:
                    try:
                        from app.voice import tts_engine
                        if tts_engine.available:
                            tts_engine.speak_async(content)
                    except Exception:
                        logger.debug("TTS indisponível", exc_info=True)

            saved = self._save(conversation_id, content, turn)
            finished = True
            done = {
                "type": "done", "conversation_id": conversation_id,
                "message_id": saved["id"] if saved else None, "content": content,
                "tool_calls": len(turn.tool_trace), "backend": "codex",
            }
            if turn.router.thought:
                done["reasoning_seconds"] = turn.router.seconds
            yield sse_event(done)
        except (GeneratorExit, asyncio.CancelledError):
            if not finished:
                if process is not None:
                    try:
                        process.kill()
                    except Exception:
                        pass
                partial = turn.text().strip()
                if partial or turn.router.thought:
                    self._save(conversation_id, partial + CANCELLED_MARKER, turn)
                logger.info("Codex turn cancelled for conversation %s", conversation_id)
            raise


codex_backend = CodexBackend()
