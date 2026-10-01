"""Tests for ``VersionCommand``."""

from __future__ import annotations

from dataclasses import dataclass

from simple_cli_coder_with_rag import __version__
from simple_cli_coder_with_rag.presentation.commands import CommandContext
from simple_cli_coder_with_rag.presentation.commands.version import VersionCommand


@dataclass
class _StubRepl:
    request_exit_calls: int = 0

    def request_exit(self) -> None:
        self.request_exit_calls += 1


def _context() -> CommandContext:
    return CommandContext(repl=_StubRepl(), app_state=None)  # type: ignore[arg-type]


def test_version_prints_package_version() -> None:
    result = VersionCommand().execute(_context())

    assert result.message == __version__


def test_version_does_not_exit() -> None:
    result = VersionCommand().execute(_context())

    assert result.action == "continue"
