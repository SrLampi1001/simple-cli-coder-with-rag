"""Prompt builders for the application-layer facade.

Exposes :func:`build_chat_messages` which composes the message list
handed to ``LLMClient.complete``.

After DO-09 the function honours a ``recalled`` parameter. DO-13
extends the parameter to a list of ``(source, chunk_index, text)``
tuples so the LLM sees **source attribution** alongside the
retrieved content and is steered by an explicit "LLM-decides
retrieval" header. The four pinned decision rules tell the LLM:

* Use the context when the question references or requires
  specific information from the user's documents or previous
  sessions.
* If the question can be answered without the context, answer
  from general knowledge.
* If the question requires specific document content that was NOT
  retrieved, say so rather than guess.
* When the LLM does use the context, mention the source(s).

The "LLM-decides" framing is a system-prompt contract — there is no
Python branch that forbids generation when retrieval returns no
chunks. The fallback (``recalled == []``) just omits the
``SystemMessage`` entirely and the LLM answers from its general
knowledge, exactly as if no RAG was wired in.

Format::

    SystemMessage(content=(
        _RECALL_HEADER
        + _RECALL_SEPARATOR.join(
            _RECALL_CHUNK_FORMAT.format(source=s, chunk_index=i, content=t)
            for s, i, t in recalled
        )
    ))

A single recalled chunk produces no separator (the ``join`` returns
the formatted string verbatim).
"""

from __future__ import annotations

from simple_cli_coder_with_rag.domain.messages import (
    Message,
    SystemMessage,
    UserMessage,
)

# LLM-decides retrieval header. The four decision rules are pinned
# by the DO-13 behavioural contract — every chat prompt that has
# recalled context includes this block, and the LLM is expected to
# follow it. There is NO Python branch that enforces the rules; the
# design is "let the LLM decide" (per the OBJECTIVES framing).
_RECALL_HEADER = (
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
)

# Per-chunk format. ``{source}`` is the file path (or empty for
# session chunks); ``{chunk_index}`` is the zero-based position in
# the source; ``{content}`` is the chunk text.
_RECALL_CHUNK_FORMAT = "[Source: {source}, chunk #{chunk_index}]\n{content}"

# Separator between consecutive chunks in the system message.
_RECALL_SEPARATOR = "\n\n---\n\n"


def build_chat_messages(
    user_message: str,
    history: list[Message],
    recalled: list[tuple[str, int, str]],
) -> list[Message]:
    """Return ``[SystemMessage(recalled)?, ...history, UserMessage(user_message)]``.

    Parameters
    ----------
    user_message:
        The text the user just submitted.
    history:
        Prior turns, in chronological order (oldest first). May be empty.
    recalled:
        Retrieved snippets from the vector store. Each entry is a
        ``(source, chunk_index, text)`` tuple — ``source`` is the
        file path (or empty for session chunks); ``chunk_index`` is
        the zero-based position in the source; ``text`` is the chunk
        text. When non-empty, a single ``SystemMessage`` carrying
        the LLM-decides header + the formatted chunks is prepended
        to the messages list. When empty (or ``[]``), no system
        message is added — the function degenerates to
        ``[*history, UserMessage(user_message)]``.

    Returns
    -------
    list[Message]
        A new list that ends with the new user message; the caller's
        ``history`` is not mutated.
    """
    messages: list[Message] = []
    if recalled:
        formatted = [
            _RECALL_CHUNK_FORMAT.format(source=source, chunk_index=chunk_index, content=text)
            for source, chunk_index, text in recalled
        ]
        content = _RECALL_HEADER + _RECALL_SEPARATOR.join(formatted)
        messages.append(SystemMessage(content=content))
    messages.extend(history)
    messages.append(UserMessage(content=user_message))
    return messages


__all__ = ["build_chat_messages"]
