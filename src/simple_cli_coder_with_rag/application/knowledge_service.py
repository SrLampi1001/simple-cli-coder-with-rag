"""Application-layer Facade for the LLM-powered chat loop and RAG hooks.

:class:`KnowledgeService` is the single seam between the REPL (presentation
layer) and the LLM-backed ``LLMClient`` Protocol (domain layer). It
exposes three operations:

* :meth:`KnowledgeService.chat` — plain chat turn (DO-03).
* :meth:`KnowledgeService.learn` — append the in-memory history to the
  on-disk session, compact it via the compactor, and persist the result
  (DO-04).
* :meth:`KnowledgeService.recall` — return relevant chunks; a stub until
  DO-09 wires the vector store.

Architectural notes:

* This module imports from :mod:`domain` and from other ``application``
  modules (the compactor and the session store). It does **not** import
  from :mod:`infrastructure` — no vendor SDKs and no ``Settings`` type.
  The composition root in :mod:`simple_cli_coder_with_rag.cli` resolves
  ``chat_model`` / ``compactor_model`` from ``Settings`` and passes the
  resolved strings into the constructor.
* ``LLMError`` is **not** caught here. The REPL catches it and prints a
  one-line message; any wrapping would only duplicate work and risk
  swallowing the wrong exception type.
* ``CompactionError`` is likewise propagated verbatim so the REPL sees a
  single failure type.
"""

from __future__ import annotations

from simple_cli_coder_with_rag.application.compactor import Compactor
from simple_cli_coder_with_rag.application.prompts import build_chat_messages
from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.domain.llm_client import LLMClient
from simple_cli_coder_with_rag.domain.messages import Message


class KnowledgeService:
    """Facade exposing ``chat`` / ``learn`` / ``recall`` to the REPL."""

    def __init__(
        self,
        llm: LLMClient,
        chat_model: str,
        session_store: SessionStore,
        compactor: Compactor,
    ) -> None:
        self._llm = llm
        self._chat_model = chat_model
        self._session_store = session_store
        self._compactor = compactor

    def chat(self, user_message: str, history: list[Message]) -> str:
        """Send ``user_message`` (with prior ``history``) to the LLM and return the reply.

        ``LLMError`` propagates verbatim so the caller (the REPL) can decide
        how to surface it.
        """
        messages = build_chat_messages(user_message, history, recalled=[])
        return self._llm.complete(messages, model=self._chat_model)

    def learn(self, session_id: str, messages: list[Message]) -> None:
        """Persist ``messages`` to disk and write the compacted JSON for ``session_id``.

        Algorithm:

        1. Read the existing on-disk transcript (returns ``[]`` on a fresh
           session).
        2. Append each message in ``messages`` whose ``(role, content)`` is
           not already present. This is the idempotency hook — repeated
           ``/learn`` calls do not duplicate lines.
        3. Re-read the full transcript (existing + newly appended) and ask
           the compactor for a structured :class:`CompactedSession`. The
           compactor short-circuits on an empty list without contacting the
           LLM.
        4. Persist the compacted document via ``write_compacted`` (which
           overwrites any prior file — the second ``/learn`` replaces the
           first).

        ``LLMError`` and :class:`~simple_cli_coder_with_rag.application.compactor.CompactionError`
        propagate verbatim.
        """
        existing = self._session_store.read(session_id)
        seen: set[tuple[str, str]] = {(m.role, m.content) for m in existing}
        for msg in messages:
            key = (msg.role, msg.content)
            if key in seen:
                continue
            self._session_store.append(session_id, msg)
            seen.add(key)

        all_messages = self._session_store.read(session_id)
        compacted = self._compactor.compact(session_id, all_messages)
        self._session_store.write_compacted(session_id, compacted)

    def recall(self, query: str) -> list[str]:
        """Return the most relevant chunks for ``query``. Filled in by DO-09."""
        return []


__all__ = ["KnowledgeService"]
