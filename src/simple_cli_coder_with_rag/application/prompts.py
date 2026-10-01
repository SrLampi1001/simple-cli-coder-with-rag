"""Prompt builders for the application-layer facade.

Currently exposes :func:`build_chat_messages` which composes the message
list handed to ``LLMClient.complete``. The third positional argument
(``recalled``) is accepted but unused in DO-03; DO-09 injects retrieved
context into the prompt here.
"""

from __future__ import annotations

from simple_cli_coder_with_rag.domain.messages import (
    Message,
    UserMessage,
)


def build_chat_messages(
    user_message: str,
    history: list[Message],
    recalled: list[str],
) -> list[Message]:
    """Return ``[...history, UserMessage(user_message)]``.

    Parameters
    ----------
    user_message:
        The text the user just submitted.
    history:
        Prior turns, in chronological order (oldest first). May be empty.
    recalled:
        Retrieved snippets from the vector store. Accepted for forward
        compatibility with DO-09; ignored here.

    Returns
    -------
    list[Message]
        A new list that ends with the new user message; the caller's
        ``history`` is not mutated.
    """
    del recalled  # unused in DO-03 — DO-09 will inject recall here
    return [*history, UserMessage(content=user_message)]


__all__ = ["build_chat_messages"]
