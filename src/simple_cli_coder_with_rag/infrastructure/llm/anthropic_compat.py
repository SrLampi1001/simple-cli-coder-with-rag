"""Anthropic-SDK-backed ``LLMClient`` adapter.

Used by MiniMax, which exposes an Anthropic-compatible Messages endpoint at
``https://api.minimax.io/anthropic``. The Anthropic Python SDK already ships
``max_retries`` + exponential backoff, so we do not layer an extra retry
library on top (per ``docs/development-tools.md`` §6 and §8).

Auth scheme note: MiniMax's HTTP API expects ``Authorization: Bearer <key>``,
not the Anthropic SDK's default ``x-api-key`` header. The SDK's ``auth_token``
parameter sets the Bearer header, so we use it instead of ``api_key``. The
mock tests in ``test_anthropic_compat_adapter.py`` confirm the adapter passes
the key as ``auth_token``.
"""

from __future__ import annotations

from typing import Any, cast

import anthropic

from simple_cli_coder_with_rag.domain.llm_client import LLMError
from simple_cli_coder_with_rag.domain.messages import (
    AssistantTurn,
    SystemMessage,
    ToolSpec,
)


class AnthropicCompatLLMClient:
    """``LLMClient`` implementation backed by the Anthropic Python SDK."""

    def __init__(self, *, api_key: str, base_url: str, default_model: str) -> None:
        # The SDK holds one persistent client for the lifetime of the
        # adapter; constructing it more than once would defeat connection
        # pooling and inflate per-call latency.
        self._client = anthropic.Anthropic(
            auth_token=api_key,
            base_url=base_url,
        )
        self._default_model = default_model

    def complete(self, messages: list[Any], *, model: str) -> str:
        """Plain chat completion. Returns the model's text reply."""
        system, chat_messages = _split_system(messages)
        kwargs: dict[str, Any] = {"max_tokens": 1024}
        if system:
            kwargs["system"] = system
        try:
            response = self._client.messages.create(
                model=model,
                messages=cast("Any", chat_messages),
                **kwargs,
            )
        except Exception as exc:
            raise LLMError(f"Anthropic-compat backend error: {exc}") from exc

        return _extract_text(response)

    def complete_with_tools(
        self,
        messages: list[Any],
        *,
        model: str,
        tools: list[ToolSpec],
    ) -> AssistantTurn:
        """Stub: sends the request, returns text with ``tool_calls=[]``.

        DO-10 fills in tool-use parsing. For now we only need the contract to
        compile and the round-trip shape to be correct.
        """
        system, chat_messages = _split_system(messages)
        anthropic_tools = [_tool_spec_to_anthropic(tool) for tool in tools]
        kwargs: dict[str, Any] = {
            "max_tokens": 1024,
            "tools": anthropic_tools,
        }
        if system:
            kwargs["system"] = system
        try:
            response = self._client.messages.create(
                model=model,
                messages=cast("Any", chat_messages),
                **kwargs,
            )
        except Exception as exc:
            raise LLMError(f"Anthropic-compat backend error: {exc}") from exc

        return AssistantTurn(content=_extract_text(response), tool_calls=[])


def _split_system(messages: list[Any]) -> tuple[str, list[dict[str, str]]]:
    """Pop the trailing system message (if any) out of the message list.

    The Anthropic API takes system instructions as a top-level ``system``
    parameter, not as a messages-array entry.
    """
    system_text = ""
    chat: list[dict[str, str]] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            system_text = msg.content
        else:
            chat.append({"role": msg.role, "content": msg.content})
    return system_text, chat


def _extract_text(response: Any) -> str:
    """Return the concatenated text of all text blocks in the response."""
    parts: list[str] = []
    for block in getattr(response, "content", []):
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(text)
    return "".join(parts)


def _tool_spec_to_anthropic(tool: ToolSpec) -> dict[str, Any]:
    """Project ``ToolSpec`` -> Anthropic SDK ``tools`` array entry."""
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
    }


__all__ = ["AnthropicCompatLLMClient"]
