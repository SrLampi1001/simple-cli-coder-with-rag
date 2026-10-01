"""Tests for the ``Repl`` loop."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from simple_cli_coder_with_rag import __version__
from simple_cli_coder_with_rag.presentation.commands import AppState, CommandContext
from simple_cli_coder_with_rag.presentation.commands.exit import ExitCommand
from simple_cli_coder_with_rag.presentation.registry import CommandRegistry
from simple_cli_coder_with_rag.presentation.repl import Repl

if TYPE_CHECKING:
    from simple_cli_coder_with_rag.presentation.registry import CommandRegistry


@dataclass
class _SpyHelp:
    name: str = "help"
    summary: str = "spy"
    execute_calls: int = 0

    def execute(self, context: CommandContext) -> object:  # type: ignore[override]
        self.execute_calls += 1
        from simple_cli_coder_with_rag.presentation.commands import CommandResult

        return CommandResult(action="continue", message="help ran")


def _app_state() -> AppState:
    return AppState(version=__version__)


def _patch_prompt(monkeypatch: pytest.MonkeyPatch, inputs: list[str]) -> None:
    """Replace ``PromptSession.prompt`` with a function returning successive inputs."""
    from prompt_toolkit import PromptSession

    iterator = iter(inputs)

    def fake_prompt(self: object, *args: object, **kwargs: object) -> str:
        try:
            return next(iterator)
        except StopIteration:
            # End of the input sequence: act like EOF.
            raise EOFError from None

    monkeypatch.setattr(PromptSession, "prompt", fake_prompt)


def test_repl_invokes_help_for_slash_help(
    monkeypatch: pytest.MonkeyPatch, fresh_registry: CommandRegistry
) -> None:
    spy = _SpyHelp()
    fresh_registry.register(spy)
    fresh_registry.register(ExitCommand())
    _patch_prompt(monkeypatch, ["/help"])

    repl = Repl(registry=fresh_registry, app_state=_app_state())
    repl.run()

    assert spy.execute_calls == 1


def test_repl_invokes_exit_for_slash_exit(
    monkeypatch: pytest.MonkeyPatch, fresh_registry: CommandRegistry
) -> None:
    fresh_registry.register(ExitCommand())
    _patch_prompt(monkeypatch, ["/exit"])

    repl = Repl(registry=fresh_registry, app_state=_app_state())
    repl.run()  # must return without further input


def test_repl_prints_unknown_command_message(
    monkeypatch: pytest.MonkeyPatch,
    fresh_registry: CommandRegistry,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fresh_registry.register(ExitCommand())
    _patch_prompt(monkeypatch, ["/foo", "/exit"])

    repl = Repl(registry=fresh_registry, app_state=_app_state())
    repl.run()

    captured = capsys.readouterr().out
    assert "Unknown command: /foo" in captured


def test_repl_echoes_non_slash_input_message(
    monkeypatch: pytest.MonkeyPatch,
    fresh_registry: CommandRegistry,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fresh_registry.register(ExitCommand())
    _patch_prompt(monkeypatch, ["hello", "/exit"])

    repl = Repl(registry=fresh_registry, app_state=_app_state())
    repl.run()

    captured = capsys.readouterr().out
    assert "Type /help for available commands." in captured


def test_repl_does_not_call_loguru_sink_for_stderr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    """When the REPL starts, no loguru sink writes to stdout or stderr."""
    from loguru import logger as _logger

    captured: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(_logger, "add", lambda *a, **kw: captured.append((a, kw)) or 1)
    monkeypatch.setattr(_logger, "remove", lambda *_a, **_kw: None)

    from simple_cli_coder_with_rag.infrastructure.logging import configure_logging

    configure_logging(log_dir=tmp_path)

    # The file sink must be registered.
    assert captured, "configure_logging did not register any loguru sink"

    # No sink may write to stdout/stderr.
    for args, _kwargs in captured:
        for arg in args:
            assert arg is not sys.stdout, f"stdout sink present: {arg!r}"
            assert arg is not sys.stderr, f"stderr sink present: {arg!r}"
