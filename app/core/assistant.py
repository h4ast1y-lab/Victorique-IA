import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, Any, Optional, List

from app.memory.conversation_store import conversation_store
from app.core.context_builder import context_builder
from app.models.ollama_client import ollama_client
from app.models.llama_cpp_client import llama_cpp_client
from app.models.llama_cpp_server_client import llama_cpp_server
from app.tools.registry import tool_registry
from app.config import settings, DEFAULT_LLAMA_CPP_MODEL
from app.voice import tts_engine
from app.models.events import ReasoningDelta
from app.core.sse import CANCELLED_MARKER, NO_TEXT_FALLBACK, sse_event, truncate

logger = logging.getLogger("assistant")

TOOL_TRACE_RESULT_CHARS = 1500
_event = sse_event
_truncate = truncate


def _tools_unsupported(exc: Exception) -> bool:
    message = str(exc).lower()
    return "support tools" in message or "does not support tool" in message


def _unwrap_code_fence(text: str) -> str:
    """
    Models sometimes wrap ordinary prose in a ``` block (with the text either
    on its own line or right after the backticks). That renders as a code
    block, so the fence is removed. Non-fenced text is returned unchanged.
    """
    raw = (text or "").strip()
    if not raw.startswith("```"):
        return text
    body = raw[3:]
    if body.startswith("\n"):
        inner = body[1:]
    else:
        first_line, _, rest = body.partition("\n")
        # "```json\n..." / "```python\n..." — a short single token is a
        # language tag, not content.
        if first_line and " " not in first_line and len(first_line) <= 15 \
                and all(c.isalnum() or c in "_+-" for c in first_line):
            inner = rest
        else:
            inner = body
    inner = inner.rstrip()
    if inner.endswith("```"):
        inner = inner[:-3]
    inner = inner.strip()
    return inner if inner else text


def _fenced_prose_ready(text: str) -> bool:
    """
    True once a fenced block is clearly prose (its body does not start with a
    JSON object), so it can be shown instead of being buffered indefinitely.
    """
    stripped = (text or "").lstrip()
    if not stripped.startswith("```"):
        return False
    lines = stripped.splitlines()
    if len(lines) < 2:
        return False
    body = "\n".join(lines[1:]).lstrip()
    if not body:
        return False
    if body.startswith("{"):
        return False
    return len(body) >= 64 or stripped.rstrip().endswith("```")


def _parse_text_tool_call(text: str) -> Optional[Dict[str, Any]]:
    """
    Some local models (notably qwen2.5-coder) answer a tool request with a raw
    JSON object instead of using Ollama's native tool_calls field. This parser
    accepts only a pure JSON object naming a registered tool.
    """
    raw = (text or "").strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines:
            raw = "\n".join(lines[1:])
        raw = raw.strip()
        if raw.endswith("```"):
            raw = raw[:-3].strip()
    if not (raw.startswith("{") and raw.endswith("}")):
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None

    function = obj.get("function") if isinstance(obj.get("function"), dict) else {}
    name = obj.get("name") or obj.get("tool") or function.get("name")
    arguments = (
        obj.get("arguments")
        if obj.get("arguments") is not None
        else obj.get("parameters")
    )
    if arguments is None:
        arguments = function.get("arguments")

    if not isinstance(name, str) or name not in tool_registry.tools:
        return None
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return None
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return None

    allowed_keys = {"name", "arguments", "tool", "parameters", "function", "type", "id"}
    if not set(obj.keys()).issubset(allowed_keys):
        return None
    if obj.get("type") not in (None, "function"):
        return None
    if obj.get("id") is not None and not isinstance(obj.get("id"), str):
        return None
    return {"function": {"name": name, "arguments": arguments}}


