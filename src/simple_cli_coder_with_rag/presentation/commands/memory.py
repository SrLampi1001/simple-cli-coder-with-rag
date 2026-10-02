"""``/memory`` command — show the active conversation window.

DO-12 — backing the TL acceptance criterion "10 most recent
user/assistant messages". The command reads ``AppState`` directly:

* ``session_id`` — short + long form of the active session id.
* ``history`` — the messages currently held in the REPL's rolling
  window (the ones sent to the LLM on every chat turn).

There is no LLM call, no session-store read, no summary. The
readout is bounded to the last user / assistant pair — anything
older has already been trimmed from the active history.
"""

from __future__ import annotations

from simple_cli_coder_with_rag.domain.messages import AssistantMessage, UserMessage
from simple_cli_coder_with_rag.presentation.commands import (
    AppState,
    CommandContext,
    CommandResult,
)

# Truncation length for the ``last user:`` / ``last assistant:``
# lines. The exact value is pinned by
# ``agent-development/12-session-memory-and-saved-chats/contracts.md``
# so the command's contract is regression-guarded by
# ``tests/presentation/commands/test_memory.py``.
_TRUNCATE_AT = 60
_TRUNCATION_MARKER = "\u2026"  # "..." (single Unicode ellipsis char)


class MemoryCommand:
    """``/memory``: show the active conversation window."""

    name = "memory"
    summary = "Show the active conversation window."

    def execute(self, context: CommandContext) -> CommandResult:
        state: AppState = context.app_state

        if state.session_store is None and not state.session_id:
            return CommandResult(
                action="continue",
                message=("No active session yet — type a chat line to start one."),
            )

        short_id = state.session_id[:8] if state.session_id else "(none)"
        max_turns = state.settings.int_history_cap if state.settings is not None else 10
        message_count = len(state.history)
        kept_turns = message_count // 2

        last_user = _last_of_role(state.history, "user")
        last_assistant = _last_of_role(state.history, "assistant")

        lines = [
            f"session:    {short_id}",
            f"turns:      {kept_turns} / {max_turns}",
            f"messages:   {message_count}",
            f"last user:  {_truncate(last_user)}",
            f"last assistant: {_truncate(last_assistant)}",
        ]
        return CommandResult(action="continue", message="\n".join(lines))


def _last_of_role(messages: list, role: str) -> str:
    """Return the content of the last message with ``role``, or the empty-string sentinel."""
    for msg in reversed(messages):
        if isinstance(msg, (UserMessage, AssistantMessage)) and msg.role == role:
            return msg.content
    return "(no messages yet)"


def _truncate(content: str) -> str:
    """Truncate ``content`` to ``_TRUNCATE_AT`` chars and append the ellipsis marker.

    Strings that fit are returned verbatim (no marker). The sentinel
    ``"(no messages yet)"`` is also returned verbatim — it is the
    fixed-length fallback when ``_last_of_role`` finds no match.
    """
    if len(content) <= _TRUNCATE_AT:
        return content
    return content[:_TRUNCATE_AT] + _TRUNCATION_MARKER


__all__ = ["MemoryCommand"]
