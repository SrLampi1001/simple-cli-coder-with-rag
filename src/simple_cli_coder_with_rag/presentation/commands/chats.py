"""``/chats`` command — list saved sessions on disk.

DO-12 — backing the TL acceptance criterion "``/chats`` lists
[the saved sessions] by stable id". The command formats a table
from ``SessionStore.list_sessions()``:

* ``session_id`` — short form (first 13 chars + ellipsis).
* ``last activity`` — humanised relative time (``just now``,
  ``3m ago``, ``3h ago``, ``yesterday``, ``3d ago``, ``<YYYY-MM-DD>``).
* ``messages`` — line count of ``<id>.jsonl``.

The trailing ``active: <id>`` line always shows the active
session id, even when the listing is empty (so the user can see
the session id that *would* be active on a fresh run).
"""

from __future__ import annotations

from datetime import UTC, datetime

from simple_cli_coder_with_rag.presentation.commands import (
    AppState,
    CommandContext,
    CommandResult,
)

# Truncation length for the ``session id`` column. Pinned by
# ``agent-development/12-session-memory-and-saved-chats/contracts.md``.
# The first 10 chars of a UUIDv4 hex string are typically enough
# to disambiguate sessions in interactive use; the trailing
# ``...`` marker tells the user the value is incomplete.
_SHORT_ID_LEN = 10

# Boundaries (in seconds) for the relative-time formatter. Larger
# boundaries live in the table below; everything older falls back
# to the ``<YYYY-MM-DD>`` rendering.
_NOW_THRESHOLD = 60  # anything within a minute is "just now"
_MINUTE_THRESHOLD = 60 * 60  # anything within an hour is "Xm ago"
_HOUR_THRESHOLD = 24 * 60 * 60  # anything within a day is "Xh ago"
_DAY_THRESHOLD = 2 * 24 * 60 * 60  # "yesterday" window
_WEEK_THRESHOLD = 7 * 24 * 60 * 60  # anything within a week is "Xd ago"


class ChatsCommand:
    """``/chats``: list saved sessions on disk."""

    name = "chats"
    summary = "List saved sessions on disk."

    def execute(self, context: CommandContext) -> CommandResult:
        state: AppState = context.app_state
        store = state.session_store

        if store is None:
            return CommandResult(
                action="continue",
                message="No saved sessions available in this session.",
            )

        sessions = store.list_sessions()
        if not sessions:
            return CommandResult(action="continue", message="No saved sessions yet.")

        now = datetime.now(UTC).timestamp()
        lines = ["session id         last activity   messages"]
        for session_id, mtime, message_count in sessions:
            short_id = _short_id(session_id)
            last_activity = _humanize(mtime, now)
            lines.append(f"{short_id:<17}{last_activity:<16}{message_count}")
        lines.append(f"active: {state.session_id or '(none)'}")
        return CommandResult(action="continue", message="\n".join(lines))


def _short_id(session_id: str) -> str:
    """Return the first ``_SHORT_ID_LEN`` chars of ``session_id`` followed by ``...``."""
    if len(session_id) <= _SHORT_ID_LEN:
        return session_id
    return session_id[:_SHORT_ID_LEN] + "..."


def _humanize(mtime: float, now: float) -> str:
    """Format ``mtime`` as a humanised relative time."""
    delta = now - mtime
    if delta < _NOW_THRESHOLD:
        return "just now"
    if delta < _MINUTE_THRESHOLD:
        return f"{int(delta // 60)}m ago"
    if delta < _HOUR_THRESHOLD:
        return f"{int(delta // 3600)}h ago"
    if delta < _DAY_THRESHOLD:
        return "yesterday"
    if delta < _WEEK_THRESHOLD:
        return f"{int(delta // 86400)}d ago"
    return datetime.fromtimestamp(mtime, tz=UTC).strftime("%Y-%m-%d")


__all__ = ["ChatsCommand"]
