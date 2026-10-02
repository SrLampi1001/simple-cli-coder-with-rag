"""Tests for ``LearnCommand``. Pinned by
``agent-development/04-learn-compaction/tests.md`` and extended by
``agent-development/05-chunker-strategy/tests.md``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from simple_cli_coder_with_rag import __version__
from simple_cli_coder_with_rag.application.compactor import CompactionError
from simple_cli_coder_with_rag.domain.llm_client import LLMError
from simple_cli_coder_with_rag.domain.messages import (
    AssistantMessage,
    UserMessage,
)
from simple_cli_coder_with_rag.presentation.commands import (
    AppState,
    CommandContext,
)
from simple_cli_coder_with_rag.presentation.commands.learn import LearnCommand
from simple_cli_coder_with_rag.presentation.registry import CommandRegistry

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@dataclass
class _StubRepl:
    """Minimal stand-in for ``Repl`` — only ``request_exit`` is invoked by commands."""

    request_exit_calls: int = 0

    def request_exit(self) -> None:
        self.request_exit_calls += 1


def _make_context(app_state: AppState) -> CommandContext:
    return CommandContext(repl=_StubRepl(), app_state=app_state)


def _wait_for(predicate, timeout: float = 5.0) -> None:
    """Poll ``predicate`` until true or the deadline passes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting for background /learn to finish")


def test_learn_command_runs_in_background(mocker: MockerFixture) -> None:
    """``LearnCommand`` returns immediately and calls ``knowledge.learn`` off-thread."""
    knowledge = mocker.MagicMock()
    knowledge.learn.return_value = 3

    app_state = AppState(
        version=__version__,
        knowledge=knowledge,  # type: ignore[arg-type]
        session_id="sid",
        history=[UserMessage(content="a"), AssistantMessage(content="b")],
    )

    result = LearnCommand().execute(_make_context(app_state))

    assert result.action == "continue"
    assert result.message is not None
    assert "background" in result.message
    _wait_for(lambda: knowledge.learn.called)
    knowledge.learn.assert_called_once()
    assert knowledge.learn.call_args.args == ("sid",)


def test_learn_command_does_not_exit(mocker: MockerFixture) -> None:
    """``learn`` must not terminate the REPL, even when it succeeds."""
    knowledge = mocker.MagicMock()
    knowledge.learn.return_value = 0

    app_state = AppState(
        version=__version__,
        knowledge=knowledge,  # type: ignore[arg-type]
        session_id="sid",
        history=[],
    )

    result = LearnCommand().execute(_make_context(app_state))

    assert result.action == "continue"


def test_learn_command_reports_llm_error(mocker: MockerFixture, capsys) -> None:
    """On ``LLMError`` the background worker prints ``learn failed:`` and the REPL survives."""
    knowledge = mocker.MagicMock()
    knowledge.learn.side_effect = LLMError("boom")

    app_state = AppState(
        version=__version__,
        knowledge=knowledge,  # type: ignore[arg-type]
        session_id="sid",
        history=[UserMessage(content="hi")],
    )

    result = LearnCommand().execute(_make_context(app_state))

    assert result.action == "continue"
    out = ""
    for _ in range(500):
        out += capsys.readouterr().out
        if "learn failed: " in out:
            break
        time.sleep(0.01)
    assert "learn failed: " in out
    assert "boom" in out


def test_learn_command_reports_compaction_error(mocker: MockerFixture, capsys) -> None:
    """On ``CompactionError`` the worker prints ``learn failed:`` and the REPL survives."""
    knowledge = mocker.MagicMock()
    knowledge.learn.side_effect = CompactionError("schema mismatch")

    app_state = AppState(
        version=__version__,
        knowledge=knowledge,  # type: ignore[arg-type]
        session_id="sid",
        history=[UserMessage(content="hi")],
    )

    result = LearnCommand().execute(_make_context(app_state))

    assert result.action == "continue"
    out = ""
    for _ in range(500):
        out += capsys.readouterr().out
        if "schema mismatch" in out:
            break
        time.sleep(0.01)
    assert "schema mismatch" in out


def test_learn_command_is_registered() -> None:
    """``LearnCommand`` declares the canonical ``"learn"`` name and registers in a registry."""
    registry = CommandRegistry()
    registry.register(LearnCommand())

    assert registry.get("learn") is not None
    assert LearnCommand.name == "learn"


def test_learn_command_persists_history_to_session_store(
    mocker: MockerFixture,
) -> None:
    """``LearnCommand`` re-persists in-memory history before invoking ``learn``.

    This is the defensive idempotent path: the REPL also persists each
    turn, but ``LearnCommand`` does it again so a ``/learn`` invoked
    out-of-order (or after a process restart that lost the in-memory
    append) still works.
    """
    from pathlib import Path

    from simple_cli_coder_with_rag.application.session_store import SessionStore

    knowledge = mocker.MagicMock()
    knowledge.learn.return_value = 2

    store = SessionStore(Path("/tmp"))
    history = [
        UserMessage(content="hello"),
        AssistantMessage(content="hi back"),
    ]
    app_state = AppState(
        version=__version__,
        knowledge=knowledge,  # type: ignore[arg-type]
        session_id="sid",
        history=history,
        session_store=store,
    )

    # Spy on ``SessionStore.append`` so we can assert the call.
    append_calls: list[tuple[str, str]] = []

    def fake_append(session_id: str, msg: object) -> None:
        append_calls.append((session_id, msg.content))  # type: ignore[attr-defined]

    mocker.patch.object(store, "append", side_effect=fake_append)
    mocker.patch.object(store, "read", return_value=[])

    LearnCommand().execute(_make_context(app_state))
    _wait_for(lambda: knowledge.learn.called)

    assert append_calls == [("sid", "hello"), ("sid", "hi back")]
    knowledge.learn.assert_called_once()
    assert knowledge.learn.call_args.args == ("sid",)


def test_learn_command_skips_already_persisted_messages(
    mocker: MockerFixture,
) -> None:
    """``LearnCommand`` does not re-append messages already on disk."""
    from pathlib import Path

    from simple_cli_coder_with_rag.application.session_store import SessionStore
    from simple_cli_coder_with_rag.domain.messages import UserMessage

    knowledge = mocker.MagicMock()
    knowledge.learn.return_value = 1

    store = SessionStore(Path("/tmp"))
    app_state = AppState(
        version=__version__,
        knowledge=knowledge,  # type: ignore[arg-type]
        session_id="sid",
        history=[UserMessage(content="already-there")],
        session_store=store,
    )

    append_calls: list[tuple[str, str]] = []

    def fake_append(session_id: str, msg: object) -> None:
        append_calls.append((session_id, msg.content))  # type: ignore[attr-defined]

    mocker.patch.object(store, "append", side_effect=fake_append)
    # ``read`` returns the same message → LearnCommand skips the append.
    mocker.patch.object(store, "read", return_value=[UserMessage(content="already-there")])

    LearnCommand().execute(_make_context(app_state))
    _wait_for(lambda: knowledge.learn.called)

    assert append_calls == []  # nothing appended
    knowledge.learn.assert_called_once()
    assert knowledge.learn.call_args.args == ("sid",)
