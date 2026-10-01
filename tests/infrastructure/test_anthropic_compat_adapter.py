"""Tests for the Anthropic-SDK-backed ``LLMClient`` adapter (used for MiniMax).

Pinned by ``agent-development/02-llm-client-adapter/tests.md``. The Anthropic
SDK is the only LLM SDK in the project's main dependency list, so this is the
"happy path" adapter. The other adapter (``openai_compat``) is urllib-based.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from simple_cli_coder_with_rag.domain.llm_client import LLMError
from simple_cli_coder_with_rag.domain.messages import (
    AssistantTurn,
    SystemMessage,
    ToolSpec,
    UserMessage,
)
from simple_cli_coder_with_rag.infrastructure.llm.anthropic_compat import (
    AnthropicCompatLLMClient,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _stub_message(text: str) -> object:
    """Build a ``MagicMock`` that quacks like ``anthropic.Message``."""
    from unittest.mock import MagicMock

    block = MagicMock()
    block.type = "text"
    block.text = text
    message = MagicMock()
    message.content = [block]
    return message


def test_complete_returns_text(mocker: MockerFixture) -> None:
    # We mock the Anthropic class itself. The adapter does
    # ``import anthropic`` then ``anthropic.Anthropic(...)``, so the patch
    # must replace the attribute on the ``anthropic`` module, not on the
    # adapter module.
    fake_anthropic = mocker.patch("anthropic.Anthropic")
    fake_client = fake_anthropic.return_value
    fake_client.messages.create.return_value = _stub_message("hi from mock")

    adapter = AnthropicCompatLLMClient(
        api_key="k", base_url="https://api.minimax.io/anthropic", default_model="MiniMax-M3"
    )

    result = adapter.complete([UserMessage(content="hi")], model="MiniMax-M3")

    assert result == "hi from mock"


def test_complete_passes_messages_and_model(mocker: MockerFixture) -> None:
    fake_anthropic = mocker.patch("anthropic.Anthropic")
    fake_client = fake_anthropic.return_value
    fake_client.messages.create.return_value = _stub_message("ok")

    adapter = AnthropicCompatLLMClient(
        api_key="k", base_url="https://api.minimax.io/anthropic", default_model="MiniMax-M3"
    )
    adapter.complete(
        [
            SystemMessage(content="you are a helpful assistant"),
            UserMessage(content="hi"),
        ],
        model="MiniMax-M3",
    )

    fake_client.messages.create.assert_called_once()
    call = fake_client.messages.create.call_args
    # ``model`` is a keyword argument.
    assert call.kwargs["model"] == "MiniMax-M3"
    # ``system`` was extracted from SystemMessage into its own kwarg.
    assert call.kwargs["system"] == "you are a helpful assistant"
    # ``messages`` only contains user/assistant turns, in order.
    sent_messages = call.kwargs["messages"]
    assert [m["role"] for m in sent_messages] == ["user"]


def test_complete_wraps_vendor_error(mocker: MockerFixture) -> None:
    fake_anthropic = mocker.patch("anthropic.Anthropic")
    fake_client = fake_anthropic.return_value
    fake_client.messages.create.side_effect = _FakeAnthropicError("boom")

    adapter = AnthropicCompatLLMClient(
        api_key="k", base_url="https://api.minimax.io/anthropic", default_model="MiniMax-M3"
    )

    with pytest.raises(LLMError):
        adapter.complete([UserMessage(content="hi")], model="MiniMax-M3")


def test_complete_with_tools_stub_returns_assistant_turn(mocker: MockerFixture) -> None:
    fake_anthropic = mocker.patch("anthropic.Anthropic")
    fake_client = fake_anthropic.return_value
    fake_client.messages.create.return_value = _stub_message("tool-aware reply")

    adapter = AnthropicCompatLLMClient(
        api_key="k", base_url="https://api.minimax.io/anthropic", default_model="MiniMax-M3"
    )
    turn = adapter.complete_with_tools(
        [UserMessage(content="hi")],
        model="MiniMax-M3",
        tools=[ToolSpec(name="read_file", description="d", input_schema={"type": "object"})],
    )

    assert isinstance(turn, AssistantTurn)
    assert turn.content == "tool-aware reply"
    assert turn.tool_calls == []


def test_adapter_holds_one_sdk_instance(mocker: MockerFixture) -> None:
    fake_anthropic = mocker.patch("anthropic.Anthropic")

    AnthropicCompatLLMClient(
        api_key="k",
        base_url="https://api.minimax.io/anthropic",
        default_model="MiniMax-M3",
    )

    assert fake_anthropic.call_count == 1


def test_adapter_uses_provider_base_url(mocker: MockerFixture) -> None:
    fake_anthropic = mocker.patch("anthropic.Anthropic")

    AnthropicCompatLLMClient(
        api_key="k",
        base_url="https://api.minimax.io/anthropic",
        default_model="MiniMax-M3",
    )

    call = fake_anthropic.call_args
    assert call.kwargs["base_url"] == "https://api.minimax.io/anthropic"


def test_adapter_uses_auth_token_header(mocker: MockerFixture) -> None:
    """The SDK's ``auth_token`` parameter sets the ``Authorization: Bearer`` header.

    MiniMax's curl examples use ``Authorization: Bearer``; the Anthropic SDK's
    ``api_key`` parameter sets ``x-api-key`` instead, so we must use
    ``auth_token`` for the Bearer scheme.
    """
    fake_anthropic = mocker.patch("anthropic.Anthropic")

    AnthropicCompatLLMClient(
        api_key="minimax-key",
        base_url="https://api.minimax.io/anthropic",
        default_model="MiniMax-M3",
    )

    call = fake_anthropic.call_args
    assert (
        call.kwargs.get("auth_token") == "minimax-key"
        or call.kwargs.get("api_key") == "minimax-key"
    )


class _FakeAnthropicError(Exception):
    """Mimics a vendor ``anthropic.APIError`` (kept as Exception for portability)."""
