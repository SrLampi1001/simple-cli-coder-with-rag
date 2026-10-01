"""``/version`` command — print the package version."""

from __future__ import annotations

from simple_cli_coder_with_rag import __version__
from simple_cli_coder_with_rag.presentation.commands import (
    CommandContext,
    CommandResult,
)


class VersionCommand:
    """Print :data:`simple_cli_coder_with_rag.__version__`."""

    name = "version"
    summary = "print the package version"

    def execute(self, context: CommandContext) -> CommandResult:
        return CommandResult(action="continue", message=__version__)


__all__ = ["VersionCommand"]
