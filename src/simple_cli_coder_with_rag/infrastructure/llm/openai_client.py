"""Official-``openai``-SDK-backed ``LLMClient`` adapter.

Covers every OpenAI-compatible chat endpoint (OpenAI itself, NVIDIA NIM,
Mistral, and any custom registry entry whose ``adapter`` is ``"openai"``)
by passing ``base_url`` to the SDK constructor. ``ToolResultMessage`` is
sent as ``{"role": "tool", ...}`` — the OpenAI wire format supports a
``tool`` role natively. See ``tests/infrastructure/llm/test_openai_client.py``
for the mocked-SDK contract.
"""

from __future__ import annotations

import json
from typing import Any, cast

import openai

from simple_cli_coder_with_rag.domain.llm_client import LLMError
from simple_cli_coder_with_rag.domain.messages import (
    AssistantMessage,
    AssistantTurn,
    Message,
    SystemMessage,
    ToolCall,
    ToolResultMessage,
    ToolSpec,
    UserMessage,
)


class OpenAILLMClient:
    """``LLMClient`` implementation backed by the official ``openai`` SDK."""

    def __init__(self, *, api_key: str, base_url: str, default_model: str) -> None:
        # One persistent SDK client per adapter instance (DO-02 contract) —
        # connection pooling would be defeated by a per-call constructor.
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url)
        self._default_model = default_model

    def complete(self, messages: list[Any], *, model: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=cast("Any", _messages_to_openai(messages)),
            )
        except Exception as exc:
            raise LLMError(f"OpenAI error: {exc}") from exc
        try:
            return cast("str", response.choices[0].message.content)
        except (AttributeError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected OpenAI response shape: {response!r}") from exc

    def complete_with_tools(
        self,
        messages: list[Any],
        *,
        model: str,
        tools: list[ToolSpec],
    ) -> AssistantTurn:
        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=cast("Any", _messages_to_openai(messages)),
                tools=cast("Any", [_tool_spec_to_openai(tool) for tool in tools]),
            )
        except Exception as exc:
            raise LLMError(f"OpenAI error: {exc}") from exc
        try:
            message = response.choices[0].message
        except (AttributeError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected OpenAI response shape: {response!r}") from exc
        return _parse_response(message)


def _messages_to_openai(messages: list[Any]) -> list[dict[str, Any]]:
    """Translate our domain ``Message`` list to the OpenAI shape."""
    out: list[dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            out.append({"role": "system", "content": msg.content})
        elif isinstance(msg, UserMessage):
            out.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AssistantMessage):
            entry: dict[str, Any] = {"role": "assistant", "content": msg.content}
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments),
                        },
                    }
                    for call in msg.tool_calls
                ]
            out.append(entry)
        elif isinstance(msg, ToolResultMessage):
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content,
                }
            )
        elif isinstance(msg, Message):  # defensive
            out.append({"role": msg.role, "content": msg.content})
        else:  # pragma: no cover - defensive
            raise TypeError(f"unsupported message type for OpenAI adapter: {type(msg).__name__}")
    return out


def _parse_response(message: Any) -> AssistantTurn:
    """Extract text + tool calls from the SDK's response message object."""
    content = getattr(message, "content", None) or ""
    tool_calls: list[ToolCall] = []
    for raw in getattr(message, "tool_calls", None) or []:
        function = getattr(raw, "function", None) or (
            raw.get("function", {}) if isinstance(raw, dict) else {}
        )
        if isinstance(function, dict):
            name = function.get("name", "")
            arguments_raw: Any = function.get("arguments", "{}")
        else:
            name = getattr(function, "name", "") or ""
            arguments_raw = getattr(function, "arguments", "{}")
        if isinstance(arguments_raw, str):
            try:
                arguments = json.loads(arguments_raw) if arguments_raw.strip() else {}
            except json.JSONDecodeError:
                arguments = {"_raw": arguments_raw}
        elif isinstance(arguments_raw, dict):
            arguments = dict(arguments_raw)
        else:
            arguments = {}
        raw_id = raw.get("id", "") if isinstance(raw, dict) else getattr(raw, "id", "")
        tool_calls.append(ToolCall(id=raw_id or "", name=name, arguments=arguments))
    return AssistantTurn(content=content, tool_calls=tool_calls)


def _tool_spec_to_openai(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


__all__ = ["OpenAILLMClient"]
