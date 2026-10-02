"""Tests for ``Repl._handle_chat`` persistence to ``SessionStore`` (DO-12).

Pinned by ``agent-development/12-session-memory-and-saved-chats/tests.md``.

The REPL appends every chat turn (user + assistant) to the on-disk
``<id>.jsonl`` transcript so ``/chats`` can list it and ``/resume
<id>`` can load it back. Idempotency comes from a ``seen`` set built
from ``session_store.read(session_id)`` before each chat turn — a
resumed session whose messages are already on disk never
re-appends them.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from simple_cli_coder_with_rag import __version__
from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.domain.messages import (
    AssistantMessage,
    Message,
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


def _app_state_with(
    knowledge: object,
    *,
    session_store: SessionStore | None,
    session_id: str,
) -> AppState:
    """Return a fresh ``AppState`` carrying ``knowledge`` and an empty history."""
    return AppState(
        version=__version__,
        knowledge=knowledge,
        history=[],
        session_store=session_store,
        session_id=session_id,
    )


def test_repl_appends_each_turn_to_session_store(
    monkeypatch: pytest.MonkeyPatch,
    fresh_registry: CommandRegistry,
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Three chat turns produce 6 lines in the on-disk ``.jsonl``."""
    knowledge = mocker.MagicMock()
    knowledge.chat.return_value = "ok"
    store = SessionStore(tmp_path)
    session_id = store.current_id()

    state = _app_state_with(knowledge, session_store=store, session_id=session_id)
    fresh_registry.register(ExitCommand())
    _patch_prompt(monkeypatch, ["hi", "next", "more", "/exit"])

    repl = Repl(registry=fresh_registry, app_state=state)
    repl.run()

    persisted = store.read(session_id)
    assert len(persisted) == 6
    assert persisted[0] == Message(role="user", content="hi")
    assert persisted[1] == Message(role="assistant", content="ok")
    assert persisted[2] == Message(role="user", content="next")
    assert persisted[3] == Message(role="assistant", content="ok")
    assert persisted[4] == Message(role="user", content="more")
    assert persisted[5] == Message(role="assistant", content="ok")


def test_repl_does_not_re_persist_messages_already_loaded(
    monkeypatch: pytest.MonkeyPatch,
    fresh_registry: CommandRegistry,
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Pre-existing transcript lines are not duplicated by a fresh turn."""
    knowledge = mocker.MagicMock()
    knowledge.chat.return_value = "new"
    store = SessionStore(tmp_path)
    session_id = store.current_id()
    # Two existing user/assistant pairs.
    store.append(session_id, UserMessage(content="a"))
    store.append(session_id, AssistantMessage(content="A"))
    store.append(session_id, UserMessage(content="b"))
    store.append(session_id, AssistantMessage(content="B"))

    state = _app_state_with(knowledge, session_store=store, session_id=session_id)
    fresh_registry.register(ExitCommand())
    _patch_prompt(monkeypatch, ["c", "/exit"])

    repl = Repl(registry=fresh_registry, app_state=state)
    repl.run()

    persisted = store.read(session_id)
    assert len(persisted) == 6  # 4 prior + 2 new
    assert persisted[-2] == Message(role="user", content="c")
    assert persisted[-1] == Message(role="assistant", content="new")


def test_repl_no_session_store_skips_persistence(
    monkeypatch: pytest.MonkeyPatch,
    fresh_registry: CommandRegistry,
    mocker: MockerFixture,
) -> None:
    """``session_store is None`` does not crash; the history still grows."""
    knowledge = mocker.MagicMock()
    knowledge.chat.return_value = "ok"

    state = _app_state_with(knowledge, session_store=None, session_id="")
    fresh_registry.register(ExitCommand())
    _patch_prompt(monkeypatch, ["hi", "hi", "/exit"])

    repl = Repl(registry=fresh_registry, app_state=state)
    repl.run()

    assert len(state.history) == 4


def test_repl_generates_session_id_when_missing(
    monkeypatch: pytest.MonkeyPatch,
    fresh_registry: CommandRegistry,
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """An empty ``session_id`` is filled in via ``session_store.current_id()``."""
    knowledge = mocker.MagicMock()
    knowledge.chat.return_value = "ok"
    store = SessionStore(tmp_path)

    state = _app_state_with(knowledge, session_store=store, session_id="")
    fresh_registry.register(ExitCommand())
    _patch_prompt(monkeypatch, ["hi", "/exit"])

    repl = Repl(registry=fresh_registry, app_state=state)
    repl.run()

    # 32-char UUIDv4 hex string.
    assert len(state.session_id) == 32
    assert all(c in "0123456789abcdef" for c in state.session_id)
    assert store.path(state.session_id).exists()


def test_repl_does_not_persist_failed_turns(
    monkeypatch: pytest.MonkeyPatch,
    fresh_registry: CommandRegistry,
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """A turn that raises ``LLMError`` does not pollute the on-disk transcript."""
    from simple_cli_coder_with_rag.domain.llm_client import LLMError

    knowledge = mocker.MagicMock()
    knowledge.chat.side_effect = LLMError("boom")
    store = SessionStore(tmp_path)
    session_id = store.current_id()

    state = _app_state_with(knowledge, session_store=store, session_id=session_id)
    fresh_registry.register(ExitCommand())
    _patch_prompt(monkeypatch, ["hi", "/exit"])

    repl = Repl(registry=fresh_registry, app_state=state)
    repl.run()

    # The failed turn is not persisted.
    assert store.read(session_id) == []
