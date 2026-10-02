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

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class Message(BaseModel):
    """Base chat message.

    Constructible directly (e.g. ``Message(role="user", content="hi")``).
    Leaf subclasses (:class:`UserMessage`, :class:`AssistantMessage`,
    :class:`SystemMessage`, :class:`ToolResultMessage`) freeze the role
    to a single literal and freeze the instance, while still being usable
    as a ``Message`` for downstream consumers.

    The ``role`` literal is widened to four values after DO-10 to
    accommodate ``ToolResultMessage``. The union discriminator below
    (``MessageUnion``) lists the four leaf classes; ``model_validate``
    dispatches on the ``role`` field automatically.
    """

    role: Literal["user", "assistant", "system", "tool"]
    content: str

    @classmethod
    def model_validate(  # type: ignore[override]
        cls,
        obj: Any,
        *,
        strict: bool | None = None,
        from_attributes: bool | None = None,
        context: Any | None = None,
    ) -> Any:
        """Polymorphic ``model_validate``: dispatch on ``role`` to the right leaf.

        ``Message.model_validate({"role": "tool", "tool_call_id": "1", ...})``
        returns a :class:`ToolResultMessage` (not a base ``Message`` with the
        ``tool_call_id`` field stripped). The chat-loop in
        :class:`~simple_cli_coder_with_rag.application.knowledge_service.KnowledgeService`
        relies on this so a tool result keeps its ``tool_call_id`` through
        the round trip to the adapter.

        Direct construction (``Message(role="user", content="hi")``) is
        unaffected — it goes through ``__init__`` and the model validator
        is bypassed, so the existing DO-02 tests still pass.

        Unknown roles still raise ``ValidationError`` because the literal
        on ``Message.role`` rejects them.
        """
        if cls is not Message:
            return super().model_validate(
                obj, strict=strict, from_attributes=from_attributes, context=context
            )
        if not isinstance(obj, dict) or "role" not in obj:
            return super().model_validate(
                obj, strict=strict, from_attributes=from_attributes, context=context
            )
        return _MESSAGE_UNION_ADAPTER.validate_python(obj)


class UserMessage(Message):
    """A message sent by the user."""

    model_config = ConfigDict(frozen=True)
    role: Literal["user"] = "user"


class AssistantMessage(Message):
    """A message produced by the assistant.

    DO-10 extends the constructor with an optional ``tool_calls`` field
    (default ``[]``) so the chat-loop can echo an assistant tool-use turn
    back into the transcript before sending the tool results to the LLM.
    DO-02/DO-03 callers that only set ``content`` keep working — the
    default factory produces an empty list.
    """

    model_config = ConfigDict(frozen=True)
    role: Literal["assistant"] = "assistant"
    tool_calls: list[ToolCall] = Field(default_factory=list)


class SystemMessage(Message):
    """A system-level instruction.

    The Anthropic adapter lifts this out of the ``messages`` array and
    passes it as the top-level ``system`` parameter; the OpenAI-compat
    adapter keeps it in the messages array with ``role="system"``.
    """

    model_config = ConfigDict(frozen=True)
    role: Literal["system"] = "system"


class ToolResultMessage(Message):
    """The result of a tool invocation, returned to the LLM on a subsequent turn.

    Pairs a ``tool_call_id`` (the id of the ``ToolCall`` returned by the
    LLM on the previous turn) with the tool's textual output. The
    Anthropic adapter translates this into a **user** message carrying a
    ``tool_result`` block (Anthropic's Messages API has no ``tool``
    role); the OpenAI-compat adapter sends it as an assistant message
    with ``role="tool"``.

    ``tool_call_id`` is the field that lets the provider match each
    result back to the specific ``ToolUseBlock`` / ``tool_call`` it
    answers; the adapter MUST preserve it verbatim.
    """

    model_config = ConfigDict(frozen=True)
    role: Literal["tool"] = "tool"
    tool_call_id: str


# Discriminated union used by adapters that want static dispatch on role.
MessageUnion = Annotated[
    UserMessage | AssistantMessage | SystemMessage | ToolResultMessage,
    Field(discriminator="role"),
]

# Adapter used by ``Message.model_validate`` to dispatch on ``role`` to the
# right leaf class. Built once at import time so each call is a single
# ``validate_python`` invocation rather than a full schema rebuild.
_MESSAGE_UNION_ADAPTER: TypeAdapter[Any] = TypeAdapter(MessageUnion)


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
    "ToolResultMessage",
    "ToolSpec",
    "UserMessage",
]
