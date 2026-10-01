"""Interactive REPL driven by a :class:`CommandRegistry`."""

from __future__ import annotations

from collections.abc import Callable

from prompt_toolkit import PromptSession

from simple_cli_coder_with_rag.presentation.commands import (
    AppState,
    CommandContext,
)
from simple_cli_coder_with_rag.presentation.registry import CommandRegistry


class Repl:
    """Block in a :mod:`prompt_toolkit` loop until a command exits."""

    _PROMPT = ">>> "

    def __init__(
        self,
        registry: CommandRegistry,
        app_state: AppState,
        *,
        output: Callable[[str], None] = print,
    ) -> None:
        self._registry = registry
        self._app_state = app_state
        self._output = output
        self._should_exit = False

    def request_exit(self) -> None:
        """Set the flag that breaks the read-eval loop."""
        self._should_exit = True

    def run(self) -> None:
        """Read input, dispatch, repeat until :meth:`request_exit` is called."""
        session: PromptSession[str] = PromptSession()
        while not self._should_exit:
            try:
                line = session.prompt(self._PROMPT)
            except EOFError:
                # Ctrl-D on an empty prompt: behave as /exit.
                self._should_exit = True
                break
            self._handle(line)

    def _handle(self, line: str) -> None:
        """Dispatch a single line of input."""
        stripped = line.strip()
        if not stripped:
            return
        if not stripped.startswith("/"):
            self._output("Type /help for available commands.")
            return
        token = stripped[1:].split(maxsplit=1)[0]
        command = self._registry.get(token)
        if command is None:
            self._output(f"Unknown command: /{token}")
            self._output("Type /help for available commands.")
            return
        result = command.execute(CommandContext(repl=self, app_state=self._app_state))
        if result.message:
            self._output(result.message)


__all__ = ["Repl"]
