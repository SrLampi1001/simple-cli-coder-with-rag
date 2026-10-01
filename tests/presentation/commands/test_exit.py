"""Tests for ``ExitCommand``."""

from __future__ import annotations

from dataclasses import dataclass

from simple_cli_coder_with_rag.presentation.commands import CommandContext
from simple_cli_coder_with_rag.presentation.commands.exit import ExitCommand


@dataclass
class _StubRepl:
    request_exit_calls: int = 0

    def request_exit(self) -> None:
        self.request_exit_calls += 1


def test_exit_signals_exit() -> None:
    repl = _StubRepl()
    context = CommandContext(repl=repl, app_state=None)  # type: ignore[arg-type]

    result = ExitCommand().execute(context)

    assert result.action == "exit"


def test_exit_calls_repl_request_exit() -> None:
    repl = _StubRepl()
    context = CommandContext(repl=repl, app_state=None)  # type: ignore[arg-type]

    ExitCommand().execute(context)

    assert repl.request_exit_calls == 1
