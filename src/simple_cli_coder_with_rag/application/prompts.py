"""Prompt builders for the application-layer facade.

Exposes :func:`build_chat_messages` which composes the message list
handed to ``LLMClient.complete``. After DO-09, the function honours a
``recalled`` parameter — a list of chunk texts retrieved from the
vector store before the user's turn — and injects them as a single
``SystemMessage`` at the **head** of the messages list. The system
message position is deliberate: the LLM sees the recalled context
before the user's request, so the answer is shaped by it.

Format::

    SystemMessage(content=(
        "The following context may be relevant:\n\n"
        + "\n\n---\n\n".join(recalled)
    ))

Multiple recalled chunks are joined with a ``---`` separator; a single
chunk produces no separator (matches the ``test_single_recalled_chunk_uses_no_separator``
contract).
"""

from __future__ import annotations

from simple_cli_coder_with_rag.domain.messages import (
    Message,
    SystemMessage,
    UserMessage,
)

_RECALL_HEADER = "The following context may be relevant:\n\n"
_RECALL_SEPARATOR = "\n\n---\n\n"


def build_chat_messages(
    user_message: str,
    history: list[Message],
    recalled: list[str],
) -> list[Message]:
    """Return ``[SystemMessage(recalled)? , ...history, UserMessage(user_message)]``.

    Parameters
    ----------
    user_message:
        The text the user just submitted.
    history:
        Prior turns, in chronological order (oldest first). May be empty.
    recalled:
        Retrieved snippets from the vector store (DO-09). When
        non-empty, a single ``SystemMessage`` summarising them is
        prepended to the messages list. When empty (or ``[]``), no
        system message is added — the function degenerates to
        ``[*history, UserMessage(user_message)]``.

    Returns
    -------
    list[Message]
        A new list that ends with the new user message; the caller's
        ``history`` is not mutated.
    """
    messages: list[Message] = []
    if recalled:
        content = _RECALL_HEADER + _RECALL_SEPARATOR.join(recalled)
        messages.append(SystemMessage(content=content))
    messages.extend(history)
    messages.append(UserMessage(content=user_message))
    return messages


__all__ = ["build_chat_messages"]
