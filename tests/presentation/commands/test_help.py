"""Tests for ``HelpCommand``."""

from __future__ import annotations

from dataclasses import dataclass

from simple_cli_coder_with_rag.presentation.commands import CommandContext, CommandResult
from simple_cli_coder_with_rag.presentation.commands.help import HelpCommand
from simple_cli_coder_with_rag.presentation.registry import CommandRegistry


@dataclass(frozen=True)
class _StubCommand:
    name: str
    summary: str

    def execute(self, context: CommandContext) -> CommandResult:
        return CommandResult(action="continue")


@dataclass
class _StubRepl:
    request_exit_calls: int = 0

    def request_exit(self) -> None:
        self.request_exit_calls += 1


def _make_context() -> CommandContext:
    return CommandContext(repl=_StubRepl(), app_state=None)  # type: ignore[arg-type]


def test_help_lists_all_registered_commands() -> None:
    registry = CommandRegistry()
    registry.register(_StubCommand(name="alpha", summary="first"))
    registry.register(_StubCommand(name="beta", summary="second"))
    registry.register(_StubCommand(name="gamma", summary="third"))

    result = HelpCommand(registry).execute(_make_context())

    assert result.action == "continue"
    assert result.message is not None
    assert "alpha" in result.message
    assert "first" in result.message
    assert "beta" in result.message
    assert "second" in result.message
    assert "gamma" in result.message
    assert "third" in result.message


def test_help_message_is_human_readable() -> None:
    registry = CommandRegistry()
    registry.register(_StubCommand(name="alpha", summary="first"))
    registry.register(_StubCommand(name="beta", summary="second"))

    message = HelpCommand(registry).execute(_make_context()).message
    assert message is not None
    # One newline-separated entry per command, plus a header line.
    lines = [line for line in message.splitlines() if line.strip()]
    assert len(lines) >= 2
