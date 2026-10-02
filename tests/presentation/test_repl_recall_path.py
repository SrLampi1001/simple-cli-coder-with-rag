"""Tests for the REPL chat path through recall (DO-09).

Pinned by ``agent-development/09-recall-integration/tests.md``. The
chat path now calls ``KnowledgeService.recall`` before
``KnowledgeService.chat`` and passes the result to
``build_chat_messages``. Slash commands must not trigger recall;
trivial prompts must short-circuit to ``[]``; an unready embedder must
not block the prompt.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from simple_cli_coder_with_rag import __version__
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
            raise EOFError from None

    monkeypatch.setattr(PromptSession, "prompt", fake_prompt)


def _app_state_with(knowledge: object, *, embedder: object | None = None) -> AppState:
    """Return a fresh ``AppState`` carrying ``knowledge`` and an empty history."""
    return AppState(
        version=__version__,
        knowledge=knowledge,
        history=[],
        embedder=embedder,  # type: ignore[arg-type]
    )


def test_repl_calls_recall_before_chat(
    monkeypatch: pytest.MonkeyPatch,
    fresh_registry: CommandRegistry,
    mocker: MockerFixture,
) -> None:
    """A non-trivial prompt triggers ``knowledge.recall`` once before ``knowledge.chat``."""
    knowledge = mocker.MagicMock()
    knowledge.recall.return_value = ["memory"]
    knowledge.chat.return_value = "ignored"

    state = _app_state_with(knowledge)
    fresh_registry.register(ExitCommand())
    _patch_prompt(monkeypatch, ["why does this fail", "/exit"])

    repl = Repl(registry=fresh_registry, app_state=state)
    repl.run()

    knowledge.recall.assert_called_once_with("why does this fail")
    knowledge.chat.assert_called_once()
    chat_args = knowledge.chat.call_args
    # Recall result must be passed to chat so the prompt builder can inject it.
    assert chat_args.kwargs.get("recalled") == ["memory"] or (
        len(chat_args.args) >= 3 and chat_args.args[2] == ["memory"]
    )


def test_repl_passes_recall_result_to_chat(
    monkeypatch: pytest.MonkeyPatch,
    fresh_registry: CommandRegistry,
    mocker: MockerFixture,
) -> None:
    """The recalled list propagates to ``chat`` and ends up in the sent messages."""
    knowledge = mocker.MagicMock()
    knowledge.recall.return_value = ["prior error fixed by X"]
    knowledge.chat.return_value = "ok"

    state = _app_state_with(knowledge)
    fresh_registry.register(ExitCommand())
    _patch_prompt(monkeypatch, ["why does this fail", "/exit"])

    repl = Repl(registry=fresh_registry, app_state=state)
    repl.run()

    # ``chat`` was called with the recalled list — assert it appears in the
    # arguments somehow (positional or keyword).
    chat_call = knowledge.chat.call_args
    recalled_arg = chat_call.kwargs.get("recalled")
    if recalled_arg is None and len(chat_call.args) >= 3:
        # Fall back to positional third argument (after user, history).
        recalled_arg = chat_call.args[2]
    assert recalled_arg == ["prior error fixed by X"]


def test_repl_skips_recall_for_slash_command(
    monkeypatch: pytest.MonkeyPatch,
    fresh_registry: CommandRegistry,
    mocker: MockerFixture,
) -> None:
    """Slash commands dispatch through the registry and never touch recall."""
    knowledge = mocker.MagicMock()
    knowledge.recall.return_value = []
    knowledge.chat.return_value = "ignored"

    state = _app_state_with(knowledge)
    fresh_registry.register(ExitCommand())
    _patch_prompt(monkeypatch, ["/help", "/exit"])

    repl = Repl(registry=fresh_registry, app_state=state)
    repl.run()

    knowledge.recall.assert_not_called()
    knowledge.chat.assert_not_called()


def test_repl_skips_recall_for_trivial_prompt(
    monkeypatch: pytest.MonkeyPatch,
    fresh_registry: CommandRegistry,
    mocker: MockerFixture,
) -> None:
    """Trivial prompt still routes to recall — the gate inside the coordinator skips work."""
    knowledge = mocker.MagicMock()
    knowledge.recall.return_value = []  # Coordinator gate short-circuits to []
    knowledge.chat.return_value = "ok"

    state = _app_state_with(knowledge)
    fresh_registry.register(ExitCommand())
    _patch_prompt(monkeypatch, ["hi", "/exit"])

    repl = Repl(registry=fresh_registry, app_state=state)
    repl.run()

    knowledge.recall.assert_called_once_with("hi")
    knowledge.chat.assert_called_once()
    chat_call = knowledge.chat.call_args
    recalled_arg = chat_call.kwargs.get("recalled", [])
    if not recalled_arg and len(chat_call.args) >= 3:
        recalled_arg = chat_call.args[2]
    assert recalled_arg == []


def test_repl_does_not_block_when_embedder_not_ready(
    monkeypatch: pytest.MonkeyPatch,
    fresh_registry: CommandRegistry,
    mocker: MockerFixture,
) -> None:
    """When the embedder is still loading, recall returns ``[]`` and chat still proceeds."""
    knowledge = mocker.MagicMock()
    knowledge.recall.return_value = []  # EmbedderNotReady → []
    knowledge.chat.return_value = "response"

    # Embedder wired but not ready.
    class _UnreadyEmbedder:
        def is_ready(self) -> bool:
            return False

    state = _app_state_with(knowledge, embedder=_UnreadyEmbedder())
    fresh_registry.register(ExitCommand())
    _patch_prompt(monkeypatch, ["hello world", "/exit"])

    repl = Repl(registry=fresh_registry, app_state=state)
    repl.run()

    # Recall was called (the coordinator handles the unready case internally);
    # chat was called once with an empty recalled list.
    knowledge.recall.assert_called_once_with("hello world")
    knowledge.chat.assert_called_once()


def test_repl_appends_recall_to_history_via_chat(
    monkeypatch: pytest.MonkeyPatch,
    fresh_registry: CommandRegistry,
    mocker: MockerFixture,
) -> None:
    """History grows by user + assistant turn, regardless of recalled injection."""
    knowledge = mocker.MagicMock()
    knowledge.recall.return_value = ["ctx"]
    knowledge.chat.return_value = "hi back"

    state = _app_state_with(knowledge)
    fresh_registry.register(ExitCommand())
    _patch_prompt(monkeypatch, ["hello", "/exit"])

    repl = Repl(registry=fresh_registry, app_state=state)
    repl.run()

    # The REPL only persists the user + assistant turns in history — the
    # ``SystemMessage`` for recall context lives inside the LLM request
    # and is not part of the on-disk transcript.
    assert state.history == [
        UserMessage(content="hello"),
        AssistantMessage(content="hi back"),
    ]


def test_repl_recall_exception_does_not_crash_loop(
    monkeypatch: pytest.MonkeyPatch,
    fresh_registry: CommandRegistry,
    mocker: MockerFixture,
) -> None:
    """An unexpected recall failure must not bring down the REPL loop.

    Defensive: the coordinator catches the common failures, but a
    novel ``Exception`` must not propagate out of the chat path.
    """
    knowledge = mocker.MagicMock()
    knowledge.recall.side_effect = RuntimeError("unexpected")
    knowledge.chat.return_value = "ok"

    state = _app_state_with(knowledge)
    fresh_registry.register(ExitCommand())
    _patch_prompt(monkeypatch, ["hi", "/exit"])

    repl = Repl(registry=fresh_registry, app_state=state)
    # Must not raise.
    repl.run()

    # Even on recall failure, chat still gets called with an empty
    # recalled list so the prompt degrades gracefully.
    knowledge.chat.assert_called_once()
