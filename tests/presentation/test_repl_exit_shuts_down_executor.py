"""Test pinning that ``Repl.run`` invokes its ``on_exit`` callback on EOF.

Pinned by ``agent-development/08-retriever-with-decorator/tests.md``.

The composition root wires ``RetrievalExecutor.shutdown`` as the REPL's
``on_exit`` callback so Ctrl-D does not hang waiting for in-flight
retrieval threads (``docs/development-tools.md`` §9). This test
exercises the **wiring** — it builds a ``Repl`` whose ``on_exit`` is the
real executor's ``shutdown``, feeds the prompt an empty input list
(immediate ``EOFError``), and asserts ``shutdown`` was called exactly
once after ``run()`` returns.

A regression here would let Ctrl-D hang the process while pending retrieval
futures drain — the original v1 problem the timeout Decorator was added to
avoid in the first place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from simple_cli_coder_with_rag import __version__
from simple_cli_coder_with_rag.infrastructure.retrievers.executor import (
    RetrievalExecutor,
)
from simple_cli_coder_with_rag.presentation.commands import AppState
from simple_cli_coder_with_rag.presentation.commands.exit import ExitCommand
from simple_cli_coder_with_rag.presentation.registry import CommandRegistry
from simple_cli_coder_with_rag.presentation.repl import Repl

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _app_state() -> AppState:
    """Return a bare ``AppState`` — the loop exits before any field is read."""
    return AppState(version=__version__)


def _patch_prompt_immediate_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace ``PromptSession.prompt`` so the REPL loop exits on the first call."""
    from prompt_toolkit import PromptSession

    def raise_eof(self: object, *args: object, **kwargs: object) -> str:
        raise EOFError

    monkeypatch.setattr(PromptSession, "prompt", raise_eof)


def test_repl_eof_calls_executor_shutdown(
    monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    """``Repl.run`` fed an empty stream (immediate EOF) invokes ``on_exit`` once.

    Patches ``RetrievalExecutor.shutdown`` so we can observe the call
    without actually tearing down the executor — the executor is otherwise
    unused in this test (no retrieval is submitted).
    """
    executor = RetrievalExecutor(max_workers=1)
    shutdown_spy = mocker.patch.object(executor, "shutdown")

    registry = CommandRegistry()
    registry.register(ExitCommand())

    _patch_prompt_immediate_eof(monkeypatch)

    repl = Repl(
        registry=registry,
        app_state=_app_state(),
        on_exit=executor.shutdown,
    )
    repl.run()

    shutdown_spy.assert_called_once_with()


def test_repl_exit_command_also_calls_on_exit(
    monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    """A clean ``/exit`` invokes ``on_exit`` — same controller, different trigger."""
    from prompt_toolkit import PromptSession

    executor = RetrievalExecutor(max_workers=1)
    shutdown_spy = mocker.patch.object(executor, "shutdown")

    iterator = iter(["/exit"])

    def feed_prompt(self: object, *args: object, **kwargs: object) -> str:
        try:
            return next(iterator)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr(PromptSession, "prompt", feed_prompt)

    registry = CommandRegistry()
    registry.register(ExitCommand())

    repl = Repl(
        registry=registry,
        app_state=_app_state(),
        on_exit=executor.shutdown,
    )
    repl.run()

    shutdown_spy.assert_called_once_with()


def test_repl_without_on_exit_does_not_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``Repl`` without an ``on_exit`` callback returns cleanly on EOF.

    Regression guard — the optional callback must default to ``None`` and
    the ``finally`` block must skip the call when ``None``. Pre-DO-08 tests
    construct ``Repl`` without ``on_exit``; they must not regress.
    """
    _patch_prompt_immediate_eof(monkeypatch)

    registry = CommandRegistry()
    registry.register(ExitCommand())

    repl = Repl(registry=registry, app_state=_app_state())
    repl.run()  # must not raise
