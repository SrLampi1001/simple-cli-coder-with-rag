"""Tests for ``ClearCommand``."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from simple_cli_coder_with_rag.presentation.commands import CommandContext
from simple_cli_coder_with_rag.presentation.commands.clear import ClearCommand


@dataclass
class _StubRepl:
    request_exit_calls: int = 0

    def request_exit(self) -> None:
        self.request_exit_calls += 1


def test_clear_signals_continue(monkeypatch: pytest.MonkeyPatch) -> None:
    from prompt_toolkit import shortcuts as _shortcuts

    monkeypatch.setattr(_shortcuts, "clear", lambda: None)

    context = CommandContext(repl=_StubRepl(), app_state=None)  # type: ignore[arg-type]
    result = ClearCommand().execute(context)

    assert result.action == "continue"


def test_clear_invokes_prompt_toolkit_clear(monkeypatch: pytest.MonkeyPatch) -> None:
    from prompt_toolkit import shortcuts as _shortcuts

    calls = {"n": 0}

    def fake_clear() -> None:
        calls["n"] += 1

    monkeypatch.setattr(_shortcuts, "clear", fake_clear)

    context = CommandContext(repl=_StubRepl(), app_state=None)  # type: ignore[arg-type]
    ClearCommand().execute(context)

    assert calls["n"] == 1
