"""``/learn`` compaction pipeline: turn a chat transcript into a structured ``CompactedSession``.

The compactor is the application-layer seam between the chat history held
in memory (and mirrored on disk by :class:`SessionStore
<simple_cli_coder_with_rag.application.session_store.SessionStore>`)
and the structured JSON document the chunker / embedder / vector store
consume in DO-05..DO-07.

Pipeline (per ``compact`` call):

1. **Empty short-circuit.** If ``messages`` is empty, return a
   ``CompactedSession`` with ``summary="(empty session)"`` and empty
   ``errors`` / ``decisions`` *without* calling the LLM. This guarantees
   ``/learn`` on a fresh session is cheap and offline.
2. **Structured-output prompt.** Build a four-message prompt — system
   instruction, schema description, the session transcript, final reminder
   — and hand it to
   :class:`~simple_cli_coder_with_rag.domain.llm_client.LLMClient.complete`.
3. **Validation.** Parse the LLM reply as JSON and validate it through
   :class:`~simple_cli_coder_with_rag.domain.compacted.CompactedSession`.
   Any failure (``JSONDecodeError`` or ``pydantic.ValidationError``) is
   re-raised as :class:`CompactionError` so the REPL can surface a single,
   project-owned exception type.
4. **Identity stamp.** Override ``session_id`` and ``created_at`` with the
   values the caller passed in / we just computed — the model never
   decides these.

Architectural note: this module imports from :mod:`domain` only (no
:mod:`infrastructure`). The composition root resolves the compactor's
model name from
:class:`~simple_cli_coder_with_rag.infrastructure.settings.Settings`
and passes it in via the constructor; ``Settings`` itself does not leak
into the application layer.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pydantic import ValidationError

from simple_cli_coder_with_rag.domain.compacted import (
    CompactedSession,
    DecisionRecord,
    ErrorRecord,
)
from simple_cli_coder_with_rag.domain.llm_client import LLMClient
from simple_cli_coder_with_rag.domain.messages import Message

# Prompt fragments. Kept as module-level constants so the intent is greppable
# and so the helpers stay small.
_SYSTEM_INSTRUCTION = (
    "You are a session analyzer. Reply with ONLY a JSON object matching the "
    "schema below. No prose, no markdown fences, no commentary."
)

_SCHEMA_DESCRIPTION = (
    "Schema (respond with a single JSON object):\n"
    "{\n"
    '  "summary": "<one-paragraph description of the session>",\n'
    '  "errors": [\n'
    '    {"signature": "<id>", "message": "<text>", "occurrences": <int>=1}\n'
    "  ],\n"
    '  "decisions": [\n'
    '    {"summary": "<what>", "rationale": "<why>"}\n'
    "  ]\n"
    "}\n"
    "Use an empty list for categories with no entries. "
    "Every item must satisfy the constraints above."
)

_FINAL_INSTRUCTION = "Respond with ONLY the JSON object."

_EMPTY_SUMMARY = "(empty session)"


class CompactionError(Exception):
    """Raised when the LLM reply cannot be parsed into a ``CompactedSession``.

    Wraps the underlying ``pydantic.ValidationError`` or ``json.JSONDecodeError``
    via ``__cause__`` (and echoes the raw reply in the message) so the REPL
    has one project-owned exception type to handle.
    """


class Compactor:
    """Turn a session transcript into a structured ``CompactedSession``.

    The compactor is stateless apart from the dependencies it was built
    with — it does not cache LLM responses, does not keep a session index,
    and never touches disk. ``KnowledgeService`` is the only place that
    wires the compactor to a ``SessionStore``.
    """

    def __init__(self, llm: LLMClient, compactor_model: str) -> None:
        self._llm = llm
        self._compactor_model = compactor_model

    def compact(self, session_id: str, messages: list[Message]) -> CompactedSession:
        """Return a ``CompactedSession`` for ``messages``.

        Empty ``messages`` short-circuits to ``(empty session)`` without
        contacting the LLM. Non-empty transcripts are sent through the
        structured-output prompt and validated; a malformed reply raises
        :class:`CompactionError`.
        """
        if not messages:
            return CompactedSession(
                session_id=session_id,
                created_at=datetime.now(UTC),
                summary=_EMPTY_SUMMARY,
            )

        prompt_messages = _build_compaction_messages(messages)
        raw_reply = self._llm.complete(prompt_messages, model=self._compactor_model)

        try:
            parsed = CompactedSession.model_validate_json(raw_reply)
        except (ValidationError, json.JSONDecodeError) as exc:
            raise CompactionError(
                f"compactor received an unparseable reply: {raw_reply!r}"
            ) from exc

        # The model decides ``summary`` / ``errors`` / ``decisions``; we
        # always override ``session_id`` and ``created_at`` so the on-disk
        # JSON cannot drift away from the id that owned it.
        parsed.session_id = session_id
        parsed.created_at = datetime.now(UTC)
        return parsed


def _build_compaction_messages(messages: list[Message]) -> list[Message]:
    """Assemble the four-message structured-output prompt for ``messages``.

    The shape — system, schema, transcript, final reminder — matches the
    recipe in this module's docstring. Each transcript message is
    serialised with ``model_dump_json()`` and prefixed with its role so
    the LLM has a stable, easy-to-parse transcript view (independent of
    Pydantic-internal whitespace).
    """
    from simple_cli_coder_with_rag.domain.messages import (  # local: avoid top-level cycle
        SystemMessage,
        UserMessage,
    )

    role_prefix = {"user": "USER", "assistant": "ASSISTANT", "system": "SYSTEM"}

    transcript_lines = []
    for msg in messages:
        prefix = role_prefix.get(msg.role, msg.role.upper())
        transcript_lines.append(f"{prefix}: {msg.model_dump_json()}")
    transcript_text = "\n".join(transcript_lines)

    return [
        SystemMessage(content=_SYSTEM_INSTRUCTION),
        UserMessage(content=_SCHEMA_DESCRIPTION),
        UserMessage(content=f"Session transcript:\n{transcript_text}"),
        UserMessage(content=_FINAL_INSTRUCTION),
    ]


__all__ = [
    # Re-export the schema types so ``Compactor`` users can ``from
    # simple_cli_coder_with_rag.application.compactor import CompactedSession``
    # if they prefer a single import surface.
    "CompactedSession",
    "CompactionError",
    "Compactor",
    "DecisionRecord",
    "ErrorRecord",
    # Internal helpers are exported for tests that want to introspect the
    # prompt shape directly; production code should treat them as private.
    "_build_compaction_messages",
]
