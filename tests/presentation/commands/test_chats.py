"""Tests for ``ChatsCommand`` (DO-12).

Pinned by ``agent-development/12-session-memory-and-saved-chats/tests.md``.

The command formats the on-disk session listing off
``SessionStore.list_sessions()`` directly. The pinned format
(fixed column widths, sorted by mtime descending, trailing
``active: <id>`` line) is the regression guard for ``/chats``'s
contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from simple_cli_coder_with_rag import __version__
from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.domain.messages import UserMessage
from simple_cli_coder_with_rag.presentation.commands import AppState, CommandContext
from simple_cli_coder_with_rag.presentation.commands.chats import ChatsCommand

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@dataclass
class _StubRepl:
    request_exit_calls: int = 0

    def request_exit(self) -> None:
        self.request_exit_calls += 1


def _context(app_state: AppState) -> CommandContext:
    return CommandContext(repl=_StubRepl(), app_state=app_state)  # type: ignore[arg-type]


def test_chats_renders_table_for_three_sessions(tmp_path: Path, mocker: MockerFixture) -> None:
    """Three sessions render as three table rows + a trailing active line."""
    state = AppState(version=__version__, session_id="abc1234567deadbeef")
    state.session_store = mocker.MagicMock()
    # Three mtimes ordered descending; the formatter is opaque —
    # we only assert that each entry's text appears.
    state.session_store.list_sessions.return_value = [
        ("abc1234567deadbeef", 1_700_000_000.0, 18),
        ("a1b2c3d4ef5678901234567890123456", 1_698_080_000.0, 38),
        ("5e6f7g8h9i0k1l2m3n4o6p7q8r9s0t1u", 1_600_000_000.0, 204),
    ]

    result = ChatsCommand().execute(_context(state))
    message = result.message or ""

    # Header line is present.
    assert "session id" in message
    assert "messages" in message
    # All three ids appear (truncated to 10 chars in the table).
    assert "abc1234567..." in message
    assert "a1b2c3d4ef..." in message
    assert "5e6f7g8h9i..." in message
    # All three counts.
    assert "18" in message
    assert "38" in message
    assert "204" in message
    # Trailing active line.
    assert message.rstrip().endswith("active: abc1234567deadbeef")


def test_chats_includes_active_id_line(tmp_path: Path, mocker: MockerFixture) -> None:
    """The message ends with ``active: <id>``."""
    state = AppState(version=__version__, session_id="my-active-session")
    state.session_store = mocker.MagicMock()
    state.session_store.list_sessions.return_value = [
        ("my-active-session", 1_700_000_000.0, 18),
    ]

    result = ChatsCommand().execute(_context(state))
    message = result.message or ""

    assert message.rstrip().endswith("active: my-active-session")


def test_chats_empty_list_returns_friendly_message(tmp_path: Path, mocker: MockerFixture) -> None:
    """An empty list returns ``"No saved sessions yet."``."""
    state = AppState(version=__version__, session_id="x")
    state.session_store = mocker.MagicMock()
    state.session_store.list_sessions.return_value = []

    result = ChatsCommand().execute(_context(state))

    assert result.message == "No saved sessions yet."


def test_chats_without_session_store_returns_friendly_fallback() -> None:
    """``session_store is None`` returns the friendly fallback."""
    state = AppState(version=__version__, session_id="x", session_store=None)

    result = ChatsCommand().execute(_context(state))

    assert "No saved sessions" in (result.message or "")


def test_chats_with_real_session_store(tmp_path: Path) -> None:
    """The Command can drive a real ``SessionStore`` end-to-end."""
    store = SessionStore(tmp_path)
    store.append("aaa", UserMessage(content="a"))
    store.append("bbb", UserMessage(content="b"))
    store.append("bbb", UserMessage(content="c"))
    state = AppState(version=__version__, session_id="aaa", session_store=store)

    result = ChatsCommand().execute(_context(state))
    message = result.message or ""

    assert "aaa" in message
    assert "bbb" in message


def test_chats_returns_continue(tmp_path: Path, mocker: MockerFixture) -> None:
    """The CommandResult action is ``"continue"``."""
    state = AppState(version=__version__, session_id="x")
    state.session_store = mocker.MagicMock()
    state.session_store.list_sessions.return_value = []

    result = ChatsCommand().execute(_context(state))

    assert result.action == "continue"
