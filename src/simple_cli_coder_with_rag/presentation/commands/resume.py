"""``/resume <session-id>`` command — load the last 10 messages of a saved session.

DO-12 — backing the TL acceptance criterion
"``/resume <session-id>`` continues one [saved chat], while active
model context remains capped at the 10 most recent user/assistant
messages".

The command is deliberately minimal:

1. Read the saved transcript via ``SessionStore.read(<id>)``.
2. Take the **last** ``2 * int_history_cap`` messages (= the
   configured number of user/assistant turns).
3. Replace ``app_state.history[:]`` with that slice.
4. Update ``app_state.session_id = <id>`` so subsequent chat
   turns persist to the resumed session.
5. Advance ``app_state.persisted_through`` so the loaded
   messages are never re-appended.
6. **Print the loaded messages inline** — the same shape
   ``/memory`` produces, so the user immediately sees the
   conversation they just switched to (OpenCode-style UX).

There is **no** LLM call, **no** compactor invocation, **no**
summary generation, and **no** blocking pause. ``NEW_REQUIREMENTS.md``
§3 says ``/resume`` is simply a way to "continue one" — the
command returns the instant the file is read.
"""

from __future__ import annotations

from simple_cli_coder_with_rag.presentation.commands import (
    AppState,
    CommandContext,
    CommandResult,
)
from simple_cli_coder_with_rag.presentation.commands.memory import (
    format_messages_for_display,
)

# DO-12 fallback cap when ``app_state.settings`` is ``None``.
_DEFAULT_HISTORY_CAP_TURNS = 10


class ResumeCommand:
    """``/resume <session-id>``: load a saved chat and continue it."""

    name = "resume"
    summary = "Resume a saved chat session by id (prints the loaded messages)."

    def execute(self, context: CommandContext) -> CommandResult:
        state: AppState = context.app_state
        store = state.session_store
        session_id = context.args.strip()
        if not session_id:
            return CommandResult(action="continue", message="usage: /resume <session-id>")
        if store is None:
            return CommandResult(
                action="continue",
                message="No session store configured — `/resume` is unavailable in this session.",
            )

        transcript = store.read(session_id)
        if not transcript:
            return CommandResult(
                action="continue",
                message=f"unknown session '{session_id}'. Run `/chats` to list.",
            )

        capacity = self._resolve_history_cap(state)
        last_n = transcript[-capacity:]
        # Replace the active history in place — the REPL keeps a
        # reference, so the change is seen immediately. ``last_n``
        # may be shorter than ``capacity`` (a transcript that is
        # already below the cap); the slice is verbatim.
        state.history[:] = last_n
        state.session_id = session_id
        # All loaded messages are already on disk; advance the
        # REPL's persistence pointer so they are never re-appended.
        state.persisted_through = len(state.history)

        # Print the loaded messages inline so the user immediately
        # sees the conversation they just switched to. Same shape
        # as ``/memory`` — single formatter keeps the two surfaces
        # in sync.
        header = f"resumed {session_id} ({len(last_n)} of {len(transcript)} messages loaded):"
        body = format_messages_for_display(last_n)
        return CommandResult(action="continue", message=f"{header}\n{body}")

    @staticmethod
    def _resolve_history_cap(state: AppState) -> int:
        """Return the message cap (= turns * 2) to load on resume.

        Reads ``Settings.int_history_cap`` (in *turns*). Falls back to
        ``_DEFAULT_HISTORY_CAP_TURNS`` (= ``10``) when ``settings`` is
        ``None`` so legacy unit tests that build a bare ``AppState``
        keep passing.
        """
        cap_turns = (
            state.settings.int_history_cap
            if state.settings is not None
            else _DEFAULT_HISTORY_CAP_TURNS
        )
        return 2 * cap_turns


__all__ = ["ResumeCommand"]
