"""``/learn`` command — compact the current session, chunk it, and report the count.

This is the user-facing surface of the DO-04 + DO-05 pipeline. The command:

1. Pulls ``session_id``, ``history``, and ``session_store`` off
   :class:`AppState`.
2. Persists any in-memory history messages to the session store
   (idempotent — skips messages already on disk).
3. Forwards ``session_id`` to :meth:`KnowledgeService.learn`, which
   compacts via the LLM, writes the JSON, and chunks the result.
4. Reports the result as a one-line ``"learned N chunks"`` message.

``LLMError`` and :class:`CompactionError` are caught here so a failed
``/learn`` does not bring down the REPL — the user can retry the same
command on the next prompt. Anything else (programming bug) still
propagates out so the user notices.
"""

from __future__ import annotations

from simple_cli_coder_with_rag.application.compactor import CompactionError
from simple_cli_coder_with_rag.domain.llm_client import LLMError
from simple_cli_coder_with_rag.presentation.commands import (
    CommandContext,
    CommandResult,
)


class LearnCommand:
    """``/learn``: compact the current session and store it."""

    name = "learn"
    summary = "Compact the current session and store it."

    def execute(self, context: CommandContext) -> CommandResult:
        knowledge = context.app_state.knowledge
        session_id = context.app_state.session_id
        history = context.app_state.history
        session_store = context.app_state.session_store
        if knowledge is None:
            return CommandResult(
                action="continue", message="learn failed: knowledge not configured"
            )

        # Persist any in-memory history that is not yet on disk. The REPL
        # does this on each chat turn in DO-04's contract; the idempotency
        # check protects against re-persisting on a repeated ``/learn``.
        if session_store is not None:
            existing = session_store.read(session_id)
            seen: set[tuple[str, str]] = {(m.role, m.content) for m in existing}
            for msg in history:
                key = (msg.role, msg.content)
                if key in seen:
                    continue
                session_store.append(session_id, msg)
                seen.add(key)

        try:
            count = knowledge.learn(session_id)
        except (LLMError, CompactionError) as exc:
            # Both failure modes — the LLM client blew up, or the LLM's
            # reply failed schema validation — are surfaced as a one-line
            # error message and the REPL keeps running. Anything else
            # (programming bug) still propagates out so the user notices.
            return CommandResult(action="continue", message=f"learn failed: {exc}")
        return CommandResult(action="continue", message=f"learned {count} chunks")


__all__ = ["LearnCommand"]
