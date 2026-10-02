"""``/memory`` command — print the last 10 messages in the active window.

DO-12 / NEW_REQUIREMENTS.md §3: *"Provide /memory to inspect the
active window."* The active window is the rolling 10-message cap
the REPL maintains in ``AppState.history`` (= ``INT_HISTORY_CAP``
user/assistant turns, default 10 turns = 20 messages).

The command reads ``AppState.history`` directly — no LLM call,
no session-store read. Each message is shown with its 1-based
index and its role, so the user can read the conversation back
exactly as it sits in the LLM's request payload.

Format:

    [1] USER: hello there
    [2] ASSISTANT: hi! how can I help?
    [3] USER: what's 2+2?
    [4] ASSISTANT: four
    ...

The ``/resume <id>`` command reuses ``format_messages_for_display``
so the resumed conversation is printed in the same shape right
after a context switch — the OpenCode-style UX.

Empty history is rendered as ``"(no messages in the active
window)"`` so the output is never blank.
"""

from __future__ import annotations

from simple_cli_coder_with_rag.domain.messages import Message
from simple_cli_coder_with_rag.presentation.commands import (
    AppState,
    CommandContext,
    CommandResult,
)


class MemoryCommand:
    """``/memory``: print the last 10 messages in the active window."""

    name = "memory"
    summary = "Print the last 10 messages in the active window."

    def execute(self, context: CommandContext) -> CommandResult:
        state: AppState = context.app_state
        return CommandResult(
            action="continue",
            message=format_messages_for_display(state.history),
        )


def format_messages_for_display(messages: list[Message]) -> str:
    """Format ``messages`` for terminal display (one line per message).

    Used by both ``/memory`` (standalone inspection) and
    ``/resume <id>`` (inline print on context switch). Keeping a
    single formatter means the two surfaces stay in sync — if the
    user reads the conversation back via ``/memory`` and then runs
    ``/resume <other>``, the next ``/memory`` output matches what
    ``/resume`` printed at load time.

    Returns a single multi-line string suitable for
    ``CommandResult.message``. An empty ``messages`` list yields
    ``"(no messages in the active window)"`` so the output is
    never blank.
    """
    if not messages:
        return "(no messages in the active window)"
    lines = [f"[{i}] {msg.role.upper()}: {msg.content}" for i, msg in enumerate(messages, start=1)]
    return "\n".join(lines)


__all__ = ["MemoryCommand", "format_messages_for_display"]
