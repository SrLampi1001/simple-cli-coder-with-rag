"""``/learn`` command — compact the current session and persist it as JSON.

This is the user-facing surface of the DO-04 pipeline. The command:

1. Pulls ``session_id`` and ``history`` off :class:`AppState`.
2. Forwards the snapshot of history to
   :meth:`KnowledgeService.learn`, which appends it to the session's
   ``.jsonl`` transcript and then asks the compactor to produce the
   ``.compacted.json`` document.
3. Reports the result as a single line. ``LLMError`` is caught here so a
   failed ``/learn`` does not bring down the REPL — the user can retry
   the same command on the next prompt.

The chunk-count message is a stub (``"learned 0 chunks"``); DO-05 will
replace it with the real count once the chunker lands.
"""

from __future__ import annotations

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
        if knowledge is None:
            return CommandResult(
                action="continue", message="learn failed: knowledge not configured"
            )
        try:
            knowledge.learn(session_id, list(history))
        except LLMError as exc:
            return CommandResult(action="continue", message=f"learn failed: {exc}")
        return CommandResult(action="continue", message="learned 0 chunks")


__all__ = ["LearnCommand"]
