"""Stdlib-only ``LLMClient`` adapter for OpenAI-compatible chat APIs.

Used by **NVIDIA NIM** (cloud, ``integrate.api.nvidia.com``) and **Mistral**
(``api.mistral.ai``) — both expose ``POST /v1/chat/completions`` with
``Authorization: Bearer <key>``.

We deliberately avoid adding a third-party SDK here: per the DO-02 plan and
the user's sign-off, the implementation uses ``urllib.request`` and
``json`` from the standard library. That keeps the install footprint
identical to DO-01 and lets us hold the Adapter pattern without leaking
httpx or openai types into the application layer.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from simple_cli_coder_with_rag.domain.llm_client import LLMError
from simple_cli_coder_with_rag.domain.messages import (
    AssistantTurn,
    ToolSpec,
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
        body = {
            "model": model,
            "messages": _messages_to_openai(messages),
            "tools": [_tool_spec_to_openai(tool) for tool in tools],
        }
        payload = _post_json(self._base_url, self._api_key, body)
        try:
            text = payload["choices"][0]["message"].get("content", "")
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected OpenAI-compat response shape: {payload!r}") from exc
        # DO-10 will parse payload["choices"][0]["message"]["tool_calls"].
        return AssistantTurn(content=text or "", tool_calls=[])


def _messages_to_openai(messages: list[Any]) -> list[dict[str, str]]:
    """Translate our domain ``Message`` list to the OpenAI-compat shape.

    System messages stay in the array (with ``role="system"``) — the
    OpenAI-compat spec does not have a separate ``system`` parameter.
    """
    return [{"role": msg.role, "content": msg.content} for msg in messages]


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
