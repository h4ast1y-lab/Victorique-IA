"""Cliente de inferência local via llama.cpp (opcional).

Usa a biblioteca ``llama-cpp-python`` quando instalada. Como ela depende de
compilação C++ e pode não estar disponível em todos os ambientes (especialmente
Python 3.15 recém-lançado), esta classe degrade graciosamente: se a importação
falhar, todos os métodos reportam indisponibilidade e o assistente continua
usando o Ollama como backend padrão.

O Ollama permanece como modelo padrão. O llama.cpp é uma alternativa opcional
para modelos GGUF locais, sem dependência de servidor externo.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional

logger = logging.getLogger("llama_cpp")

try:
    from llama_cpp import Llama  # type: ignore

    _LLAMA_CPP_AVAILABLE = True
    _LLAMA_CPP_IMPORT_ERROR: Optional[str] = None
except Exception as exc:  # pragma: no cover - depends on environment
    _LLAMA_CPP_AVAILABLE = False
    _LLAMA_CPP_IMPORT_ERROR = str(exc)


class LlamaCppClient:
    """Wrapper síncrono/assíncrono sobre llama-cpp-python.

    Mantém uma instância Llama carregada em memória. Não faz download de
    modelos: o usuário deve fornecer o caminho do arquivo .gguf.
    """

    def __init__(self, model_path: Optional[str] = None, n_ctx: int = 4096):
        self._llm = None
        self._model_path: Optional[str] = None
        self._available = False
        self._init_error: Optional[str] = None
        self._n_ctx = n_ctx
        if model_path:
            self.load_model(model_path, n_ctx)

    @property
    def available(self) -> bool:
        return self._available and self._llm is not None

    def status(self) -> dict:
        return {
            "available": self.available,
            "engine": "llama.cpp",
            "model_path": self._model_path,
            "n_ctx": self._n_ctx,
            "error": self._init_error,
        }

    def load_model(self, model_path: str, n_ctx: int = 4096) -> bool:
        """Carrega um modelo GGUF. Retorna True se sucesso."""
        if not _LLAMA_CPP_AVAILABLE:
            self._init_error = (
                f"llama-cpp-python não instalado: {_LLAMA_CPP_IMPORT_ERROR}. "
                "Instale com: pip install llama-cpp-python"
            )
            logger.warning(self._init_error)
            return False
        p = Path(model_path)
        if not p.is_file():
            self._init_error = f"Modelo GGUF não encontrado: {model_path}"
            logger.warning(self._init_error)
            return False
        try:
            self._llm = Llama(model_path=str(p), n_ctx=n_ctx, verbose=False)
            self._model_path = str(p)
            self._n_ctx = n_ctx
            self._available = True
            self._init_error = None
            logger.info(f"Modelo llama.cpp carregado: {p.name} (ctx={n_ctx})")
            return True
        except Exception as exc:  # pragma: no cover - depends on environment
            self._init_error = str(exc)
            logger.error(f"Falha ao carregar modelo llama.cpp: {exc}")
            return False

    def unload(self):
        self._llm = None
        self._available = False
        self._model_path = None

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        num_ctx: Optional[int] = None,
        max_tokens: int = 1024,
        tools: Optional[List[Dict]] = None,  # ignorado por enquanto
        tool_calls_out: Optional[List[Dict]] = None,  # ignorado por enquanto
    ) -> AsyncGenerator[str, None]:
        """Gera resposta por llama.cpp, token a token (simulado via streaming)."""
        if not self.available:
            raise RuntimeError(
                "llama.cpp não disponível. Carregue um modelo GGUF primeiro "
                f"({self._init_error or 'sem modelo carregado'})."
            )

        # Constrói o prompt simples a partir das mensagens.
        prompt_parts: List[str] = []
        if system_prompt:
            prompt_parts.append(f"System: {system_prompt}")
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            prompt_parts.append(f"{role.capitalize()}: {content}")
        prompt_parts.append("Assistant:")
        prompt = "\n".join(prompt_parts)

        n_ctx = num_ctx or self._n_ctx
        try:
            # llama-cpp-python é síncrono; executamos em thread para não
            # bloquear o event loop do FastAPI.
            import asyncio

            loop = asyncio.get_event_loop()

            def _generate():
                full = ""
                for chunk in self._llm(
                    prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=True,
                ):
                    token = chunk.get("choices", [{}])[0].get("text", "")
                    if token:
                        full += token
                        yield token
                return full

            async for token in self._async_generator(_generate(), loop):
                yield token
        except Exception as exc:  # pragma: no cover - depends on environment
            logger.error(f"Erro na inferência llama.cpp: {exc}")
            raise

    async def _async_generator(self, sync_gen, loop):
        """Adapta um gerador síncrono para assíncrono."""
        iterator = iter(sync_gen)
        while True:
            try:
                # Executar next() na thread executor para não bloquear.
                item = await loop.run_in_executor(None, next, iterator)
                yield item
            except StopIteration:
                break

    async def generate_embeddings(
        self, text: str, model: Optional[str] = None
    ) -> List[float]:
        """llama.cpp pode gerar embeddings se o modelo suportar."""
        if not self.available:
            raise RuntimeError("llama.cpp não disponível.")
        try:
            result = self._llm.embed(text)
            return result if isinstance(result, list) else []
        except Exception as exc:  # pragma: no cover
            logger.error(f"Erro ao gerar embeddings via llama.cpp: {exc}")
            return []


llama_cpp_client = LlamaCppClient()
