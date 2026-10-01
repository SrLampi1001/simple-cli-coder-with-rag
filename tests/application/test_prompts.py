"""Tests for ``build_chat_messages``.

Pinned by ``agent-development/03-agent-responds-baseline/tests.md``.
"""

from __future__ import annotations

from simple_cli_coder_with_rag.application.prompts import build_chat_messages
from simple_cli_coder_with_rag.domain.messages import (
    AssistantMessage,
    UserMessage,
)


def test_prompts_returns_history_plus_user() -> None:
    """History is preserved in order, with the new user message appended last."""
    history = [UserMessage(content="a"), AssistantMessage(content="b")]
    result = build_chat_messages("c", history=history, recalled=[])
    assert result == [
        UserMessage(content="a"),
        AssistantMessage(content="b"),
        UserMessage(content="c"),
    ]


def test_prompts_ignores_recalled_for_now() -> None:
    """``recalled`` is accepted but unused in DO-03 (DO-09 injects recall)."""
    result = build_chat_messages("hi", history=[], recalled=["x", "y"])
    assert result == [UserMessage(content="hi")]


def test_prompts_returns_user_message_only_when_history_empty() -> None:
    """Empty history + a user message yields just the user message."""
    result = build_chat_messages("hi", history=[], recalled=[])
    assert result == [UserMessage(content="hi")]
