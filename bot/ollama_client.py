from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Iterator

import requests


class OllamaConnectionError(RuntimeError):
    """Raised when the local Ollama service cannot be reached."""


class OllamaResponseError(RuntimeError):
    """Raised when Ollama returns an unexpected response."""


@dataclass(frozen=True)
class ChatResult:
    """Assistant reply plus Ollama timing metrics."""

    content: str
    output_tokens: int | None
    prompt_tokens: int | None
    total_duration_seconds: float | None
    load_duration_seconds: float | None
    prompt_eval_duration_seconds: float | None
    eval_duration_seconds: float | None
    tokens_per_second: float | None


def _nanoseconds_to_seconds(value: Any) -> float | None:
    """Convert Ollama nanosecond duration fields into seconds."""
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    return float(value) / 1_000_000_000


def _chat_result_from_data(content: str, data: dict[str, Any]) -> ChatResult:
    """Build ChatResult from an Ollama response object."""
    output_tokens = data.get("eval_count")
    prompt_tokens = data.get("prompt_eval_count")
    eval_duration_seconds = _nanoseconds_to_seconds(data.get("eval_duration"))

    tokens_per_second = None
    if isinstance(output_tokens, int) and eval_duration_seconds:
        tokens_per_second = output_tokens / eval_duration_seconds

    return ChatResult(
        content=content.strip(),
        output_tokens=output_tokens if isinstance(output_tokens, int) else None,
        prompt_tokens=prompt_tokens if isinstance(prompt_tokens, int) else None,
        total_duration_seconds=_nanoseconds_to_seconds(data.get("total_duration")),
        load_duration_seconds=_nanoseconds_to_seconds(data.get("load_duration")),
        prompt_eval_duration_seconds=_nanoseconds_to_seconds(
            data.get("prompt_eval_duration")
        ),
        eval_duration_seconds=eval_duration_seconds,
        tokens_per_second=tokens_per_second,
    )


class OllamaClient:
    """Small wrapper around Ollama's /api/chat endpoint."""

    def __init__(self, base_url: str, model: str, timeout: int = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def _chat_url(self) -> str:
        """Return the chat endpoint, accepting either base URL or /api/chat URL."""
        if self.base_url.endswith("/api/chat"):
            return self.base_url
        return f"{self.base_url}/api/chat"

    def _tags_url(self) -> str:
        """Return the tags endpoint from either base URL or /api/chat URL."""
        if self.base_url.endswith("/api/chat"):
            root_url = self.base_url.removesuffix("/api/chat")
            return f"{root_url}/api/tags"
        return f"{self.base_url}/api/tags"

    def set_base_url(self, base_url: str) -> None:
        """Switch the Ollama URL used by later requests."""
        self.base_url = base_url.rstrip("/")

    def set_model(self, model: str) -> None:
        """Switch the model used by later chat requests."""
        self.model = model

    def list_models(self) -> list[str]:
        """Return model names installed in local Ollama."""
        url = self._tags_url()

        try:
            response = requests.get(url, timeout=self.timeout)
        except requests.exceptions.ConnectionError as exc:
            raise OllamaConnectionError("无法连接到 Ollama。") from exc
        except requests.exceptions.Timeout as exc:
            raise OllamaConnectionError("请求 Ollama 超时。") from exc

        if response.status_code != 200:
            raise OllamaResponseError(
                f"HTTP {response.status_code}: {response.text[:500]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise OllamaResponseError("Ollama 返回的不是合法 JSON。") from exc

        models = data.get("models", [])
        if not isinstance(models, list):
            return []

        names: list[str] = []
        for item in models:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if isinstance(name, str) and name:
                names.append(name)

        return names

    def chat(self, messages: list[dict[str, str]]) -> ChatResult:
        """Send chat messages to Ollama and return text plus speed metrics."""
        url = self._chat_url()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": "30m",
        }

        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
        except requests.exceptions.ConnectionError as exc:
            raise OllamaConnectionError("无法连接到 Ollama。") from exc
        except requests.exceptions.Timeout as exc:
            raise OllamaConnectionError("请求 Ollama 超时。") from exc

        if response.status_code != 200:
            raise OllamaResponseError(
                f"HTTP {response.status_code}: {response.text[:500]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise OllamaResponseError("Ollama 返回的不是合法 JSON。") from exc

        message = data.get("message")
        if not isinstance(message, dict):
            raise OllamaResponseError("Ollama 响应缺少 message 字段。")

        content = message.get("content")
        if not isinstance(content, str):
            raise OllamaResponseError("Ollama 响应缺少 message.content 字段。")

        return _chat_result_from_data(content, data)

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        should_stop: Callable[[], bool] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Stream chat chunks from Ollama.

        Yields dictionaries:
        - {"type": "content", "content": "..."}
        - {"type": "done", "result": ChatResult, "interrupted": bool}
        """
        url = self._chat_url()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "keep_alive": "30m",
        }

        try:
            response = requests.post(url, json=payload, timeout=self.timeout, stream=True)
        except requests.exceptions.ConnectionError as exc:
            raise OllamaConnectionError("无法连接到 Ollama。") from exc
        except requests.exceptions.Timeout as exc:
            raise OllamaConnectionError("请求 Ollama 超时。") from exc

        if response.status_code != 200:
            raise OllamaResponseError(
                f"HTTP {response.status_code}: {response.text[:500]}"
            )

        chunks: list[str] = []
        final_data: dict[str, Any] = {}
        interrupted = False

        try:
            for line in response.iter_lines(decode_unicode=True):
                if should_stop and should_stop():
                    interrupted = True
                    break

                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise OllamaResponseError("Ollama 流式响应不是合法 JSON。") from exc

                message = data.get("message", {})
                content = message.get("content") if isinstance(message, dict) else None
                if isinstance(content, str) and content:
                    chunks.append(content)
                    yield {"type": "content", "content": content}

                if data.get("done"):
                    final_data = data
                    break
        finally:
            response.close()

        result = _chat_result_from_data("".join(chunks), final_data)
        yield {"type": "done", "result": result, "interrupted": interrupted}
