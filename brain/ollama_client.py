"""
Ollama API client with tool calling support.

Pi 4B defaults are applied when no explicit options are passed:
  num_thread=4, num_ctx=2048, num_predict=256, num_batch=128
These keep RAM within the ~3 GB headroom available on a 4 GB Pi 4B.
"""

import httpx
import json
from typing import Optional, Dict, Any, List, Generator
from dataclasses import dataclass


@dataclass
class ToolCall:
    """Represents a tool call from the model."""
    name: str
    arguments: Dict[str, Any]


@dataclass
class ChatResponse:
    """Response from chat completion."""
    content: Optional[str]
    tool_calls: List[ToolCall]
    is_tool_call: bool


class OllamaClient:
    """Client for Ollama API with tool calling."""

    # Pi 4B conservative defaults
    DEFAULT_NUM_THREAD = 4
    DEFAULT_NUM_CTX = 2048
    DEFAULT_NUM_PREDICT = 256
    DEFAULT_NUM_BATCH = 128

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:4b",
        timeout: float = 120.0,
        num_thread: int = DEFAULT_NUM_THREAD,
        num_ctx: int = DEFAULT_NUM_CTX,
        num_predict: int = DEFAULT_NUM_PREDICT,
        num_batch: int = DEFAULT_NUM_BATCH,
    ):
        self.base_url = base_url
        self.model = model
        self.client = httpx.Client(timeout=timeout)
        self._options = {
            "temperature": 0.7,
            "num_thread": num_thread,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
            "num_batch": num_batch,
        }

    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        stream: bool = False
    ) -> ChatResponse:
        """
        Send chat completion request with optional tools.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions
            stream: Whether to stream the response

        Returns:
            ChatResponse with content and/or tool calls
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": self._options,
        }

        if tools:
            payload["tools"] = tools

        response = self.client.post(
            f"{self.base_url}/api/chat",
            json=payload
        )
        response.raise_for_status()

        data = response.json()
        message = data.get("message", {})

        # Check for tool calls
        tool_calls = []
        if "tool_calls" in message:
            for tc in message["tool_calls"]:
                func = tc.get("function", {})
                args = func.get("arguments", {})

                # Handle arguments that might be strings
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}

                tool_calls.append(ToolCall(
                    name=func.get("name", ""),
                    arguments=args
                ))

        return ChatResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
            is_tool_call=len(tool_calls) > 0
        )

    def chat_stream(
        self,
        messages: List[Dict[str, str]]
    ) -> Generator[str, None, None]:
        """
        Stream chat completion response.

        Yields content chunks as they arrive.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": self._options,
        }

        with self.client.stream(
            "POST",
            f"{self.base_url}/api/chat",
            json=payload
        ) as response:
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    if "message" in data and "content" in data["message"]:
                        yield data["message"]["content"]

    def is_available(self) -> bool:
        """Check if Ollama is running."""
        try:
            response = self.client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except Exception:
            return False

    def ensure_model_loaded(self) -> bool:
        """Ensure model is loaded in memory."""
        try:
            response = self.client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": "hello",
                    "keep_alive": "10m"
                }
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Error loading model: {e}")
            return False
