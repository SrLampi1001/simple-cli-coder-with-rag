"""Registry of :class:`~simple_cli_coder_with_rag.presentation.commands.Command` instances."""

from __future__ import annotations

from simple_cli_coder_with_rag.presentation.commands import Command


class CommandRegistry:
    """In-memory mapping of command name to :class:`Command`."""

    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}

    def register(self, command: Command) -> None:
        """Add ``command`` under its ``name``. Duplicate names raise."""
        if command.name in self._commands:
            raise ValueError(f"command already registered: {command.name!r}")
        self._commands[command.name] = command

    def unregister(self, name: str) -> None:
        """Remove the command registered as ``name``, if any."""
        self._commands.pop(name, None)

    def get(self, name: str) -> Command | None:
        """Return the command registered as ``name``, or ``None``."""
        return self._commands.get(name)

    def names(self) -> list[str]:
        """Return registered names in deterministic (sorted) order."""
        return sorted(self._commands)

    def all(self) -> list[Command]:
        """Return every registered command (insertion order)."""
        return list(self._commands.values())


__all__ = ["CommandRegistry"]
