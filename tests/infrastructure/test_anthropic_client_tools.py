"""Tests for ``AnthropicCompatLLMClient.complete_with_tools`` (DO-10).

Pinned by ``agent-development/10-file-editing/tests.md``.

Replaces the ``test_complete_with_tools_stub_returns_assistant_turn`` stub
from DO-02 (now removed from ``test_anthropic_compat_adapter.py``). The
adapter must:

* Call ``anthropic.Anthropic.messages.create(...)`` with the Anthropic
  tool schema (``name`` / ``description`` / ``input_schema``).
* Parse ``TextBlock.text`` and ``ToolUseBlock(id, name, input)`` from the
  response into ``AssistantTurn(content, tool_calls)``.
* Wrap vendor ``APIError`` in ``LLMError``.
* Translate ``AssistantMessage.tool_calls`` to ``tool_use`` blocks and
  ``ToolResultMessage`` to a ``user`` message containing ``tool_result``
  blocks — Anthropic's Messages API has **no** ``tool`` role.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from simple_cli_coder_with_rag.domain.llm_client import LLMError
from simple_cli_coder_with_rag.domain.messages import (
    AssistantMessage,
    AssistantTurn,
    ToolCall,
    ToolResultMessage,
    ToolSpec,
    UserMessage,
)
from simple_cli_coder_with_rag.infrastructure.llm.anthropic_compat import (
    AnthropicCompatLLMClient,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _stub_text_message(text: str) -> MagicMock:
    """Build a mock ``anthropic.Message`` with only a single text block."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    message = MagicMock()
    message.content = [block]
    return message


def _stub_tool_use_message(tool_use_id: str, name: str, input_: dict) -> MagicMock:
    """Build a mock ``anthropic.Message`` containing one tool_use block."""
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_use_id
    block.name = name
    block.input = input_
    message = MagicMock()
    message.content = [block]
    return message


