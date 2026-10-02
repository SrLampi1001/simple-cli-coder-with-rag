"""Tests for ``build_chat_messages`` after DO-09 injects recalled context.

Pinned by ``agent-development/09-recall-integration/tests.md`` (the
``recalled`` parameter shape) and updated in
``agent-development/13-rag-over-documents-supabase/tests.md`` to the
``(source, chunk_index, text)`` tuple shape. DO-13 also added the
"LLM-decides retrieval" header with the four decision rules.

The function signature is unchanged; the behaviour now reflects the
``recalled`` parameter as a list of tuples rather than a list of
plain strings. Empty ``recalled`` still degenerates to
``[*history, UserMessage(user_message)]`` — the backward-compatible
path.
"""

from __future__ import annotations

from simple_cli_coder_with_rag.application.prompts import build_chat_messages
from simple_cli_coder_with_rag.domain.messages import (
    AssistantMessage,
    SystemMessage,
    UserMessage,
)


def test_with_recalled_injects_system_message() -> None:
    """Recalled chunks become a single ``SystemMessage`` at the head of the list.

    Each tuple is ``(source, chunk_index, text)``; the system message
    formats each chunk with the LLM-decides decision rules and a
    ``[Source: ..., chunk #N]`` attribution.
    """
    result = build_chat_messages(
        "q",
        [],
        [("foo.md", 0, "a"), ("foo.md", 1, "b")],
    )

    assert result == [
        SystemMessage(
            content=(
                "You have access to the following context from the user's "
                "loaded documents and previous sessions.\n\n"
                "Decision rules:\n"
                "  - Use the context when the question references or requires "
                "specific information from the user's documents or previous sessions.\n"
                "  - If the question can be answered without the context, answer "
                "from your general knowledge.\n"
                "  - If the question requires specific document content that was "
                "NOT retrieved, say you don't have enough information rather than "
                "guessing.\n"
                "  - When you use the context, mention which source(s) you drew from.\n\n"
                "Context:\n\n"
                "[Source: foo.md, chunk #0]\na\n\n---\n\n"
                "[Source: foo.md, chunk #1]\nb"
            )
        ),
        UserMessage(content="q"),
    ]


def test_with_empty_recalled_no_system_message() -> None:
    """Empty ``recalled`` yields just the user message — no extra ``SystemMessage``."""
    result = build_chat_messages("q", [], [])

    assert result == [UserMessage(content="q")]


def test_recalled_preserves_history_order() -> None:
    """History appears after the recalled system message and before the new user turn."""
    history = [UserMessage(content="p"), AssistantMessage(content="r")]
    result = build_chat_messages("q", history, [("foo.md", 0, "a")])

    assert result == [
        SystemMessage(
            content=(
                "You have access to the following context from the user's "
                "loaded documents and previous sessions.\n\n"
                "Decision rules:\n"
                "  - Use the context when the question references or requires "
                "specific information from the user's documents or previous sessions.\n"
                "  - If the question can be answered without the context, answer "
                "from your general knowledge.\n"
                "  - If the question requires specific document content that was "
                "NOT retrieved, say you don't have enough information rather than "
                "guessing.\n"
                "  - When you use the context, mention which source(s) you drew from.\n\n"
                "Context:\n\n"
                "[Source: foo.md, chunk #0]\na"
            )
        ),
        UserMessage(content="p"),
        AssistantMessage(content="r"),
        UserMessage(content="q"),
    ]


def test_single_recalled_chunk_uses_no_separator() -> None:
    """A single recalled chunk yields the system message without the ``---`` separator."""
    result = build_chat_messages("q", [], [("foo.md", 0, "only")])

    assert result == [
        SystemMessage(
            content=(
                "You have access to the following context from the user's "
                "loaded documents and previous sessions.\n\n"
                "Decision rules:\n"
                "  - Use the context when the question references or requires "
                "specific information from the user's documents or previous sessions.\n"
                "  - If the question can be answered without the context, answer "
                "from your general knowledge.\n"
                "  - If the question requires specific document content that was "
                "NOT retrieved, say you don't have enough information rather than "
                "guessing.\n"
                "  - When you use the context, mention which source(s) you drew from.\n\n"
                "Context:\n\n"
                "[Source: foo.md, chunk #0]\nonly"
            )
        ),
        UserMessage(content="q"),
    ]


def test_recalled_with_full_history_and_user() -> None:
    """End-to-end: full structure with history, recall, and the new user turn."""
    history = [
        UserMessage(content="earlier"),
        AssistantMessage(content="reply"),
    ]
    result = build_chat_messages(
        "now",
        history,
        [("foo.md", 0, "ctx-1"), ("foo.md", 1, "ctx-2")],
    )

    assert result == [
        SystemMessage(
            content=(
                "You have access to the following context from the user's "
                "loaded documents and previous sessions.\n\n"
                "Decision rules:\n"
                "  - Use the context when the question references or requires "
                "specific information from the user's documents or previous sessions.\n"
                "  - If the question can be answered without the context, answer "
                "from your general knowledge.\n"
                "  - If the question requires specific document content that was "
                "NOT retrieved, say you don't have enough information rather than "
                "guessing.\n"
                "  - When you use the context, mention which source(s) you drew from.\n\n"
                "Context:\n\n"
                "[Source: foo.md, chunk #0]\nctx-1\n\n---\n\n"
                "[Source: foo.md, chunk #1]\nctx-2"
            )
        ),
        UserMessage(content="earlier"),
        AssistantMessage(content="reply"),
        UserMessage(content="now"),
    ]


def test_recalled_omits_source_attribution_when_source_empty() -> None:
    """Session chunks (no source) format with an empty source field — backward compat.

    Session-compacted chunks have ``source == ""`` and
    ``chunk_index == 0`` (the new ``Chunk`` schema defaults). The
    prompt formats them as ``[Source: , chunk #0]\\n<text>`` which
    the LLM treats as an "anonymous chunk" — the same chunk it
    would have seen before DO-13, just with an explicit empty
    attribution.
    """
    result = build_chat_messages("q", [], [("", 0, "session text")])

    assert result == [
        SystemMessage(
            content=(
                "You have access to the following context from the user's "
                "loaded documents and previous sessions.\n\n"
                "Decision rules:\n"
                "  - Use the context when the question references or requires "
                "specific information from the user's documents or previous sessions.\n"
                "  - If the question can be answered without the context, answer "
                "from your general knowledge.\n"
                "  - If the question requires specific document content that was "
                "NOT retrieved, say you don't have enough information rather than "
                "guessing.\n"
                "  - When you use the context, mention which source(s) you drew from.\n\n"
                "Context:\n\n"
                "[Source: , chunk #0]\nsession text"
            )
        ),
        UserMessage(content="q"),
    ]
