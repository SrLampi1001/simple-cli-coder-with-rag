"""``/clear`` command — clear the visible screen."""

from __future__ import annotations

from simple_cli_coder_with_rag.presentation.commands import (
    CommandContext,
    CommandResult,
)


class ClearCommand:
    """Erase the visible screen via :func:`prompt_toolkit.shortcuts.clear`.

    The import is deferred so tests can monkeypatch
    :data:`prompt_toolkit.shortcuts.clear` and observe the call.
    """

    name = "clear"
    summary = "clear the screen"

    def execute(self, context: CommandContext) -> CommandResult:
        from prompt_toolkit.shortcuts import clear

        clear()
        return CommandResult(action="continue")


__all__ = ["ClearCommand"]