def _stub_mixed_message(text: str, tool_use_id: str, name: str, input_: dict) -> MagicMock:
    """Build a mock ``anthropic.Message`` with text + tool_use blocks."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = tool_use_id
    tool_block.name = name
    tool_block.input = input_
    message = MagicMock()
    message.content = [text_block, tool_block]
    return message


class _FakeAnthropicError(Exception):
    """Mimics ``anthropic.APIError`` — kept as ``Exception`` for portability."""


def _make_adapter(
    mocker: MockerFixture, response: MagicMock
) -> tuple[AnthropicCompatLLMClient, MagicMock]:
    """Build an adapter whose SDK client returns ``response``.

    Returns ``(adapter, fake_client)`` so the test can introspect the
    captured ``messages.create`` call.
    """
    fake_anthropic = mocker.patch("anthropic.Anthropic")
    fake_client = fake_anthropic.return_value
    fake_client.messages.create.return_value = response
    adapter = AnthropicCompatLLMClient(
        api_key="k",
        base_url="https://api.minimax.io/anthropic",
        default_model="MiniMax-M3",
    )
    return adapter, fake_client


# ---------------------------------------------------------------------------
# Adapter-level behaviour
# ---------------------------------------------------------------------------


def test_complete_with_tools_returns_tool_calls(mocker: MockerFixture) -> None:
    """A response with a ``ToolUseBlock`` becomes ``AssistantTurn(tool_calls=[...])``."""
    response = _stub_tool_use_message("1", "read_file", {"path": "foo.txt"})
    adapter, _ = _make_adapter(mocker, response)

    turn = adapter.complete_with_tools(
        [UserMessage(content="hi")],
        model="MiniMax-M3",
        tools=[ToolSpec(name="read_file", description="d", input_schema={"type": "object"})],
    )

    assert isinstance(turn, AssistantTurn)
    assert turn.content == ""
    assert turn.tool_calls == [ToolCall(id="1", name="read_file", arguments={"path": "foo.txt"})]


def test_complete_with_tools_returns_text_only(mocker: MockerFixture) -> None:
    """A response with only text yields ``tool_calls=[]`` and the text in ``content``."""
    response = _stub_text_message("plain text reply")
    adapter, _ = _make_adapter(mocker, response)

    turn = adapter.complete_with_tools(
        [UserMessage(content="hi")],
        model="MiniMax-M3",
        tools=[ToolSpec(name="read_file", description="d", input_schema={"type": "object"})],
    )

    assert turn.content == "plain text reply"
    assert turn.tool_calls == []


def test_complete_with_tools_collects_text_and_tools(mocker: MockerFixture) -> None:
    """A response with text + tool_use blocks yields concatenated text and parsed calls."""
    response = _stub_mixed_message("here you go", "call-1", "read_file", {"path": "x"})
    adapter, _ = _make_adapter(mocker, response)

    turn = adapter.complete_with_tools(
        [UserMessage(content="hi")],
        model="MiniMax-M3",
        tools=[ToolSpec(name="read_file", description="d", input_schema={"type": "object"})],
    )

    assert turn.content == "here you go"
    assert turn.tool_calls == [ToolCall(id="call-1", name="read_file", arguments={"path": "x"})]


def test_complete_with_tools_wraps_api_error(mocker: MockerFixture) -> None:
    """A vendor ``APIError`` is wrapped in the project-owned ``LLMError``."""
    fake_anthropic = mocker.patch("anthropic.Anthropic")
    fake_client = fake_anthropic.return_value
    fake_client.messages.create.side_effect = _FakeAnthropicError("boom")

    adapter = AnthropicCompatLLMClient(
        api_key="k",
        base_url="https://api.minimax.io/anthropic",
        default_model="MiniMax-M3",
    )

    with pytest.raises(LLMError):
        adapter.complete_with_tools(
            [UserMessage(content="hi")],
            model="MiniMax-M3",
            tools=[ToolSpec(name="read_file", description="d", input_schema={"type": "object"})],
        )


def test_complete_with_tools_passes_tool_schemas(mocker: MockerFixture) -> None:
    """The captured SDK call's ``tools`` arg is a list of dicts with the Anthropic shape."""
    response = _stub_text_message("ok")
    adapter, fake_client = _make_adapter(mocker, response)

    tools = [
        ToolSpec(
            name="read_file",
            description="Read a file.",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        ),
        ToolSpec(
            name="edit_file",
            description="Edit a file.",
            input_schema={"type": "object"},
        ),
    ]
    adapter.complete_with_tools(
        [UserMessage(content="hi")],
        model="MiniMax-M3",
        tools=tools,
    )

    sent_tools = fake_client.messages.create.call_args.kwargs["tools"]
    assert sent_tools == [
        {
            "name": "read_file",
            "description": "Read a file.",
            "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
        },
        {
            "name": "edit_file",
            "description": "Edit a file.",
            "input_schema": {"type": "object"},
        },
    ]


# ---------------------------------------------------------------------------
# Domain -> SDK message translation
# ---------------------------------------------------------------------------


def test_assistant_tool_calls_map_to_tool_use_blocks(mocker: MockerFixture) -> None:
    """An ``AssistantMessage`` with ``tool_calls`` becomes an assistant message with a
    ``tool_use`` block on the wire."""
    response = _stub_text_message("ok")
    adapter, fake_client = _make_adapter(mocker, response)

    messages = [
        UserMessage(content="hi"),
        AssistantMessage(
            content="",
            tool_calls=[ToolCall(id="call-7", name="read_file", arguments={"path": "foo.txt"})],
        ),
    ]
    adapter.complete_with_tools(
        messages,
        model="MiniMax-M3",
        tools=[ToolSpec(name="read_file", description="d", input_schema={"type": "object"})],
    )

    sent_messages = fake_client.messages.create.call_args.kwargs["messages"]
    assert len(sent_messages) == 2
    assistant_entry = sent_messages[1]
    assert assistant_entry["role"] == "assistant"
    blocks = assistant_entry["content"]
    assert any(
        block.get("type") == "tool_use"
        and block.get("id") == "call-7"
        and block.get("name") == "read_file"
        and block.get("input") == {"path": "foo.txt"}
        for block in blocks
    )


