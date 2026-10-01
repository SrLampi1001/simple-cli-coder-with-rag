"""Pydantic models for LLM messages, tool specs, and assistant turns.

Defines the wire shape that the application / presentation layers pass around.
The LLM adapters (``infrastructure/llm/``) translate this shape into the
provider's native format (``anthropic`` Messages API or OpenAI-compat
``/v1/chat/completions``).

DO-02 pins the schema with three roles (``user`` / ``assistant`` /
``system``); DO-10 extends the union with ``"tool"`` and a leaf
``ToolResultMessage`` (see ``agent-development/README.md`` *Known
discrepancies*).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    """Base chat message.

    Constructible directly (e.g. ``Message(role="user", content="hi")``).
    Leaf subclasses (:class:`UserMessage`, :class:`AssistantMessage`,
    :class:`SystemMessage`) freeze the role to a single literal and freeze
    the instance, while still being usable as a ``Message`` for downstream
    consumers.
    """

    role: Literal["user", "assistant", "system"]
    content: str


class UserMessage(Message):
    """A message sent by the user."""

    model_config = ConfigDict(frozen=True)
    role: Literal["user"] = "user"


class AssistantMessage(Message):
    """A message produced by the assistant."""

    model_config = ConfigDict(frozen=True)
    role: Literal["assistant"] = "assistant"


class SystemMessage(Message):
    """A system-level instruction.

    The Anthropic adapter lifts this out of the ``messages`` array and
    passes it as the top-level ``system`` parameter; the OpenAI-compat
    adapter keeps it in the messages array with ``role="system"``.
    """

    model_config = ConfigDict(frozen=True)
    role: Literal["system"] = "system"


# Discriminated union used by adapters that want static dispatch on role.
MessageUnion = Annotated[
    UserMessage | AssistantMessage | SystemMessage,
    Field(discriminator="role"),
]


class ToolSpec(BaseModel):
    """A tool definition exposed to the model.

    ``input_schema`` is a JSON Schema object describing the tool's argument
    shape; the adapters serialise it as-is (Anthropic: ``input_schema``,
    OpenAI: ``parameters``).
    """

    name: str
    description: str
    input_schema: dict[str, Any]


class ToolCall(BaseModel):
    """A single tool invocation the assistant decided to make.

    DO-10 wires parsing of vendor tool-use responses into ``AssistantTurn``.
    DO-02 leaves ``tool_calls`` empty by default.
    """

    id: str
    name: str
    arguments: dict[str, Any]


class AssistantTurn(BaseModel):
    """A single assistant reply, optionally carrying tool invocations.

    ``complete_with_tools`` returns this; ``complete`` is just the
    ``content`` field of this same shape.
    """

    content: str
    tool_calls: list[ToolCall] = Field(default_factory=list)


__all__ = [
    "AssistantMessage",
    "AssistantTurn",
    "Message",
    "MessageUnion",
    "SystemMessage",
    "ToolCall",
    "ToolSpec",
    "UserMessage",
]
