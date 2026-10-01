"""``/exit`` command — terminate the REPL loop."""

from __future__ import annotations

from simple_cli_coder_with_rag.presentation.commands import (
    CommandContext,
    CommandResult,
)


class ExitCommand:
    """Signal the REPL to stop accepting input."""

    name = "exit"
    summary = "leave the interactive shell"

    def execute(self, context: CommandContext) -> CommandResult:
        context.repl.request_exit()
        return CommandResult(action="exit")


__all__ = ["ExitCommand"]
