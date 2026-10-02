"""Tests for the REPL chat path through ``KnowledgeService``.

Pinned by ``agent-development/03-agent-responds-baseline/tests.md``.
``prompt_toolkit.PromptSession.prompt`` is patched to yield the configured
inputs; ``KnowledgeService.chat`` is replaced with a ``MagicMock`` so the
tests never touch the LLM.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from simple_cli_coder_with_rag import __version__
from simple_cli_coder_with_rag.domain.llm_client import LLMError
from simple_cli_coder_with_rag.domain.messages import (
    AssistantMessage,
    UserMessage,
)
from simple_cli_coder_with_rag.presentation.commands import AppState
from simple_cli_coder_with_rag.presentation.commands.exit import ExitCommand
from simple_cli_coder_with_rag.presentation.repl import Repl

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from simple_cli_coder_with_rag.presentation.registry import CommandRegistry


def _patch_prompt(monkeypatch: pytest.MonkeyPatch, inputs: list[str]) -> None:
    """Replace ``PromptSession.prompt`` with a function returning successive inputs."""
    from prompt_toolkit import PromptSession

    iterator = iter(inputs)

    def fake_prompt(self: object, *args: object, **kwargs: object) -> str:
        try:
            return next(iterator)
        except StopIteration:
            # End of input: behave like EOF so the REPL loop exits.
            raise EOFError from None

    monkeypatch.setattr(PromptSession, "prompt", fake_prompt)


def _app_state_with(knowledge: object) -> AppState:
    """Return a fresh ``AppState`` carrying ``knowledge`` and an empty history."""
    return AppState(version=__version__, knowledge=knowledge, history=[])


def test_repl_calls_chat_for_non_slash_input(
    monkeypatch: pytest.MonkeyPatch,
    fresh_registry: CommandRegistry,
    mocker: MockerFixture,
) -> None:
    """A non-slash line routes through ``KnowledgeService.chat`` exactly once.

    DO-09 adds an optional ``recalled`` kwarg to ``KnowledgeService.chat``;
    this test pins that the REPL continues to invoke ``chat`` with the
    user message and history in the documented positions, regardless of
    the additional ``recalled`` payload.
    """
    knowledge = mocker.MagicMock()
    knowledge.chat.return_value = "ignored"

    state = _app_state_with(knowledge)
    fresh_registry.register(ExitCommand())
    _patch_prompt(monkeypatch, ["hello", "/exit"])

    repl = Repl(registry=fresh_registry, app_state=state)
    repl.run()

    knowledge.chat.assert_called_once()
    call = knowledge.chat.call_args
    assert call.args == ("hello",)
    assert call.kwargs["history"] == []


def test_repl_prints_llm_response(
    monkeypatch: pytest.MonkeyPatch,
    fresh_registry: CommandRegistry,
    capsys: pytest.CaptureFixture[str],
    mocker: MockerFixture,
) -> None:
    """The LLM response is written to stdout."""
    knowledge = mocker.MagicMock()
    knowledge.chat.return_value = "response text"

    state = _app_state_with(knowledge)
    fresh_registry.register(ExitCommand())
    _patch_prompt(monkeypatch, ["hello", "/exit"])

    repl = Repl(registry=fresh_registry, app_state=state)
    repl.run()

    captured = capsys.readouterr().out
    assert "response text" in captured


def test_repl_appends_to_history(
    monkeypatch: pytest.MonkeyPatch,
    fresh_registry: CommandRegistry,
    mocker: MockerFixture,
) -> None:
    """After a chat turn, history contains the user + assistant messages in order."""
    knowledge = mocker.MagicMock()
    knowledge.chat.return_value = "hi back"

    state = _app_state_with(knowledge)
    fresh_registry.register(ExitCommand())
    _patch_prompt(monkeypatch, ["hello", "/exit"])

    repl = Repl(registry=fresh_registry, app_state=state)
    repl.run()

    assert state.history == [
        UserMessage(content="hello"),
        AssistantMessage(content="hi back"),
    ]


def test_repl_does_not_call_chat_for_slash_command(
    monkeypatch: pytest.MonkeyPatch,
    fresh_registry: CommandRegistry,
    mocker: MockerFixture,
) -> None:
    """Slash commands bypass the chat path entirely."""
    knowledge = mocker.MagicMock()
    knowledge.chat.return_value = "ignored"

    state = _app_state_with(knowledge)
    fresh_registry.register(ExitCommand())
    _patch_prompt(monkeypatch, ["/help", "/exit"])

    repl = Repl(registry=fresh_registry, app_state=state)
    repl.run()

    knowledge.chat.assert_not_called()


def test_repl_caps_history_at_20_turns(
    monkeypatch: pytest.MonkeyPatch,
    fresh_registry: CommandRegistry,
    mocker: MockerFixture,
) -> None:
    """After 25 turns, history is capped at 40 messages (20 turns) — oldest dropped."""
    knowledge = mocker.MagicMock()
    knowledge.chat.return_value = "ok"

    state = _app_state_with(knowledge)
    fresh_registry.register(ExitCommand())

    inputs = [f"msg-{i}" for i in range(25)] + ["/exit"]
    _patch_prompt(monkeypatch, inputs)

    repl = Repl(registry=fresh_registry, app_state=state)
    repl.run()

    assert len(state.history) == 40
    # The first five turns (msg-0..msg-4) were dropped from the front.
    assert state.history[0] == UserMessage(content="msg-5")
    assert state.history[-1] == AssistantMessage(content="ok")


def test_repl_swallows_llm_error(
    monkeypatch: pytest.MonkeyPatch,
    fresh_registry: CommandRegistry,
    capsys: pytest.CaptureFixture[str],
    mocker: MockerFixture,
) -> None:
    """``LLMError`` is printed as ``LLM error: <msg>`` and the loop continues."""
    knowledge = mocker.MagicMock()
    knowledge.chat.side_effect = LLMError("boom")

    state = _app_state_with(knowledge)
    fresh_registry.register(ExitCommand())
    _patch_prompt(monkeypatch, ["hello", "/exit"])

    repl = Repl(registry=fresh_registry, app_state=state)
    repl.run()

    captured = capsys.readouterr().out
    assert "LLM error: boom" in captured
    # Failed turns must not pollute the history.
    assert state.history == []


def test_repl_history_persists_across_turns(
    monkeypatch: pytest.MonkeyPatch,
    fresh_registry: CommandRegistry,
    mocker: MockerFixture,
) -> None:
    """``history`` grows between chat turns and is passed to ``chat`` each time."""
    knowledge = mocker.MagicMock()
    knowledge.chat.side_effect = ["r1", "r2"]

    state = _app_state_with(knowledge)
    fresh_registry.register(ExitCommand())
    _patch_prompt(monkeypatch, ["a", "b", "/exit"])

    repl = Repl(registry=fresh_registry, app_state=state)
    repl.run()

    assert len(knowledge.chat.call_args_list) == 2

    first_call = knowledge.chat.call_args_list[0]
    assert first_call.args == ("a",)
    assert first_call.kwargs["history"] == []

    second_call = knowledge.chat.call_args_list[1]
    assert second_call.args == ("b",)
    assert second_call.kwargs["history"] == [
        UserMessage(content="a"),
        AssistantMessage(content="r1"),
    ]
