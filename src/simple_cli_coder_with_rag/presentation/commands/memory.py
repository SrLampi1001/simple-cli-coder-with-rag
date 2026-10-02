"""``/memory`` command — show the active conversation window.

DO-12 — backing the TL acceptance criterion "10 most recent
user/assistant messages". The command reads ``AppState`` directly:

* ``session_id`` — the **full** UUIDv4 hex (32 chars), so the user
  can copy-paste it into ``/resume <id>``. Showing a truncated
  short id breaks the workflow: ``/resume <truncated>`` does not
  resolve to any saved session.
* ``history`` — the messages currently held in the REPL's rolling
  window (the ones sent to the LLM on every chat turn).

There is no LLM call, no session-store read, no summary. The
readout is bounded to the last user / assistant pair — anything
older has already been trimmed from the active history.

The ``_last_of_role`` helper filters on ``msg.role`` (a field on
the base ``Message`` class) rather than ``isinstance`` against the
leaf subclasses. ``SessionStore.read`` returns base ``Message``
instances after a ``/resume``, so a strict leaf-class check would
silently miss every loaded message and print ``(no messages yet)``.
"""

from __future__ import annotations

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

# Length of the short-id preview shown above the full id. The
# short id is informational only — the full id is the authoritative
# value the user copies into ``/resume <id>``.
_SHORT_ID_LEN = 8


class MemoryCommand:
    """``/memory``: show the active conversation window."""

    name = "memory"
    summary = "Show the active conversation window."

    def execute(self, context: CommandContext) -> CommandResult:
        state: AppState = context.app_state

        if not state.session_id:
            return CommandResult(
                action="continue",
                message="No active session yet — type a chat line to start one.",
            )

        full_id = state.session_id
        short_id = full_id[:_SHORT_ID_LEN] if len(full_id) >= _SHORT_ID_LEN else full_id
        max_turns = state.settings.int_history_cap if state.settings is not None else 10
        message_count = len(state.history)
        kept_turns = message_count // 2

        last_user = _last_of_role(state.history, "user")
        last_assistant = _last_of_role(state.history, "assistant")

        lines = [
            f"session:    {full_id}",
            f"  (short:   {short_id})",
            f"turns:      {kept_turns} / {max_turns}",
            f"messages:   {message_count}",
            f"last user:  {_truncate(last_user)}",
            f"last assistant: {_truncate(last_assistant)}",
        ]
        return CommandResult(action="continue", message="\n".join(lines))


def _last_of_role(messages: list, role: str) -> str:
    """Return the content of the last message with ``role``, or the empty-string sentinel.

    Filters on ``msg.role`` (a base ``Message`` field) so base
    ``Message`` instances returned by ``SessionStore.read`` are
    matched as well as leaf ``UserMessage`` / ``AssistantMessage``
    instances built by the chat loop.
    """
    for msg in reversed(messages):
        if getattr(msg, "role", None) == role:
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
