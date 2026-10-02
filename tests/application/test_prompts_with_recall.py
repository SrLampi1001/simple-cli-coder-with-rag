"""Tests for ``build_chat_messages`` after DO-09 injects recalled context.

Pinned by ``agent-development/09-recall-integration/tests.md``. Replaces
``test_prompts.py`` from DO-03 — the function signature is unchanged;
the behaviour now reflects the ``recalled`` parameter.
"""

from __future__ import annotations

from simple_cli_coder_with_rag.application.prompts import build_chat_messages
from simple_cli_coder_with_rag.domain.messages import (
    AssistantMessage,
    SystemMessage,
    UserMessage,
)


def test_with_recalled_injects_system_message() -> None:
    """Recalled chunks become a single ``SystemMessage`` at the head of the list."""
    result = build_chat_messages("q", [], ["a", "b"])

    assert result == [
        SystemMessage(content="The following context may be relevant:\n\na\n\n---\n\nb"),
        UserMessage(content="q"),
    ]


def test_with_empty_recalled_no_system_message() -> None:
    """Empty ``recalled`` yields just the user message — no extra ``SystemMessage``."""
    result = build_chat_messages("q", [], [])

    assert result == [UserMessage(content="q")]


def test_recalled_preserves_history_order() -> None:
    """History appears after the recalled system message and before the new user turn."""
    history = [UserMessage(content="p"), AssistantMessage(content="r")]
    result = build_chat_messages("q", history, ["a"])

    assert result == [
        SystemMessage(content="The following context may be relevant:\n\na"),
        UserMessage(content="p"),
        AssistantMessage(content="r"),
        UserMessage(content="q"),
    ]


def test_single_recalled_chunk_uses_no_separator() -> None:
    """A single recalled chunk yields the system message without the ``---`` separator."""
    result = build_chat_messages("q", [], ["only"])

    assert result == [
        SystemMessage(content="The following context may be relevant:\n\nonly"),
        UserMessage(content="q"),
    ]


def test_recalled_with_full_history_and_user() -> None:
    """End-to-end: full structure with history, recall, and the new user turn."""
    history = [
        UserMessage(content="earlier"),
        AssistantMessage(content="reply"),
    ]
    result = build_chat_messages("now", history, ["ctx-1", "ctx-2"])

    assert result == [
        SystemMessage(content="The following context may be relevant:\n\nctx-1\n\n---\n\nctx-2"),
        UserMessage(content="earlier"),
        AssistantMessage(content="reply"),
        UserMessage(content="now"),
    ]
