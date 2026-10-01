"""Application-layer Facade for the LLM-powered chat loop and RAG hooks.

:class:`KnowledgeService` is the single seam between the REPL (presentation
layer) and the LLM-backed ``LLMClient`` Protocol (domain layer). DO-03 only
implements ``chat``; ``learn`` and ``recall`` are stubs that DO-04 and DO-09
fill in respectively.

Architectural notes:

* This module imports from ``domain`` only — no vendor SDKs and no
  ``infrastructure`` modules. The composition root in ``cli.py`` is the
  only place that builds a ``KnowledgeService`` and resolves the active
  ``chat_model`` from :class:`~infrastructure.settings.Settings`.
* ``LLMError`` is **not** caught here. The REPL catches it and prints a
  one-line message; any wrapping would only duplicate work and risk
  swallowing the wrong exception type.
"""

from __future__ import annotations

from simple_cli_coder_with_rag.application.prompts import build_chat_messages
from simple_cli_coder_with_rag.domain.llm_client import LLMClient
from simple_cli_coder_with_rag.domain.messages import Message


class KnowledgeService:
    """Facade exposing ``chat`` / ``learn`` / ``recall`` to the REPL."""

    def __init__(self, llm: LLMClient, chat_model: str) -> None:
        self._llm = llm
        self._chat_model = chat_model

    def chat(self, user_message: str, history: list[Message]) -> str:
        """Send ``user_message`` (with prior ``history``) to the LLM and return the reply.

        ``LLMError`` propagates verbatim so the caller (the REPL) can decide
        how to surface it.
        """
        messages = build_chat_messages(user_message, history, recalled=[])
        return self._llm.complete(messages, model=self._chat_model)

    def learn(self, session_id: str) -> None:
        """Compact ``session_id`` into a JSON file. Filled in by DO-04."""
        raise NotImplementedError("DO-04")

    def recall(self, query: str) -> list[str]:
        """Return the most relevant chunks for ``query``. Filled in by DO-09."""
        return []


__all__ = ["KnowledgeService"]
