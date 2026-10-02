"""Tests for the ``SessionStore``.

Uses :func:`pytest`'s ``tmp_path`` fixture for isolation. Pinned by
``agent-development/04-learn-compaction/tests.md``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.domain.compacted import (
    CompactedSession,
    ErrorRecord,
)
from simple_cli_coder_with_rag.domain.messages import (
    AssistantMessage,
    Message,
    SystemMessage,
    UserMessage,
)


def test_session_store_creates_root(tmp_path: Path) -> None:
    """A non-existent root is created on construction."""
    root = tmp_path / "sessions"
    assert not root.exists()

    SessionStore(root)

    assert root.exists()
    assert root.is_dir()


def test_current_id_is_uuid_v4(tmp_path: Path) -> None:
    """``current_id`` returns distinct, parseable UUIDs."""
    store = SessionStore(tmp_path)

    id1 = store.current_id()
    id2 = store.current_id()

    # Distinct.
    assert id1 != id2
    # Both parse as UUIDs (the standard library tolerates the hyphenated form
    # and the bare hex form, so this is a stable check).
    UUID(id1)
    UUID(id2)


def test_append_creates_file_with_one_jsonl_line(tmp_path: Path) -> None:
    """A single ``append`` writes exactly one valid JSON line."""
    store = SessionStore(tmp_path)
    session_id = store.current_id()

    store.append(session_id, UserMessage(content="hi"))

    lines = [line for line in store.path(session_id).read_text("utf-8").splitlines() if line]
    assert len(lines) == 1
    assert UserMessage.model_validate_json(lines[0]) == UserMessage(content="hi")


def test_append_twice_writes_two_lines(tmp_path: Path) -> None:
    """Two ``append`` calls produce two lines, in order."""
    store = SessionStore(tmp_path)
    session_id = store.current_id()

    store.append(session_id, UserMessage(content="first"))
    store.append(session_id, AssistantMessage(content="second"))

    lines = [line for line in store.path(session_id).read_text("utf-8").splitlines() if line]
    assert len(lines) == 2
    assert UserMessage.model_validate_json(lines[0]) == UserMessage(content="first")
    assert AssistantMessage.model_validate_json(lines[1]) == AssistantMessage(content="second")


def test_read_returns_messages_in_order(tmp_path: Path) -> None:
    """``read`` returns every appended message in append order, across roles."""
    store = SessionStore(tmp_path)
    session_id = store.current_id()

    messages: list[Message] = [
        UserMessage(content="hi"),
        AssistantMessage(content="hello"),
        SystemMessage(content="you are helpful"),
    ]
    for msg in messages:
        store.append(session_id, msg)

    # ``read`` returns base ``Message`` instances (the role discriminator
    # lives on the read path, not on every individual instance), so compare
    # against base ``Message`` values with the same role/content fields.
    assert store.read(session_id) == [
        Message(role="user", content="hi"),
        Message(role="assistant", content="hello"),
        Message(role="system", content="you are helpful"),
    ]


def test_read_missing_file_returns_empty(tmp_path: Path) -> None:
    """``read`` on a non-existent id returns ``[]`` (no exception)."""
    store = SessionStore(tmp_path)

    assert store.read("nonexistent-id") == []


def test_delete_is_idempotent(tmp_path: Path) -> None:
    """``delete`` on a missing id does not raise, and removes an existing file."""
    store = SessionStore(tmp_path)
    session_id = store.current_id()

    # Missing id: no-op, no exception.
    store.delete("nonexistent-id")

    # Existing id: file is removed.
    store.append(session_id, UserMessage(content="hi"))
    assert store.path(session_id).exists()
    store.delete(session_id)
    assert not store.path(session_id).exists()


def test_write_compacted_creates_file(tmp_path: Path) -> None:
    """``write_compacted`` returns a path whose contents round-trip."""
    store = SessionStore(tmp_path)
    session_id = store.current_id()
    compacted = CompactedSession(
        session_id=session_id,
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        summary="summary",
        errors=[ErrorRecord(signature="E", message="boom", occurrences=1)],
    )

    target = store.write_compacted(session_id, compacted)

    assert isinstance(target, Path)
    assert target.exists()
    assert CompactedSession.model_validate_json(target.read_text("utf-8")) == compacted


def test_write_compacted_overwrites(tmp_path: Path) -> None:
    """A second ``write_compacted`` replaces the first; only one file remains."""
    store = SessionStore(tmp_path)
    session_id = store.current_id()

    first = CompactedSession(
        session_id=session_id,
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        summary="first",
    )
    second = CompactedSession(
        session_id=session_id,
        created_at=datetime(2026, 10, 2, tzinfo=UTC),
        summary="second",
    )

    store.write_compacted(session_id, first)
    store.write_compacted(session_id, second)

    # Exactly one compacted file exists for this session, and its content
    # matches the second document (the first was replaced).
    targets = list(tmp_path.glob(f"{session_id}.compacted.json"))
    assert len(targets) == 1
    assert CompactedSession.model_validate_json(targets[0].read_text("utf-8")) == second
