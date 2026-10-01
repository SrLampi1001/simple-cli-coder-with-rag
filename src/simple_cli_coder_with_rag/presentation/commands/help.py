"""``/help`` command — list every registered command."""

from __future__ import annotations

from simple_cli_coder_with_rag.presentation.commands import (
    CommandContext,
    CommandResult,
)
from simple_cli_coder_with_rag.presentation.registry import CommandRegistry


class HelpCommand:
    """Print the names and one-line summaries of every registered command."""

    name = "help"
    summary = "list available commands"

    def __init__(self, registry: CommandRegistry) -> None:
        self._registry = registry

    def execute(self, context: CommandContext) -> CommandResult:
        lines = ["Available commands:"]
        for command in self._registry.all():
            lines.append(f"  {command.name:<12} {command.summary}")
        return CommandResult(action="continue", message="\n".join(lines))


__all__ = ["HelpCommand"]
