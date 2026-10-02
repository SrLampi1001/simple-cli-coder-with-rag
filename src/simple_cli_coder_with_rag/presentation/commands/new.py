"""``/new`` command — start a fresh session id inside the same process.

DO-12 — the gap fix for the workflow test. ``/resume <id>`` and
``/chats`` cover continuing an existing session, but there was no
way to start a fresh conversation without restarting the REPL.
``/new`` fills that gap:

1. Generate a fresh ``session_id`` (UUIDv4 hex) via
   ``SessionStore.current_id()``.
2. Swap ``app_state.session_id`` to the fresh id so subsequent chat
   turns persist to the new ``<id>.jsonl``.
3. Clear ``app_state.history[:]`` so the LLM context starts empty.
4. Reset ``app_state.persisted_through`` to ``0`` so the cleared
   history is not treated as already-persisted.

The previous session's on-disk transcript is **untouched** — the
old messages are already in ``<old-id>.jsonl`` (the REPL persisted
them on every turn). The user can come back via
``/resume <old-id>`` at any point.
"""

from __future__ import annotations

from simple_cli_coder_with_rag.presentation.commands import (
    AppState,
    CommandContext,
    CommandResult,
)


class NewCommand:
    """``/new``: start a fresh session id (same REPL, clean slate)."""

    name = "new"
    summary = "Start a fresh chat session (same REPL, new id)."

    def execute(self, context: CommandContext) -> CommandResult:
        state: AppState = context.app_state
        store = state.session_store
        if store is None:
            return CommandResult(
                action="continue",
                message="No session store configured — `/new` is unavailable in this session.",
            )

        old_id = state.session_id
        new_id = store.current_id()
        state.session_id = new_id
        state.history.clear()
        state.persisted_through = 0

        message = f"started new session {new_id}"
        if old_id:
            message += f" (was {old_id})"
        message += "."
        return CommandResult(action="continue", message=message)


__all__ = ["NewCommand"]
