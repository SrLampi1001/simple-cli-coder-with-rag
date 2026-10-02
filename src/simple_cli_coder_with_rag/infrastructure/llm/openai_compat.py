"""Stdlib-only ``LLMClient`` adapter for OpenAI-compatible chat APIs.

Used by **NVIDIA NIM** (cloud, ``integrate.api.nvidia.com``) and **Mistral**
(``api.mistral.ai``) — both expose ``POST /v1/chat/completions`` with
``Authorization: Bearer <key>``.

We deliberately avoid adding a third-party SDK here: per the DO-02 plan and
the user's sign-off, the implementation uses ``urllib.request`` and
``json`` from the standard library. That keeps the install footprint
identical to DO-01 and lets us hold the Adapter pattern without leaking
httpx or openai types into the application layer.

DO-10 fully implements ``complete_with_tools``. The previous stub returned
``tool_calls=[]``; this version parses the OpenAI-compat
``choices[0].message.tool_calls`` shape into project-owned
:class:`~simple_cli_coder_with_rag.domain.messages.ToolCall` objects.

Wire-format notes:

* Tool schemas use the ``{"type": "function", "function": {name,
  description, parameters}}`` shape OpenAI-compat APIs expect.
* ``ToolResultMessage`` is sent as ``{"role": "tool", "tool_call_id": ...,
  "content": ...}`` — OpenAI-compat DOES support a ``tool`` role, so the
  domain ``tool`` role maps to the wire verbatim (unlike the Anthropic
  adapter, which translates to a user message).
* The application layer's chat-loop treats ``tool``-role messages
  identically for both adapters — the conversation shape is the same.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

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


class OpenAICompatLLMClient:
    """``LLMClient`` implementation backed by ``urllib.request`` + JSON.

    Stateless: every call opens a fresh HTTP request. No persistent client
    to construct, so the "one SDK instance per adapter" contract is
    trivially satisfied (see ``test_adapter_holds_one_client_instance``).
    """

    def __init__(self, *, base_url: str, api_key: str, default_model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_model = default_model

    def complete(self, messages: list[Any], *, model: str) -> str:
        body = {
            "model": model,
            "messages": _messages_to_openai(messages),
        }
        payload = _post_json(self._base_url, self._api_key, body)
        try:
            choices = payload["choices"]
            message = choices[0]["message"]
            return message["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected OpenAI-compat response shape: {payload!r}") from exc

    def complete_with_tools(
        self,
        messages: list[Any],
        *,
        model: str,
        tools: list[ToolSpec],
    ) -> AssistantTurn:
        """Send ``messages`` + ``tools`` to the OpenAI-compat backend.

        The request body adds ``tools=[{type: "function", function: ...}]``
        and forwards the chat-loop's ``ToolResultMessage``s as
        ``{"role": "tool", ...}`` messages (which the wire format accepts
        natively — no translation needed).

        The reply's ``choices[0].message`` carries both ``content`` (text)
        and ``tool_calls`` (list of ``{id, function: {name, arguments}}``
        dicts). The function arguments arrive as a JSON string per the
        spec; we parse them into a dict before constructing ``ToolCall``.
        """
        body = {
            "model": model,
            "messages": _messages_to_openai(messages),
            "tools": [_tool_spec_to_openai(tool) for tool in tools],
        }
        payload = _post_json(self._base_url, self._api_key, body)
        try:
            message = payload["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected OpenAI-compat response shape: {payload!r}") from exc
        return _parse_response(message)


def _messages_to_openai(messages: list[Any]) -> list[dict[str, Any]]:
    """Translate our domain ``Message`` list to the OpenAI-compat shape.

    * ``SystemMessage`` stays in the messages array with ``role="system"``
      (OpenAI-compat has no separate ``system`` parameter).
    * ``UserMessage`` → ``{"role": "user", "content": m.content}``.
    * ``AssistantMessage`` → ``{"role": "assistant", "content": m.content}``.
      If ``tool_calls`` is non-empty, we emit one ``tool_calls`` entry per
      call with ``{"id", "type": "function", "function": {"name",
      "arguments": json.dumps(arguments)}}``.
    * ``ToolResultMessage`` → ``{"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content}``.
    """  # noqa: E501
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
            raise TypeError(
                f"unsupported message type for OpenAI-compat adapter: {type(msg).__name__}"
            )
    return out


def _parse_response(message: dict[str, Any]) -> AssistantTurn:
    """Extract text + tool_calls from a single OpenAI-compat response message.

    ``message["content"]`` is the assistant's text reply (may be ``None``
    when the reply is tool-only). ``message["tool_calls"]`` is the list
    of tool invocations — each entry has ``{"id", "type": "function",
    "function": {"name", "arguments"}}`` where ``arguments`` is a JSON
    string that we decode here.
    """
    content = message.get("content") or ""
    tool_calls: list[ToolCall] = []
    for raw in message.get("tool_calls") or []:
        function = raw.get("function", {})
        name = function.get("name", "")
        arguments_raw = function.get("arguments", "{}")
        if isinstance(arguments_raw, str):
            try:
                arguments = json.loads(arguments_raw) if arguments_raw.strip() else {}
            except json.JSONDecodeError:
                arguments = {"_raw": arguments_raw}
        else:
            arguments = dict(arguments_raw)
        tool_calls.append(ToolCall(id=raw.get("id", ""), name=name, arguments=arguments))
    return AssistantTurn(content=content, tool_calls=tool_calls)


def _tool_spec_to_openai(tool: ToolSpec) -> dict[str, Any]:
    """Project ``ToolSpec`` -> OpenAI-compat ``tools`` array entry."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


def _post_json(base_url: str, api_key: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST ``body`` as JSON to ``<base_url>/chat/completions`` and parse the reply.

    Wraps every transport-layer error in ``LLMError`` so the caller never has
    to import ``urllib.error`` types.
    """
    url = f"{base_url}/chat/completions"
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read()
    except urllib.error.URLError as exc:
        raise LLMError(f"OpenAI-compat transport error: {exc}") from exc

    try:
        payload: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMError(f"OpenAI-compat response was not valid JSON: {raw!r}") from exc
    return payload


__all__ = ["OpenAICompatLLMClient"]
