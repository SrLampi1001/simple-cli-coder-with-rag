"""Tests for ``ResumeCommand`` (DO-12).

Pinned by ``agent-development/12-session-memory-and-saved-chats/tests.md``.

The single most important contract here is
``test_resume_does_not_call_llm`` — it is the regression guard
against re-introducing the mis-planned LLM-driven compaction
step. If a future refactor adds a compactor call to
``ResumeCommand``, this test fails.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from simple_cli_coder_with_rag import __version__
from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.domain.messages import (
    AssistantMessage,
    Message,
    UserMessage,
)
from simple_cli_coder_with_rag.presentation.commands import AppState, CommandContext
from simple_cli_coder_with_rag.presentation.commands.resume import ResumeCommand

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@dataclass
class _StubRepl:
    request_exit_calls: int = 0

    def request_exit(self) -> None:
        self.request_exit_calls += 1


def _context(app_state: AppState, args: str = "") -> CommandContext:
    return CommandContext(repl=_StubRepl(), app_state=app_state, args=args)  # type: ignore[arg-type]


def _write_transcript(store: SessionStore, session_id: str, count: int) -> None:
    """Append ``count`` user/assistant pairs to ``session_id``."""
    for i in range(count):
        store.append(session_id, UserMessage(content=f"msg-{i}"))
        store.append(session_id, AssistantMessage(content=f"reply-{i}"))


def test_resume_with_valid_id_replaces_history_with_last_n(tmp_path: Path) -> None:
    """A 50-message transcript is trimmed to the last 20 (= 10 turns)."""
    store = SessionStore(tmp_path)
    _write_transcript(store, "abc1234567deadbeef", 25)  # 50 messages

    state = AppState(
        version=__version__,
        session_id="",
        session_store=store,
        history=[],
    )

    result = ResumeCommand().execute(_context(state, "abc1234567deadbeef"))
    message = result.message or ""

    assert result.action == "continue"
    assert "resumed abc1234567deadbeef (20 of 50 messages loaded)" in message
    assert state.session_id == "abc1234567deadbeef"
    assert len(state.history) == 20
    # The last 10 turns (= 20 messages) of the original transcript.
    # ``SessionStore.read`` returns base ``Message`` instances, so
    # compare against the same shape here.
    assert state.history[-1] == Message(role="assistant", content="reply-24")
    assert state.history[0] == Message(role="user", content="msg-15")


def test_resume_with_short_transcript_loads_verbatim(tmp_path: Path) -> None:
    """A 3-message transcript is loaded as-is (no padding)."""
    store = SessionStore(tmp_path)
    store.append("short", UserMessage(content="a"))
    store.append("short", AssistantMessage(content="A"))
    store.append("short", UserMessage(content="b"))

    state = AppState(version=__version__, session_id="", session_store=store, history=[])

    result = ResumeCommand().execute(_context(state, "short"))

    assert result.action == "continue"
    assert "3 of 3 messages loaded" in (result.message or "")
    # ``SessionStore.read`` returns base ``Message`` instances.
    assert state.history == [
        Message(role="user", content="a"),
        Message(role="assistant", content="A"),
        Message(role="user", content="b"),
    ]
    assert state.session_id == "short"


def test_resume_missing_id_returns_usage_message(tmp_path: Path) -> None:
    """``/resume`` with no argument returns the usage message."""
    store = SessionStore(tmp_path)
    state = AppState(version=__version__, session_id="", session_store=store, history=[])

    result = ResumeCommand().execute(_context(state, ""))

    assert result.message == "usage: /resume <session-id>"
    assert state.session_id == ""
    assert state.history == []


def test_resume_unknown_id_returns_friendly_message(tmp_path: Path) -> None:
    """``/resume nope`` (no transcript on disk) returns the friendly fallback."""
    store = SessionStore(tmp_path)
    state = AppState(version=__version__, session_id="", session_store=store, history=[])

    result = ResumeCommand().execute(_context(state, "nope"))

    assert result.message == "unknown session 'nope'. Run `/chats` to list."
    assert state.session_id == ""
    assert state.history == []


def test_resume_without_session_store_returns_friendly_fallback() -> None:
    """``session_store is None`` returns the friendly fallback."""
    state = AppState(version=__version__, session_id="", session_store=None, history=[])

    result = ResumeCommand().execute(_context(state, "anything"))

    assert "No session store configured" in (result.message or "")


def test_resume_does_not_call_llm(tmp_path: Path, mocker: MockerFixture) -> None:
    """The command must not invoke the LLM — the regression guard for DO-12."""
    store = SessionStore(tmp_path)
    _write_transcript(store, "abc1234567deadbeef", 3)
    llm = mocker.MagicMock()
    state = AppState(
        version=__version__,
        session_id="",
        session_store=store,
        history=[],
    )
    state.knowledge = mocker.MagicMock()
    state.knowledge.llm = llm  # type: ignore[attr-defined]

    ResumeCommand().execute(_context(state, "abc1234567deadbeef"))

    # No chat call, no complete_with_tools call, no anything LLM-shaped.
    llm.complete.assert_not_called()
    llm.complete_with_tools.assert_not_called()


def test_resume_overwrites_existing_history(tmp_path: Path) -> None:
    """An existing /app_state.history is fully replaced (no merge, no append)."""
    store = SessionStore(tmp_path)
    _write_transcript(store, "abc1234567deadbeef", 2)  # 4 messages

    state = AppState(
        version=__version__,
        session_id="current",
        session_store=store,
        history=[UserMessage(content="old"), AssistantMessage(content="OLD")],
    )

    ResumeCommand().execute(_context(state, "abc1234567deadbeef"))

    # The old messages are gone; the resumed transcript is the only thing left.
    assert len(state.history) == 4
    assert state.history[0] == Message(role="user", content="msg-0")
    assert state.history[-1] == Message(role="assistant", content="reply-1")
    assert state.session_id == "abc1234567deadbeef"


def test_resume_strips_trailing_whitespace_from_arg(tmp_path: Path) -> None:
    """A trailing newline / extra whitespace in the arg is tolerated."""
    store = SessionStore(tmp_path)
    _write_transcript(store, "abc1234567deadbeef", 1)

    state = AppState(version=__version__, session_id="", session_store=store, history=[])

    result = ResumeCommand().execute(_context(state, "  abc1234567deadbeef  \n"))

    assert "resumed abc1234567deadbeef" in (result.message or "")
    assert state.session_id == "abc1234567deadbeef"


def test_resume_with_custom_cap(tmp_path: Path) -> None:
    """``int_history_cap=2`` keeps the last 4 messages (= 2 turns)."""
    from simple_cli_coder_with_rag.infrastructure.settings import Settings

    store = SessionStore(tmp_path)
    _write_transcript(store, "abc1234567deadbeef", 10)  # 20 messages

    settings = Settings(int_history_cap=2)
    state = AppState(
        version=__version__,
        session_id="",
        session_store=store,
        history=[],
        settings=settings,
    )

    result = ResumeCommand().execute(_context(state, "abc1234567deadbeef"))

    assert "4 of 20 messages loaded" in (result.message or "")
    assert len(state.history) == 4
    assert state.history[-1] == Message(role="assistant", content="reply-9")
    assert state.history[0] == Message(role="user", content="msg-8")
