"""Tests for ``NewCommand`` (DO-12 gap-fix).

Pinned by the workflow gap analysis — ``/new`` fills the missing
"start a new session" step in the workflow. Before this command
the only way to switch ``session_id`` was ``/resume <existing>``;
``/new`` generates a fresh UUIDv4 hex via ``SessionStore.current_id``
and clears the in-memory state so the next chat turn starts clean.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from simple_cli_coder_with_rag import __version__
from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.domain.messages import (
    AssistantMessage,
    UserMessage,
)
from simple_cli_coder_with_rag.presentation.commands import AppState, CommandContext
from simple_cli_coder_with_rag.presentation.commands.new import NewCommand


@dataclass
class _StubRepl:
    request_exit_calls: int = 0

    def request_exit(self) -> None:
        self.request_exit_calls += 1


def _context(app_state: AppState) -> CommandContext:
    return CommandContext(repl=_StubRepl(), app_state=app_state)  # type: ignore[arg-type]


def test_new_generates_fresh_session_id(tmp_path: Path) -> None:
    """``/new`` swaps the active ``session_id`` for a freshly-generated UUIDv4 hex."""
    store = SessionStore(tmp_path)
    old_id = store.current_id()
    state = AppState(version=__version__, session_id=old_id, session_store=store, history=[])

    result = NewCommand().execute(_context(state))

    assert result.action == "continue"
    assert state.session_id != old_id
    assert len(state.session_id) == 32  # UUIDv4 hex form


def test_new_clears_in_memory_history() -> None:
    """``/new`` empties ``app_state.history`` so the LLM context starts clean."""
    store = SessionStore(Path("/tmp"))
    state = AppState(
        version=__version__,
        session_id="abc1234567deadbeefabc1234567deadbe",
        session_store=store,
        history=[UserMessage(content="hi"), AssistantMessage(content="hello")],
    )

    NewCommand().execute(_context(state))

    assert state.history == []


def test_new_resets_persisted_through() -> None:
    """``/new`` resets the persistence pointer so the cleared history is not re-persisted."""
    store = SessionStore(Path("/tmp"))
    state = AppState(
        version=__version__,
        session_id="abc1234567deadbeefabc1234567deadbe",
        session_store=store,
        history=[],
        persisted_through=42,  # a stale value from a prior resume
    )

    NewCommand().execute(_context(state))

    assert state.persisted_through == 0


def test_new_message_includes_old_id(tmp_path: Path) -> None:
    """The result message surfaces the previous session id so the user can /resume it back."""
    store = SessionStore(tmp_path)
    old_id = store.current_id()
    state = AppState(version=__version__, session_id=old_id, session_store=store, history=[])

    result = NewCommand().execute(_context(state))

    assert old_id in (result.message or "")
    assert "started new session" in (result.message or "")


def test_new_without_session_store_returns_friendly() -> None:
    """``session_store is None`` returns the friendly fallback."""
    state = AppState(version=__version__, session_id="", session_store=None, history=[])

    result = NewCommand().execute(_context(state))

    assert "No session store configured" in (result.message or "")
    assert state.session_id == ""


def test_new_followed_by_chat_uses_fresh_session(tmp_path: Path) -> None:
    """A chat turn after ``/new`` persists to the new ``<id>.jsonl``, not the old one."""
    from unittest.mock import MagicMock

    from prompt_toolkit import PromptSession

    from simple_cli_coder_with_rag.infrastructure.settings import Settings
    from simple_cli_coder_with_rag.presentation.commands.exit import ExitCommand
    from simple_cli_coder_with_rag.presentation.registry import CommandRegistry
    from simple_cli_coder_with_rag.presentation.repl import Repl

    store = SessionStore(tmp_path)
    old_id = store.current_id()
    state = AppState(
        version=__version__,
        session_id=old_id,
        session_store=store,
        settings=Settings(),
        knowledge=MagicMock(chat=lambda *a, **kw: "ok"),
        history=[],
    )

    inputs = iter(["/new", "hi", "/exit"])
    PromptSession.prompt = lambda self, *a, **kw: next(inputs)

    registry = CommandRegistry()
    registry.register(ExitCommand())
    registry.register(NewCommand())

    Repl(registry=registry, app_state=state, on_exit=lambda: None).run()

    # The old session is empty on disk.
    assert store.read(old_id) == []
    # The new session has the chat turn.
    new_messages = store.read(state.session_id)
    assert len(new_messages) == 2
    assert new_messages[0].role == "user"
    assert new_messages[1].role == "assistant"
