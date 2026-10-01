"""Tests for the domain message Pydantic models.

Pinned by ``agent-development/02-llm-client-adapter/tests.md``. DO-10 extends
the role union with ``"tool"`` and adds new tests for tool-result messages
(see ``agent-development/README.md`` *Known discrepancies*).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from simple_cli_coder_with_rag.domain.messages import (
    AssistantMessage,
    AssistantTurn,
    Message,
    SystemMessage,
    ToolCall,
    ToolSpec,
    UserMessage,
)


def test_user_message_role_default() -> None:
    msg = UserMessage(content="hi")
    assert msg.role == "user"
    assert msg.content == "hi"


def test_assistant_message_role_default() -> None:
    msg = AssistantMessage(content="hello")
    assert msg.role == "assistant"
    assert msg.content == "hello"


def test_system_message_role_default() -> None:
    msg = SystemMessage(content="you are a helpful assistant")
    assert msg.role == "system"
    assert msg.content == "you are a helpful assistant"


def test_leaf_messages_are_frozen() -> None:
    """Frozen leaf models must reject post-init mutation."""
    msg = UserMessage(content="hi")
    with pytest.raises(ValidationError):
        msg.content = "bye"  # type: ignore[misc]


def test_message_union_validation() -> None:
    """An unknown ``role`` must fail validation on the base ``Message`` class.

    Uses ``"junior"`` (genuinely unknown; DO-10's ``"tool"`` is legitimate).
    """
    with pytest.raises(ValidationError):
        Message.model_validate({"role": "junior", "content": "hi"})


def test_message_accepts_each_known_role() -> None:
    """The base ``Message`` accepts ``"user"``, ``"assistant"``, ``"system"``."""
    assert Message(role="user", content="hi").role == "user"
    assert Message(role="assistant", content="hi").role == "assistant"
    assert Message(role="system", content="hi").role == "system"


def test_user_message_rejects_other_role() -> None:
    """``UserMessage`` pins its role; supplying a different role is rejected."""
    with pytest.raises(ValidationError):
        UserMessage(role="assistant", content="hi")  # type: ignore[arg-type]


def test_assistant_turn_default_empty_tool_calls() -> None:
    turn = AssistantTurn(content="hello")
    assert turn.content == "hello"
    assert turn.tool_calls == []


def test_tool_call_round_trip() -> None:
    call = ToolCall(id="1", name="read_file", arguments={"path": "/tmp/x"})
    dumped = call.model_dump()
    assert dumped == {"id": "1", "name": "read_file", "arguments": {"path": "/tmp/x"}}
    rebuilt = ToolCall.model_validate(dumped)
    assert rebuilt == call


def test_tool_spec_round_trip() -> None:
    spec = ToolSpec(
        name="read_file",
        description="Read a file from disk.",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
    )
    assert spec.name == "read_file"
    assert "path" in spec.input_schema["properties"]


def test_messages_are_distinct_classes() -> None:
    """The leaf classes are real subclasses — not the same type."""
    assert UserMessage(content="a") is not AssistantMessage(content="a")
    assert type(UserMessage(content="a")) is not type(AssistantMessage(content="a"))


def test_assistant_turn_preserves_tool_calls() -> None:
    calls = [ToolCall(id="1", name="x", arguments={})]
    turn = AssistantTurn(content="", tool_calls=calls)
    assert turn.tool_calls == calls
