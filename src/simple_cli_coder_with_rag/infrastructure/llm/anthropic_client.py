"""Anthropic-SDK-backed ``LLMClient`` adapter.

Targets the official Anthropic Messages API and works with any
Anthropic-compatible endpoint via ``base_url`` (e.g. MiniMax at
``https://api.minimax.io/anthropic``). The Anthropic Python SDK already ships
``max_retries`` + exponential backoff, so we do not layer an extra retry
library on top (per ``docs/development-tools.md`` §6 and §8).

Auth scheme note: we pass the key as ``auth_token`` (Bearer), not the
SDK's default ``x-api-key`` header, because MiniMax's HTTP API requires
``Authorization: Bearer <key>``; the same credential works against the
official ``https://api.anthropic.com`` endpoint. The mock tests in
``test_anthropic_client.py`` confirm the adapter passes the key as
``auth_token``.

DO-10 fully implements ``complete_with_tools``. The previous stub returned
``tool_calls=[]``; this version walks the response's content blocks,
collects ``TextBlock.text`` into ``content``, and turns each
``ToolUseBlock(id, name, input)`` into a project-owned
:class:`~simple_cli_coder_with_rag.domain.messages.ToolCall`. Vendor
``APIError`` is wrapped in :class:`LLMError`.

Wire-format translation rules (Anthropic Messages API only allows ``user``
and ``assistant`` roles — there is no ``tool`` role):

* ``SystemMessage`` → pulled out into the ``system=`` parameter, never
  placed in the ``messages`` array.
* ``UserMessage`` → ``{"role": "user", "content": m.content}``.
* ``AssistantMessage`` → ``{"role": "assistant", "content": [...]}`` where
  the block list is ``[{"type": "text", "text": m.content}]`` (omitted when
  empty) followed by one ``{"type": "tool_use", "id": ..., "name": ...,
  "input": ...}`` per ``m.tool_calls``.
* ``ToolResultMessage`` → ``{"role": "user", "content": [{"type":
  "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}, ...]}``.
  Consecutive ``ToolResultMessage``s are grouped into a single ``user``
  message so each ``tool_result`` block pairs with the assistant's
  preceding ``tool_use`` turn.
"""

from __future__ import annotations

from typing import Any, cast

import anthropic

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


class AnthropicLLMClient:
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
        system, sdk_messages = _messages_to_sdk(messages)
        kwargs: dict[str, Any] = {"max_tokens": 1024}
        if system:
            kwargs["system"] = system
        try:
            response = self._client.messages.create(
                model=model,
                messages=cast("Any", sdk_messages),
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
        """Send ``messages`` + ``tools`` to the Anthropic-compat backend and parse the reply.

        The wire shape is the Anthropic Messages API's ``tools=[{name,
        description, input_schema}]`` + ``messages=[{role: "user"|"assistant",
        content: list[block]}]`` format. ``ToolResultMessage``s are grouped
        into a single ``user`` message with ``tool_result`` blocks; see the
        module docstring for the full rule set.

        Returns an :class:`AssistantTurn` with concatenated ``TextBlock.text``
        in ``content`` and one :class:`ToolCall` per ``ToolUseBlock`` in
        ``tool_calls``. A vendor ``APIError`` is wrapped in ``LLMError``.
        """
        system, sdk_messages = _messages_to_sdk(messages)
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
                messages=cast("Any", sdk_messages),
                **kwargs,
            )
        except Exception as exc:
            raise LLMError(f"Anthropic-compat backend error: {exc}") from exc

        return _parse_response(response)