class AssistantEngine:
    def _save_assistant_message(
        self,
        conversation_id: str,
        content: str,
        sources: Optional[list],
        tool_trace: Optional[list] = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            return conversation_store.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=content,
                sources=sources or None,
                tool_trace=tool_trace or None,
            )
        except Exception as e:
            logger.error(f"Failed to save assistant message: {e}")
            return None

    async def _stream_model_round(
        self,
        state: Dict[str, Any],
        **chat_kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """
        Streams one model round. While the output looks like a raw JSON tool
        call, tokens are buffered instead of being shown to the user. If the
        buffer turns out to be ordinary text, it is flushed unchanged.
        """
        backend_name = state.get("backend_name", "ollama")
        # "llama-cpp" (biblioteca Python) pode nao estar instalada; nesse caso
        # usamos o servidor HTTP (llama-cpp-server) como fallback.
        if backend_name == "llama-cpp" and not llama_cpp_client.available:
            client = llama_cpp_server
        elif backend_name == "llama-cpp":
            client = llama_cpp_client
        elif backend_name == "llama-cpp-server":
            client = llama_cpp_server
        else:
            client = ollama_client
        async for token in client.chat_stream(
            tool_calls_out=state["calls"],
            **chat_kwargs,
        ):
            if isinstance(token, ReasoningDelta):
                # Internal reasoning never joins the answer text or the
                # tool-call buffer; the caller emits it as its own event.
                yield token
                continue
            if not state["buffering"]:
                if state.get("strip_fence"):
                    if "```" in token:
                        token = token.replace("```", "")
                        state["strip_fence"] = False
                    if not token:
                        continue
                state["text"].append(token)
                yield token
                continue

            state["prefix"] += token
            stripped = state["prefix"].lstrip()
            looks_like_json = stripped.startswith("{") or stripped.startswith("```")

            if not looks_like_json:
                # Backticks can arrive one at a time ("`", "``", "```"). While
                # the buffer could still become a code fence, keep waiting.
                if stripped and len(stripped) < 3 and "```".startswith(stripped):
                    continue
                state["buffering"] = False
                chunk = state["prefix"]
                state["prefix"] = ""
                state["text"].append(chunk)
                yield chunk
                continue

            parsed = _parse_text_tool_call(state["prefix"])
            if parsed:
                state["buffering"] = False
                state["prefix"] = ""
                state["calls"].append(parsed)
            elif _fenced_prose_ready(state["prefix"]):
                # A fenced block that is prose, not a tool call: show it now
                # without the fence instead of withholding the whole answer.
                state["buffering"] = False
                state["strip_fence"] = not state["prefix"].rstrip().endswith("```")
                chunk = _unwrap_code_fence(state["prefix"])
                state["prefix"] = ""
                state["text"].append(chunk)
                yield chunk
            elif len(state["prefix"]) > 4000:
                # Not a tool call; avoid withholding a long normal answer.
                state["buffering"] = False
                chunk = _unwrap_code_fence(state["prefix"])
                state["prefix"] = ""
                state["text"].append(chunk)
                yield chunk

        if state["buffering"] and state["prefix"]:
            parsed = _parse_text_tool_call(state["prefix"])
            state["buffering"] = False
            if parsed:
                state["calls"].append(parsed)
            else:
                chunk = _unwrap_code_fence(state["prefix"])
                state["prefix"] = ""
                state["text"].append(chunk)
                yield chunk

    async def chat_stream(
        self,
        conversation_id: str,
        user_message: str,
        model: Optional[str] = None,
        backend: Optional[str] = None,
        project_id: Optional[str] = None,
        personality_id: Optional[str] = None,
        enable_rag: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        Orchestrates one conversation turn and yields SSE JSON events:
        - {"type": "meta", "conversation_id": "...", "model": "..."}
        - {"type": "sources", "data": [...]}
        - {"type": "token", "content": "..."}
        - {"type": "tool_call", "tool": "...", "arguments": {...}}
        - {"type": "tool_result", "tool": "...", "status": "...", "result": {...}}
        - {"type": "authorization_required", "action_id": "...", ...}
        - {"type": "notice", "message": "..."}
        - {"type": "error", "message": "..."} (also emitted as token for compatibility)
        - {"type": "done", "conversation_id": "...", "message_id": "...", "content": "..."}

        Tool calling: FREE tools run automatically. Protected/external tools
        create a server-side pending authorization and the turn stops; nothing
        protected runs before the user approves it.

        If the client disconnects, the underlying Ollama stream is closed and
        the partial answer is persisted with an explicit cancellation marker.
        """
        # Save user message immediately
        conversation_store.add_message(
            conversation_id=conversation_id,
            role="user",
            content=user_message
        )

        # Seleciona o backend de inferência:
        #   "ollama" -> servidor Ollama (HTTP)
        #   "llama-cpp" -> biblioteca llama-cpp-python (se instalada)
        #   "llama-cpp-server" -> servidor llama-server.exe (subprocesso local)
        backend_name = (backend or settings.default_backend or "ollama").strip().lower()
        use_llama_cpp_server = backend_name in ("llama-cpp", "llama-cpp-server")
        use_llama_cpp_lib = backend_name == "llama-cpp" and llama_cpp_client.available

        selected_model = model or settings.default_model
        # Quando o backend é llama-cpp-server, o modelo deve ser o caminho
        # do GGUF (ou o nome registrado no servidor), não o nome do Ollama.
        if backend_name in ("llama-cpp", "llama-cpp-server"):
            selected_model = settings.llama_cpp_model_path or str(
                DEFAULT_LLAMA_CPP_MODEL if 'DEFAULT_LLAMA_CPP_MODEL' in dir() else ""
            )

        if use_llama_cpp_server and not llama_cpp_server.available:
            # Se o backend nao foi explicitamente escolhido pelo usuario,
            # cai de volta para o Ollama em vez de falhar.
            if backend is None:
                backend_name = "ollama"
                use_llama_cpp_server = False
                use_llama_cpp_lib = False
                selected_model = model or settings.default_model
                logger.warning(
                    "llama-cpp-server nao disponível; usando Ollama como fallback"
                )
            else:
                # Tenta auto-start se o backend padrão for llama-cpp.
                # Bloqueante: roda numa thread para não travar o event loop.
                # Se já houver um start em andamento, espera por ele.
                yield _event({
                    "type": "notice",
                    "message": "Carregando o modelo local (llama.cpp); isso pode levar alguns minutos.",
                })
                await asyncio.to_thread(llama_cpp_server.start, 120)
                if not llama_cpp_server.available:
                    yield _event({
                        "type": "error",
                        "message": (
                            "llama.cpp-server não está disponível. Inicie com "
                            "POST /api/llama-cpp-server/start ou use o backend Ollama."
                        ),
                    })
                    yield _event({
                        "type": "done",
                        "conversation_id": conversation_id,
                        "message_id": None,
                        "content": "",
                        "tool_calls": 0,
                    })
                    return

        full_response_parts: List[str] = []
        sources: list = []
        saved_id: Optional[str] = None
        finished = False
        tool_calls_count = 0
        pending_action_id: Optional[str] = None
        tool_trace: List[Dict[str, Any]] = []

        try:
            yield _event({
                "type": "meta",
                "conversation_id": conversation_id,
                "model": selected_model,
                "backend": backend_name,
            })

            history = conversation_store.get_messages(conversation_id)

            ctx = await context_builder.build_context(
                user_query=user_message,
                conversation_history=history,
                project_id=project_id,
                personality_id=personality_id,
                enable_rag=enable_rag
            )

            sources = ctx["sources"]
            if sources:
                yield _event({"type": "sources", "data": sources})

            working_messages: List[Dict[str, Any]] = list(ctx["messages"])
            tools_enabled = bool(settings.tool_calling_enabled)
            tool_schemas = tool_registry.get_ollama_tools() if tools_enabled else None
            seen_calls: set = set()
            max_rounds = max(0, int(settings.max_tool_rounds))
            max_calls = max(1, int(settings.max_tool_calls_per_round))

            for round_index in range(max_rounds + 1):
                state: Dict[str, Any] = {
                    "buffering": bool(tools_enabled),
                    "prefix": "",
                    "text": [],
                    "calls": [],
                    "strip_fence": False,
                    "use_llama_cpp": use_llama_cpp_server or use_llama_cpp_lib,
                    "backend_name": backend_name,
                }

                try:
                    async for token in self._stream_model_round(
                        state,
                        messages=working_messages,
                        model=selected_model,
                        system_prompt=ctx["system_prompt"],
                        max_tokens=settings.max_output_tokens,
                        tools=tool_schemas if tools_enabled else None,
                    ):
                        if isinstance(token, ReasoningDelta):
                            yield _event({"type": "reasoning", "content": token.text})
                            continue
                        full_response_parts.append(token)
                        yield _event({"type": "token", "content": token})
                except RuntimeError as exc:
                    # Some local models do not support the tools API. Fall back
                    # to plain chat instead of failing the whole turn.
                    if tools_enabled and _tools_unsupported(exc):
                        tools_enabled = False
                        tool_schemas = None
                        notice = (
                            "O modelo selecionado não suporta tool calling nesta "
                            "versão do Ollama. A resposta continuará sem execução "
                            "automática de ferramentas."
                        )
                        yield _event({"type": "notice", "message": notice})
                        state = {
                            "buffering": False,
                            "prefix": "",
                            "text": [],
                            "calls": [],
                            "strip_fence": False,
                            "use_llama_cpp": False,
                            "backend_name": "ollama",
                        }
                        async for token in self._stream_model_round(
                            state,
                            messages=working_messages,
                            model=selected_model,
                            system_prompt=ctx["system_prompt"],
                            max_tokens=settings.max_output_tokens,
                            tools=None,
                        ):
                            if isinstance(token, ReasoningDelta):
                                yield _event({"type": "reasoning", "content": token.text})
                                continue
                            full_response_parts.append(token)
                            yield _event({"type": "token", "content": token})
                    else:
                        raise

                tool_calls = state["calls"]
                if not tool_calls:
                    break

                if round_index >= max_rounds:
                    note = (
                        "\n\n_[Limite de rodadas de ferramentas atingido. "
                        "Pergunte novamente se precisar de mais uma ação.]_"
                    )
                    full_response_parts.append(note)
                    yield _event({"type": "notice", "message": note.strip("_ \n")})
                    break

                selected_calls = tool_calls[:max_calls]
                for call_index, call in enumerate(selected_calls):
                    # Ids link each tool result to its call (OpenAI format).
                    call.setdefault("id", f"call_{round_index}_{call_index}")
                working_messages.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": selected_calls,
                })

                stop_after_authorization = False
                for call in selected_calls:
                    function = call.get("function") or {}
                    name = str(function.get("name") or "")
                    arguments = function.get("arguments") or {}
                    if not isinstance(arguments, dict):
                        arguments = {}

                    yield _event({
                        "type": "tool_call",
                        "tool": name,
                        "arguments": arguments,
                    })

                    call_key = (
                        name,
                        json.dumps(arguments, sort_keys=True, ensure_ascii=False),
                    )
                    if call_key in seen_calls:
                        result = {
                            "status": "error",
                            "error": "Chamada repetida idêntica ignorada para evitar loop.",
                        }
                    else:
                        seen_calls.add(call_key)
                        tool_calls_count += 1
                        result = await tool_registry.execute_tool(
                            name=name,
                            params=arguments,
                            context={"conversation_id": conversation_id},
                        )

                    tool_trace.append({
                        "tool": name,
                        "arguments": arguments,
                        "status": result.get("status", "unknown"),
                        "result": _truncate(
                            json.dumps(result.get("result", result.get("error")),
                                       ensure_ascii=False, default=str),
                            TOOL_TRACE_RESULT_CHARS,
                        ),
                    })

                    if result.get("status") == "requires_authorization":
                        pending_action_id = result.get("action_id")
                        note = (
                            f"\n\nPreciso da sua autorização para executar "
                            f"`{name}` em `{result.get('resource', '')}`. "
                            "Nada foi executado ainda. Use a barra de autorização "
                            "para aprovar ou recusar."
                        )
                        full_response_parts.append(note)
                        yield _event({"type": "token", "content": note})
                        yield _event({
                            "type": "authorization_required",
                            **result,
                        })
                        stop_after_authorization = True
                        break

                    result_text = json.dumps(result, ensure_ascii=False, default=str)
                    yield _event({
                        "type": "tool_result",
                        "tool": name,
                        "status": result.get("status", "unknown"),
                        "result": result,
                    })
                    working_messages.append({
                        "role": "tool",
                        "tool_name": name,
                        "tool_call_id": call["id"],
                        "content": _truncate(
                            result_text,
                            max(500, int(settings.tool_result_max_chars)),
                        ),
                    })

                if stop_after_authorization:
                    break

            full_content = "".join(full_response_parts)
            if not full_content.strip():
                full_content = NO_TEXT_FALLBACK

            # Fala a resposta automaticamente se o TTS estiver habilitado.
            if settings.tts_enabled and settings.tts_speak_responses and tts_engine.available:
                tts_engine.speak_async(full_content)

            saved = self._save_assistant_message(
                conversation_id, full_content, sources, tool_trace
            )
            saved_id = saved["id"] if saved else None
            finished = True

            done_payload: Dict[str, Any] = {
                "type": "done",
                "conversation_id": conversation_id,
                "message_id": saved_id,
                "content": full_content,
                "tool_calls": tool_calls_count,
            }
            if pending_action_id:
                done_payload["pending_action_id"] = pending_action_id
            yield _event(done_payload)

        except (GeneratorExit, asyncio.CancelledError):
            # Client disconnected / generation aborted. Persist partial content.
            partial = "".join(full_response_parts).strip()
            if not finished and partial:
                self._save_assistant_message(
                    conversation_id,
                    partial + CANCELLED_MARKER,
                    sources,
                    tool_trace,
                )
            logger.info(f"Generation cancelled for conversation {conversation_id}")
            raise


assistant_engine = AssistantEngine()