def test_assistant_text_only_maps_to_text_block(mocker: MockerFixture) -> None:
    """An ``AssistantMessage`` without ``tool_calls`` becomes an assistant message with
    a single ``text`` block (Anthropic's wire shape)."""
    response = _stub_text_message("ok")
    adapter, fake_client = _make_adapter(mocker, response)

    adapter.complete_with_tools(
        [UserMessage(content="hi"), AssistantMessage(content="hello")],
        model="MiniMax-M3",
        tools=[ToolSpec(name="read_file", description="d", input_schema={"type": "object"})],
    )

    sent_messages = fake_client.messages.create.call_args.kwargs["messages"]
    assistant_entry = sent_messages[1]
    assert assistant_entry["role"] == "assistant"
    blocks = assistant_entry["content"]
    assert blocks == [{"type": "text", "text": "hello"}]


def test_tool_result_messages_map_to_user_tool_result_blocks(mocker: MockerFixture) -> None:
    """Consecutive ``ToolResultMessage``s become a single ``user`` message containing
    one ``tool_result`` block per result, keyed by ``tool_use_id``.

    Anthropic's Messages API accepts only ``user`` and ``assistant`` roles —
    the ``tool`` role must be translated at the adapter boundary.
    """
    response = _stub_text_message("ok")
    adapter, fake_client = _make_adapter(mocker, response)

    messages = [
        UserMessage(content="hi"),
        AssistantMessage(
            content="",
            tool_calls=[
                ToolCall(id="a", name="read_file", arguments={"path": "foo"}),
                ToolCall(id="b", name="read_file", arguments={"path": "bar"}),
            ],
        ),
        ToolResultMessage(tool_call_id="a", content="FOO"),
        ToolResultMessage(tool_call_id="b", content="BAR"),
    ]
    adapter.complete_with_tools(
        messages,
        model="MiniMax-M3",
        tools=[ToolSpec(name="read_file", description="d", input_schema={"type": "object"})],
    )

    sent_messages = fake_client.messages.create.call_args.kwargs["messages"]
    # No "tool" role should ever be sent.
    assert all(entry["role"] != "tool" for entry in sent_messages)
    # The two consecutive tool results should land in one user message.
    user_entries = [m for m in sent_messages if m["role"] == "user"]
    assert any(
        isinstance(entry["content"], list)
        and all(block.get("type") == "tool_result" for block in entry["content"])
        and any(
            block.get("tool_use_id") == "a" and block.get("content") == "FOO"
            for block in entry["content"]
        )
        and any(
            block.get("tool_use_id") == "b" and block.get("content") == "BAR"
            for block in entry["content"]
        )
        for entry in user_entries
    )


def test_system_message_extracted_to_system_param(mocker: MockerFixture) -> None:
    """``SystemMessage`` is lifted out of the messages array into the top-level
    ``system`` parameter, matching the Anthropic API contract."""
    response = _stub_text_message("ok")
    adapter, fake_client = _make_adapter(mocker, response)

    from simple_cli_coder_with_rag.domain.messages import SystemMessage

    adapter.complete_with_tools(
        [SystemMessage(content="you are helpful"), UserMessage(content="hi")],
        model="MiniMax-M3",
        tools=[ToolSpec(name="read_file", description="d", input_schema={"type": "object"})],
    )

    call_kwargs = fake_client.messages.create.call_args.kwargs
    assert call_kwargs["system"] == "you are helpful"
    sent_messages = call_kwargs["messages"]
    assert [m["role"] for m in sent_messages] == ["user"]