def _messages_to_sdk(messages: list[Any]) -> tuple[str | None, list[dict[str, Any]]]:
    """Translate domain ``Message`` list to Anthropic's wire shape.

    Returns ``(system_text, sdk_messages)``:

    * ``system_text`` is the concatenated system text (or ``None`` when no
      system message was present) — passed via the top-level ``system=``
      parameter on the wire.
    * ``sdk_messages`` is the list of ``user`` / ``assistant`` messages.

    ``ToolResultMessage``s are grouped into a single ``user`` message with
    multiple ``tool_result`` blocks; standalone ``UserMessage``s are passed
    through with string content.
    """
    system_text: str | None = None
    sdk_messages: list[dict[str, Any]] = []

    def _flush_tool_results(buffer: list[ToolResultMessage]) -> None:
        """Push ``buffer`` as a single ``user`` message, then clear it."""
        if not buffer:
            return
        sdk_messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": m.tool_call_id,
                        "content": m.content,
                    }
                    for m in buffer
                ],
            }
        )
        buffer.clear()

    pending_tool_results: list[ToolResultMessage] = []

    for msg in messages:
        if isinstance(msg, SystemMessage):
            # If multiple system messages are present, concatenate with a
            # newline — Anthropic accepts a string or a list of blocks for
            # ``system``. The simple string form is enough for our prompts.
            system_text = msg.content if system_text is None else f"{system_text}\n{msg.content}"
            continue
        if isinstance(msg, ToolResultMessage):
            pending_tool_results.append(msg)
            continue
        # Non-tool-result messages must break the pending buffer — Anthropic
        # rejects a ``tool_result`` block whose preceding assistant turn
        # does not contain a matching ``tool_use`` block, and the
        # application layer's chat-loop never interleaves a non-result
        # between results of the same tool call.
        _flush_tool_results(pending_tool_results)

        if isinstance(msg, UserMessage):
            sdk_messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AssistantMessage):
            content_blocks: list[dict[str, Any]] = []
            if msg.content:
                content_blocks.append({"type": "text", "text": msg.content})
            for call in msg.tool_calls:
                content_blocks.append(
                    {
                        "type": "tool_use",
                        "id": call.id,
                        "name": call.name,
                        "input": call.arguments,
                    }
                )
            sdk_messages.append({"role": "assistant", "content": content_blocks})
        elif isinstance(msg, Message):
            # Defensive fallback: a base ``Message`` (constructed without a
            # leaf role) is rare in production. Treat it as a user message
            # so a mis-typed message does not silently disappear.
            sdk_messages.append({"role": msg.role, "content": msg.content})
        else:  # pragma: no cover - defensive
            raise TypeError(f"unsupported message type for Anthropic adapter: {type(msg).__name__}")

    # Flush any trailing tool results.
    _flush_tool_results(pending_tool_results)

    return system_text, sdk_messages


def _parse_response(response: Any) -> AssistantTurn:
    """Walk ``response.content`` and collect text + tool_use blocks.

    Concatenates ``TextBlock.text`` into ``content`` and turns each
    ``ToolUseBlock(id, name, input)`` into a project-owned ``ToolCall``.
    Unknown block types are silently skipped (Anthropic adds new block
    types over time — the project must not crash on them).
    """
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    for block in getattr(response, "content", []) or []:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            text = getattr(block, "text", None)
            if text:
                text_parts.append(text)
        elif block_type == "tool_use":
            tool_calls.append(
                ToolCall(
                    id=getattr(block, "id", ""),
                    name=getattr(block, "name", ""),
                    arguments=dict(getattr(block, "input", {}) or {}),
                )
            )
        # Other block types (thinking, image, ...) are ignored.
    return AssistantTurn(content="".join(text_parts), tool_calls=tool_calls)


def _extract_text(response: Any) -> str:
    """Return the concatenated text of all text blocks in the response.

    Kept as a thin wrapper around :func:`_parse_response` for the plain
    ``complete`` path so the rule stays in one place.
    """
    return _parse_response(response).content


def _tool_spec_to_anthropic(tool: ToolSpec) -> dict[str, Any]:
    """Project ``ToolSpec`` -> Anthropic SDK ``tools`` array entry."""
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
    }


__all__ = ["AnthropicLLMClient"]
