"""Cliente para o servidor llama.cpp (llama-server.exe).

Gerencia o ciclo de vida do processo ``llama-server.exe`` (iniciar/parar) e se
comunica com ele via HTTP usando a API compatível com OpenAI
(``/v1/chat/completions``, ``/v1/models``).

O servidor roda localmente (127.0.0.1) e não faz chamadas externas. O modelo
GGUF ja esta presente em C:\\Users\\Usuário\\llama.cpp\\models\\, entao nao ha
download de modelo.

Quando a biblioteca ``llama-cpp-python`` nao esta instalada (sem wheel para
Python 3.15 neste ambiente), este cliente e a alternativa viavel: usa o
executavel ``llama-server.exe`` ja compilado em C:\\Users\\Usuário\\llama.cpp\\.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

import httpx

from app.config import DATA_DIR
from app.models.events import ReasoningDelta

logger = logging.getLogger("llama_cpp_server")

# Caminho padrão da instalação local do llama.cpp.
DEFAULT_LLAMA_CPP_DIR = Path(
    os.environ.get("LLAMA_CPP_DIR", r"C:\Users\Usuário\llama.cpp")
)
DEFAULT_SERVER_EXE = DEFAULT_LLAMA_CPP_DIR / "llama-server.exe"
DEFAULT_MODEL_PATH = (
    DEFAULT_LLAMA_CPP_DIR / "models" / "Qwen_Qwen3.5-9B-IQ4_XS.gguf"
)
DEFAULT_PORT = int(os.environ.get("LLAMA_CPP_PORT", "8899"))
DEFAULT_HOST = os.environ.get("LLAMA_CPP_HOST", "127.0.0.1")
DEFAULT_N_CTX = int(os.environ.get("LLAMA_CPP_N_CTX", "4096"))
DEFAULT_N_GPU_LAYERS = int(os.environ.get("LLAMA_CPP_N_GPU_LAYERS", "33"))


def to_openai_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Converte o histórico interno (formato do Ollama: ``arguments`` como dict,
    mensagens ``tool`` com ``tool_name``) para o formato OpenAI exigido pelo
    llama-server (``arguments`` como string JSON e ``tool_call_id``).
    """
    converted: List[Dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        if role == "assistant" and msg.get("tool_calls"):
            calls = []
            for i, call in enumerate(msg["tool_calls"]):
                function = call.get("function") or {}
                arguments = function.get("arguments")
                if not isinstance(arguments, str):
                    arguments = json.dumps(arguments or {}, ensure_ascii=False)
                calls.append({
                    "id": call.get("id") or f"call_{i}",
                    "type": "function",
                    "function": {"name": function.get("name", ""), "arguments": arguments},
                })
            converted.append({
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": calls,
            })
        elif role == "tool":
            converted.append({
                "role": "tool",
                "tool_call_id": msg.get("tool_call_id") or "",
                "content": msg.get("content") or "",
            })
        else:
            converted.append({"role": role, "content": msg.get("content") or ""})
    return converted


def _merge_tool_call_delta(pending: Dict[int, Dict[str, Any]], part: Dict[str, Any]) -> None:
    """Acumula os fragmentos de uma chamada de ferramenta em streaming."""
    index = part.get("index", 0)
    slot = pending.setdefault(index, {"id": None, "name": "", "arguments": ""})
    if part.get("id"):
        slot["id"] = part["id"]
    function = part.get("function") or {}
    if function.get("name"):
        slot["name"] += function["name"]
    if function.get("arguments"):
        slot["arguments"] += function["arguments"]


def _finish_tool_call(slot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not slot.get("name"):
        return None
    raw = slot.get("arguments") or "{}"
    try:
        arguments = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Argumentos de ferramenta inválidos do llama-server: %r", raw[:200])
        arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}
    call: Dict[str, Any] = {"function": {"name": slot["name"], "arguments": arguments}}
    if slot.get("id"):
        call = {"id": slot["id"], **call}
    return call


class LlamaCppServerClient:
    """Wrapper sobre o llama-server.exe gerenciado como subprocesso local.

    O cliente inicia o servidor sob demanda, aguarda ficar saudável e faz
    streaming de respostas via HTTP. Não confia na biblioteca Python
    ``llama-cpp-python`` (que pode não compilar neste ambiente).
    """

    def __init__(
        self,
        server_exe: Optional[str | Path] = None,
        model_path: Optional[str | Path] = None,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        n_ctx: int = DEFAULT_N_CTX,
        n_gpu_layers: int = DEFAULT_N_GPU_LAYERS,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        log_path: Optional[str | Path] = None,
    ):
        # Optional transport for tests (httpx.MockTransport).
        self._transport = transport
        # The server's stdout/stderr go here, so a failed start can be diagnosed.
        self.log_path = Path(log_path) if log_path else None
        self._log_file = None
        # Serializes starts: concurrent callers wait instead of spawning a
        # second process on the same port.
        self._start_lock = threading.Lock()
        self._starting = False
        self.server_exe = Path(server_exe or DEFAULT_SERVER_EXE)
        self.model_path = Path(model_path or DEFAULT_MODEL_PATH)
        self.host = host
        self.port = port
        self.n_ctx = n_ctx
        self.n_gpu_layers = n_gpu_layers
        self._proc: Optional[subprocess.Popen] = None
        self._base_url = f"http://{host}:{port}"
        self._available = False
        self._init_error: Optional[str] = None

    @property
    def available(self) -> bool:
        return self._available

    @property
    def base_url(self) -> str:
        return self._base_url

    def status(self) -> dict:
        return {
            "available": self.available,
            "engine": "llama.cpp-server",
            "server_exe": str(self.server_exe),
            "server_exe_exists": self.server_exe.is_file(),
            "model_path": str(self.model_path),
            "model_exists": self.model_path.is_file(),
            "host": self.host,
            "port": self.port,
            "n_ctx": self.n_ctx,
            "n_gpu_layers": self.n_gpu_layers,
            "error": self._init_error,
            "base_url": self._base_url,
            "starting": self._starting,
            "log_path": str(self.log_path) if self.log_path else None,
        }

    # ------------------------------------------------------------------
    # Process lifecycle
    # ------------------------------------------------------------------

    def is_alive(self) -> bool:
        """Verifica se o servidor já está respondendo na porta."""
        try:
            r = httpx.get(f"{self._base_url}/v1/models", timeout=2.0)
            return r.status_code == 200
        except Exception:
            return False

    def build_args(self) -> List[str]:
        """Linha de comando do llama-server.

        ``--jinja`` ativa o template de chat do modelo, necessário para
        chamadas de ferramenta nativas (campo ``tools`` / ``tool_calls``).
        """
        return [
            str(self.server_exe),
            "-m", str(self.model_path),
            "--host", self.host,
            "--port", str(self.port),
            "--ctx-size", str(self.n_ctx),
            "-ngl", str(self.n_gpu_layers),
            "--jinja",
        ]

    def start_in_background(self, wait_seconds: int = 180) -> None:
        """Inicia o servidor numa thread, sem bloquear quem chamou."""
        if self._available or self._starting:
            return
        self._starting = True
        threading.Thread(
            target=self.start, args=(wait_seconds,), daemon=True, name="llama-server-start"
        ).start()

    def start(self, wait_seconds: int = 120) -> bool:
        """Inicia o llama-server.exe se ainda não estiver vivo.

        Bloqueante: aguarda até ``wait_seconds`` segundos pelo servidor ficar
        saudável. Em código async, chame via ``asyncio.to_thread``. Chamadas
        simultâneas esperam a que já está em andamento.
        Retorna True se o servidor estiver disponível ao final.
        """
        with self._start_lock:
            self._starting = True
            try:
                return self._start_locked(wait_seconds)
            finally:
                self._starting = False

    def _open_log(self):
        if not self.log_path:
            return subprocess.DEVNULL
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log_file = open(self.log_path, "ab")
            return self._log_file
        except OSError as exc:
            logger.warning("Não foi possível abrir o log do llama-server: %s", exc)
            return subprocess.DEVNULL

    def _close_log(self):
        if self._log_file is not None:
            try:
                self._log_file.close()
            except OSError:
                pass
            self._log_file = None

    def _start_locked(self, wait_seconds: int) -> bool:
        if self.is_alive():
            self._available = True
            self._init_error = None
            logger.info("llama-server já está rodando em %s", self._base_url)
            return True

        if not self.server_exe.is_file():
            self._init_error = f"llama-server.exe não encontrado: {self.server_exe}"
            logger.error(self._init_error)
            return False

        if not self.model_path.is_file():
            self._init_error = f"Modelo GGUF não encontrado: {self.model_path}"
            logger.error(self._init_error)
            return False

        args = self.build_args()
        logger.info("Iniciando llama-server: %s", " ".join(args))

        log = self._open_log()
        try:
            self._proc = subprocess.Popen(
                args,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except Exception as exc:
            self._close_log()
            self._init_error = f"Falha ao iniciar llama-server: {exc}"
            logger.error(self._init_error)
            return False

        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            if self._proc.poll() is not None:
                # Processo encerrou antes de ficar saudável.
                self._init_error = (
                    f"llama-server encerrou inesperadamente (código {self._proc.returncode})"
                    + (f"; veja {self.log_path}" if self.log_path else "")
                )
                logger.error(self._init_error)
                self._proc = None
                self._close_log()
                return False
            if self.is_alive():
                self._available = True
                self._init_error = None
                logger.info(
                    "llama-server saudável em %s após %.1fs",
                    self._base_url,
                    time.time() - (deadline - wait_seconds),
                )
                return True
            time.sleep(1.0)

        self._init_error = (
            f"llama-server não ficou saudável em {wait_seconds}s em {self._base_url}"
        )
        logger.error(self._init_error)
        self.stop()
        return False

    def stop(self):
        """Para o servidor llama-server se foi iniciado por este cliente."""
        if self._proc is not None:
            try:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            except Exception as exc:  # pragma: no cover - best effort
                logger.warning("Erro ao parar llama-server: %s", exc)
            self._proc = None
        self._close_log()
        self._available = False

    # ------------------------------------------------------------------
    # HTTP API
    # ------------------------------------------------------------------

    async def list_models(self) -> List[Dict]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{self._base_url}/v1/models")
                if r.status_code == 200:
                    return r.json().get("data", [])
        except Exception as exc:  # pragma: no cover - network
            logger.debug("list_models falhou: %s", exc)
        return []

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        num_ctx: Optional[int] = None,
        max_tokens: int = 1024,
        tools: Optional[List[Dict]] = None,
        tool_calls_out: Optional[List[Dict]] = None,
    ) -> AsyncGenerator[Union[str, ReasoningDelta], None]:
        """Streaming de chat via llama-server (API compatível com OpenAI).

        Emite ``str`` para o texto da resposta e ``ReasoningDelta`` para o
        raciocínio interno (``reasoning_content``), que o chamador não deve
        misturar à resposta. Chamadas de ferramenta nativas são acumuladas e
        anexadas a ``tool_calls_out`` no formato interno
        ``{"id", "function": {"name", "arguments": dict}}``.
        """
        if not self.available:
            raise RuntimeError(
                "llama.cpp-server não disponível. Inicie com start() primeiro. "
                f"({self._init_error or 'sem servidor'})"
            )

        formatted: List[Dict[str, Any]] = []
        if system_prompt:
            formatted.append({"role": "system", "content": system_prompt})
        formatted.extend(to_openai_messages(messages))

        payload: Dict[str, Any] = {
            "model": model or str(self.model_path),
            "messages": formatted,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        pending_calls: Dict[int, Dict[str, Any]] = {}

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(600.0, connect=15.0),
            transport=self._transport,
        ) as client:
            async with client.stream(
                "POST", f"{self._base_url}/v1/chat/completions", json=payload
            ) as response:
                if response.status_code != 200:
                    err_body = await response.aread()
                    raise RuntimeError(
                        f"llama-server error ({response.status_code}): "
                        f"{err_body.decode('utf-8', errors='ignore')}"
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or [{}]
                    delta = choices[0].get("delta") or {}

                    reasoning = delta.get("reasoning_content")
                    if reasoning:
                        yield ReasoningDelta(reasoning)
                    content = delta.get("content")
                    if content:
                        yield content
                    for part in delta.get("tool_calls") or []:
                        _merge_tool_call_delta(pending_calls, part)

        if tool_calls_out is not None:
            for index in sorted(pending_calls):
                call = _finish_tool_call(pending_calls[index])
                if call:
                    tool_calls_out.append(call)

    async def generate_embeddings(
        self, text: str, model: Optional[str] = None
    ) -> List[float]:
        """llama-server pode não expor embeddings; retorna lista vazia se não suportar."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    f"{self._base_url}/v1/embeddings",
                    json={"model": model or str(self.model_path), "input": text},
                )
                if r.status_code == 200:
                    data = r.json()
                    embs = data.get("data", [])
                    if embs:
                        return embs[0].get("embedding", [])
        except Exception as exc:  # pragma: no cover - network
            logger.debug("embeddings não suportado pelo llama-server: %s", exc)
        return []


# Instância global (configurada via variáveis de ambiente se presentes).
llama_cpp_server = LlamaCppServerClient(
    server_exe=os.environ.get("LLAMA_CPP_SERVER_EXE"),
    model_path=os.environ.get("LLAMA_CPP_MODEL_PATH"),
    host=os.environ.get("LLAMA_CPP_HOST", DEFAULT_HOST),
    port=int(os.environ.get("LLAMA_CPP_PORT", str(DEFAULT_PORT))),
    n_ctx=int(os.environ.get("LLAMA_CPP_N_CTX", str(DEFAULT_N_CTX))),
    n_gpu_layers=int(os.environ.get("LLAMA_CPP_N_GPU_LAYERS", str(DEFAULT_N_GPU_LAYERS))),
    log_path=DATA_DIR / "llama-server.log",
)
