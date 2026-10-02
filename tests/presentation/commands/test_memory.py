"""Tests for ``MemoryCommand`` (DO-12 / NEW_REQUIREMENTS §3).

``/memory`` prints the last 10 messages in the active window — the
content the LLM actually sees on every chat turn. ``NEW_REQUIREMENTS.md``
§3 specifies *"Provide /memory to inspect the active window"*.

The command delegates to ``format_messages_for_display``, which is
also used by ``/resume <id>`` so the two surfaces stay in sync.
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
from simple_cli_coder_with_rag.presentation.commands.memory import (
    MemoryCommand,
    format_messages_for_display,
)


@dataclass
class _StubRepl:
    request_exit_calls: int = 0

    def request_exit(self) -> None:
        self.request_exit_calls += 1


def _context(app_state: AppState) -> CommandContext:
    return CommandContext(repl=_StubRepl(), app_state=app_state)  # type: ignore[arg-type]


def test_memory_prints_each_message_on_its_own_line() -> None:
    """Every message in ``history`` appears as ``[N] ROLE: content`` on its own line."""
    history = [
        UserMessage(content="hello"),
        AssistantMessage(content="hi! how can I help?"),
        UserMessage(content="what's 2+2?"),
        AssistantMessage(content="four"),
    ]
    full_id = "abc1234567deadbeefabc1234567deadbe"
    state = AppState(version=__version__, session_id=full_id, history=history)

    result = MemoryCommand().execute(_context(state))
    message = result.message or ""

    assert "[1] USER: hello" in message
    assert "[2] ASSISTANT: hi! how can I help?" in message
    assert "[3] USER: what's 2+2?" in message
    assert "[4] ASSISTANT: four" in message


def test_memory_uses_one_based_indexing() -> None:
    """The first message is ``[1]``, not ``[0]``."""
    history = [UserMessage(content="first"), AssistantMessage(content="second")]
    state = AppState(
        version=__version__, session_id="abc1234567deadbeefabc1234567deadbe", history=history
    )

    result = MemoryCommand().execute(_context(state))
    message = result.message or ""

    assert "[1] USER: first" in message
    assert "[0]" not in message


def test_memory_with_empty_history_shows_sentinel() -> None:
    """An empty history shows ``(no messages in the active window)``."""
    state = AppState(
        version=__version__,
        session_id="abc1234567deadbeefabc1234567deadbe",
        history=[],
    )

    result = MemoryCommand().execute(_context(state))

    assert result.message == "(no messages in the active window)"


def test_memory_does_not_mutate_state() -> None:
    """The command reads ``AppState.history`` but does not write back."""
    history = [UserMessage(content="hi"), AssistantMessage(content="hello")]
    state = AppState(
        version=__version__,
        session_id="abc1234567deadbeefabc1234567deadbe",
        history=list(history),
    )

    MemoryCommand().execute(_context(state))

    assert state.history == history


def test_memory_returns_continue() -> None:
    """The CommandResult action is ``"continue"``."""
    state = AppState(
        version=__version__,
        session_id="abc1234567deadbeefabc1234567deadbe",
        history=[UserMessage(content="hi"), AssistantMessage(content="hello")],
    )

    result = MemoryCommand().execute(_context(state))

    assert result.action == "continue"


def test_memory_works_on_base_message_instances_after_resume(tmp_path: Path) -> None:
    """Base ``Message`` instances from ``SessionStore.read`` render correctly.

    After ``/resume <id>``, ``app_state.history`` is populated with
    base ``Message`` instances (the role discriminator returns them
    from ``Message.model_validate_json``). The formatter filters on
    ``msg.role`` so both leaf subclasses and base instances render
    the same way.
    """
    store = SessionStore(tmp_path)
    sid = "abc1234567deadbeefabc1234567deadbe"
    store.append(sid, UserMessage(content="resumed user line"))
    store.append(sid, AssistantMessage(content="resumed assistant line"))

    state = AppState(
        version=__version__,
        session_id=sid,
        session_store=store,
        history=store.read(sid),  # base Message instances
    )

    result = MemoryCommand().execute(_context(state))
    message = result.message or ""

    assert "[1] USER: resumed user line" in message
    assert "[2] ASSISTANT: resumed assistant line" in message


def test_memory_uses_shared_formatter() -> None:
    """The command delegates to ``format_messages_for_display``."""
    history = [UserMessage(content="x"), AssistantMessage(content="y")]

    via_command = MemoryCommand().execute(
        _context(AppState(version=__version__, session_id="x", history=history))
    )
    via_helper = format_messages_for_display(history)

    assert via_command.message == via_helper


def test_format_messages_helper_empty() -> None:
    """The helper returns the sentinel string for an empty list."""
    assert format_messages_for_display([]) == "(no messages in the active window)"


def test_format_messages_helper_preserves_order() -> None:
    """The helper renders messages in the order they appear in the list."""
    history = [
        UserMessage(content="a"),
        AssistantMessage(content="b"),
        UserMessage(content="c"),
    ]

    rendered = format_messages_for_display(history)

    assert rendered == "[1] USER: a\n[2] ASSISTANT: b\n[3] USER: c"


def test_memory_includes_role_in_uppercase() -> None:
    """Roles are uppercase (``USER``, ``ASSISTANT``) — easy to scan in a terminal."""
    history = [UserMessage(content="x"), AssistantMessage(content="y")]
    state = AppState(
        version=__version__, session_id="abc1234567deadbeefabc1234567deadbe", history=history
    )

    result = MemoryCommand().execute(_context(state))
    message = result.message or ""

    assert "USER" in message
    assert "ASSISTANT" in message
    assert "user:" not in message  # lowercase 'user:' must NOT appear
    assert "assistant:" not in message  # lowercase 'assistant:' must NOT appear
