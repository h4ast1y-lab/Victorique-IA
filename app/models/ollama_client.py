import json
import logging
from typing import AsyncGenerator, Optional, List, Dict, Any
import httpx

from app.config import settings

logger = logging.getLogger("ollama_client")

class OllamaClient:
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.timeout = httpx.Timeout(120.0, connect=10.0)

    async def is_alive(self) -> bool:
        """Verifies if the Ollama service is reachable."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.base_url}/api/version")
                return resp.status_code == 200
        except Exception as e:
            logger.debug(f"Ollama healthcheck failed: {e}")
            return False

    async def get_version(self) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.base_url}/api/version")
                if resp.status_code == 200:
                    return resp.json().get("version")
        except Exception:
            pass
        return None

    async def list_models(self) -> List[Dict[str, Any]]:
        """Returns the list of locally available models."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("models", [])
        except Exception as e:
            logger.error(f"Error listing models: {e}")
        return []

    async def pull_model_stream(self, model_name: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Streams model download progress."""
        url = f"{self.base_url}/api/pull"
        payload = {"name": model_name, "stream": True}
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, json=payload) as response:
                async for line in response.aiter_lines():
                    if line.strip():
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            continue

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        num_ctx: Optional[int] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_calls_out: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Sends a conversation to Ollama and streams the response tokens in real-time.
        Closing this generator closes the HTTP connection, which makes Ollama stop
        generating (best-effort cancellation supported by the local API).

        When `tools` is provided, any tool calls requested by the model are
        appended to `tool_calls_out` (normalized) and are NOT executed here.
        The caller is responsible for validating and running them.
        """
        model = model or settings.default_model
        temperature = temperature if temperature is not None else settings.temperature

        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        formatted_messages.extend(messages)

        options = {
            "temperature": temperature,
            "num_ctx": num_ctx or settings.max_context_tokens,
        }
        if max_tokens:
            options["num_predict"] = max_tokens

        payload = {
            "model": model,
            "messages": formatted_messages,
            "stream": True,
            "options": options,
        }
        if tools:
            payload["tools"] = tools

        url = f"{self.base_url}/api/chat"
        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=15.0)) as client:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    err_body = await response.aread()
                    raise RuntimeError(f"Ollama error ({response.status_code}): {err_body.decode('utf-8', errors='ignore')}")

                async for line in response.aiter_lines():
                    if line.strip():
                        try:
                            data = json.loads(line)
                            if not isinstance(data, dict):
                                continue
                            if data.get("error"):
                                raise RuntimeError(str(data["error"]))
                            msg = data.get("message") or {}
                            if not isinstance(msg, dict):
                                continue
                            content = msg.get("content", "")
                            if content:
                                yield content

                            for raw_call in msg.get("tool_calls") or []:
                                if not isinstance(raw_call, dict):
                                    continue
                                function = raw_call.get("function") or {}
                                name = function.get("name")
                                if not name:
                                    continue
                                arguments = function.get("arguments")
                                if isinstance(arguments, str):
                                    try:
                                        arguments = json.loads(arguments)
                                    except json.JSONDecodeError:
                                        arguments = {"_raw": arguments}
                                if not isinstance(arguments, dict):
                                    arguments = {}
                                if tool_calls_out is not None:
                                    tool_calls_out.append({
                                        "function": {
                                            "name": name,
                                            "arguments": arguments,
                                        }
                                    })

                            if data.get("done", False):
                                break
                        except json.JSONDecodeError:
                            continue

    async def generate_embeddings(self, text: str, model: Optional[str] = None) -> List[float]:
        """
        Generates dense vector embeddings using local Ollama model.
        """
        model = model or settings.embedding_model
        url = f"{self.base_url}/api/embeddings"
        payload = {"model": model, "prompt": text}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("embedding", [])
            else:
                raise RuntimeError(f"Failed to generate embeddings: {resp.text}")

ollama_client = OllamaClient()
