"""Tests for ``LearnCommand``. Pinned by
``agent-development/04-learn-compaction/tests.md``.
"""

from __future__ import annotations

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


def test_learn_command_prints_count(mocker: MockerFixture) -> None:
    """``learn`` returns a message that starts with ``"learned "`` (chunk count is a stub)."""
    knowledge = mocker.MagicMock()
    knowledge.learn.return_value = None

    app_state = AppState(
        version=__version__,
        knowledge=knowledge,  # type: ignore[arg-type]
        session_id="sid",
        history=[UserMessage(content="a"), AssistantMessage(content="b")],
    )

    result = LearnCommand().execute(_make_context(app_state))

    assert result.action == "continue"
    assert result.message is not None
    assert result.message.startswith("learned ")
    knowledge.learn.assert_called_once()
    args, _ = knowledge.learn.call_args
    assert args[0] == "sid"
    assert list(args[1]) == [UserMessage(content="a"), AssistantMessage(content="b")]


def test_learn_command_does_not_exit(mocker: MockerFixture) -> None:
    """``learn`` must not terminate the REPL, even when it succeeds."""
    knowledge = mocker.MagicMock()
    knowledge.learn.return_value = None

    app_state = AppState(
        version=__version__,
        knowledge=knowledge,  # type: ignore[arg-type]
        session_id="sid",
        history=[],
    )

    result = LearnCommand().execute(_make_context(app_state))

    assert result.action == "continue"


def test_learn_command_handles_llm_error(mocker: MockerFixture) -> None:
    """On ``LLMError`` the command returns a ``learn failed:`` message and keeps the REPL alive."""
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
    assert result.message is not None
    assert result.message.startswith("learn failed: ")


def test_learn_command_handles_compaction_error(mocker: MockerFixture) -> None:
    """On ``CompactionError`` (LLM gave an unparseable response) the REPL must
    survive the trial. Without this catch the exception would propagate out of
    ``Repl._handle`` and crash the interactive session.
    """
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
    assert result.message is not None
    assert result.message.startswith("learn failed: ")
    assert "schema mismatch" in result.message


def test_learn_command_is_registered() -> None:
    """``LearnCommand`` declares the canonical ``"learn"`` name and registers in a registry."""
    registry = CommandRegistry()
    registry.register(LearnCommand())

    assert registry.get("learn") is not None
    assert LearnCommand.name == "learn"
