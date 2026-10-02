"""Tests for ``MemoryCommand`` (DO-12).

Pinned by ``agent-development/12-session-memory-and-saved-chats/tests.md``.

The command formats the active conversation window off
``AppState`` directly — no LLM call, no session-store read.
The pinned format (multi-line, with a fixed 60-char truncation
on the last user / assistant line) is the regression guard for
``/memory``'s contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from simple_cli_coder_with_rag import __version__
from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.domain.messages import (
    AssistantMessage,
    UserMessage,
)
from simple_cli_coder_with_rag.presentation.commands import AppState, CommandContext
from simple_cli_coder_with_rag.presentation.commands.memory import MemoryCommand

if TYPE_CHECKING:
    pass


@dataclass
class _StubRepl:
    request_exit_calls: int = 0

    def request_exit(self) -> None:
        self.request_exit_calls += 1


def _context(app_state: AppState) -> CommandContext:
    return CommandContext(repl=_StubRepl(), app_state=app_state)  # type: ignore[arg-type]


def test_memory_with_active_session_returns_readout(tmp_path: Path) -> None:
    """The readout contains every pinned line and the full session id."""
    store = SessionStore(tmp_path)
    full_id = "abc1234567deadbeefabc1234567deadbe"  # 32 chars
    state = AppState(
        version=__version__,
        session_id=full_id,
        session_store=store,
        history=[UserMessage(content="hi"), AssistantMessage(content="hello!")],
    )

    result = MemoryCommand().execute(_context(state))
    message = result.message or ""

    # Full id is shown so the user can copy-paste it into /resume.
    assert f"session:    {full_id}" in message
    # Short id preview sits underneath as a quick visual cue.
    assert "(short:   abc12345)" in message
    assert "messages:   2" in message
    assert "last user:  hi" in message
    assert "last assistant: hello!" in message
    assert "turns:" in message


def test_memory_with_empty_history_shows_no_messages_yet() -> None:
    """An empty history shows ``(no messages yet)`` on both tail lines."""
    state = AppState(
        version=__version__,
        session_id="abc1234567deadbeefabc1234567deadbe",
        history=[],
    )

    result = MemoryCommand().execute(_context(state))
    message = result.message or ""

    assert "last user:  (no messages yet)" in message
    assert "last assistant: (no messages yet)" in message


def test_memory_truncates_long_content_to_60_chars() -> None:
    """Long content ends with ``...`` (the truncation marker) after 60 chars."""
    long_content = "x" * 80
    state = AppState(
        version=__version__,
        session_id="abc1234567deadbeefabc1234567deadbe",
        history=[UserMessage(content=long_content), AssistantMessage(content="ok")],
    )

    result = MemoryCommand().execute(_context(state))
    message = result.message or ""

    # The line should contain 60 'x' followed by the truncation marker.
    # The marker is the ellipsis character '…'.
    truncated_line = next(line for line in message.splitlines() if line.startswith("last user:"))
    assert "x" * 60 in truncated_line
    assert "…" in truncated_line


def test_memory_without_session_id_returns_friendly() -> None:
    """Empty ``session_id`` → friendly fallback (regardless of ``session_store``)."""
    state = AppState(version=__version__, session_id="", session_store=None, history=[])

    result = MemoryCommand().execute(_context(state))

    assert "No active session" in (result.message or "")


def test_memory_does_not_mutate_state() -> None:
    """The command reads ``AppState`` but does not write back."""
    history = [UserMessage(content="hi"), AssistantMessage(content="hello")]
    state = AppState(
        version=__version__,
        session_id="abc1234567deadbeefabc1234567deadbe",
        history=list(history),
    )

    MemoryCommand().execute(_context(state))

    assert state.history == history
    assert state.session_id == "abc1234567deadbeefabc1234567deadbe"


def test_memory_returns_continue() -> None:
    """The CommandResult action is ``"continue"``."""
    state = AppState(
        version=__version__,
        session_id="abc1234567deadbeefabc1234567deadbe",
        history=[UserMessage(content="hi"), AssistantMessage(content="hello")],
    )

    result = MemoryCommand().execute(_context(state))

    assert result.action == "continue"


def test_memory_counts_user_assistant_pairs_as_turns() -> None:
    """``turns:`` is the count of completed user/assistant pairs (half the messages)."""
    history = [
        UserMessage(content="a"),
        AssistantMessage(content="A"),
        UserMessage(content="b"),
        AssistantMessage(content="B"),
        UserMessage(content="c"),
        AssistantMessage(content="C"),
    ]
    state = AppState(
        version=__version__,
        session_id="abc1234567deadbeefabc1234567deadbe",
        history=history,
    )

    result = MemoryCommand().execute(_context(state))
    message = result.message or ""

    assert "turns:      3 / 10" in message


def test_memory_finds_last_user_after_resume(tmp_path: Path) -> None:
    """The ``last user:`` / ``last assistant:`` lines work on a resumed session.

    ``SessionStore.read`` returns base ``Message`` instances (not the
    ``UserMessage`` / ``AssistantMessage`` leaf subclasses). The
    earlier strict ``isinstance`` check made the readout print
    ``(no messages yet)`` on a freshly resumed session — a real
    regression bug surfaced by the workflow test.
    """
    from simple_cli_coder_with_rag.application.session_store import SessionStore
    from simple_cli_coder_with_rag.domain.messages import AssistantMessage, UserMessage

    store = SessionStore(tmp_path)
    sid = "abc1234567deadbeefabc1234567deadbe"
    store.append(sid, UserMessage(content="first user line"))
    store.append(sid, AssistantMessage(content="first assistant reply"))
    store.append(sid, UserMessage(content="second user line"))
    store.append(sid, AssistantMessage(content="second assistant reply"))

    state = AppState(
        version=__version__,
        session_id=sid,
        session_store=store,
        history=store.read(sid),  # base Message instances — the bug trigger
    )

    result = MemoryCommand().execute(_context(state))
    message = result.message or ""

    assert "last user:  second user line" in message
    assert "last assistant: second assistant reply" in message
    assert "(no messages yet)" not in message
