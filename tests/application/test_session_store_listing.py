"""Tests for ``SessionStore.list_sessions`` (DO-12).

Pinned by ``agent-development/12-session-memory-and-saved-chats/tests.md``.

The listing is a metadata-only scan: one tuple per ``<id>.jsonl``
file under the session root, sorted by mtime descending. The
implementation must NOT parse message bodies — only count
non-empty lines and read ``st_mtime``. The cost stays bounded
even on directories with hundreds of sessions, which keeps
``/chats`` responsive on long-running installations.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from simple_cli_coder_with_rag.application.session_store import SessionStore


def _write_jsonl(path: Path, lines: list[str]) -> None:
    """Write ``lines`` joined by ``\\n`` with a final newline."""
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_list_sessions_empty_root_returns_empty_list(tmp_path: Path) -> None:
    """An empty session root yields ``[]`` (not an exception)."""
    store = SessionStore(tmp_path / "fresh")

    assert store.list_sessions() == []


def test_list_sessions_returns_tuples_for_each_jsonl(tmp_path: Path) -> None:
    """One ``.jsonl`` per saved session, sorted by mtime descending."""
    store = SessionStore(tmp_path)
    for sid in ("aaa", "bbb", "ccc"):
        _write_jsonl(store.path(sid), ['{"role":"user","content":"hi"}'])
        # Force an ordering: each subsequent file is touched *later*
        # than the previous, so the listing sorts descending.
        os.utime(store.path(sid), (1_700_000_000 + ord(sid[0]), 1_700_000_000 + ord(sid[0])))

    entries = store.list_sessions()

    assert len(entries) == 3
    # Sorted by mtime descending: ccc (c=99), bbb (b=98), aaa (a=97).
    assert [sid for sid, _mtime, _count in entries] == ["ccc", "bbb", "aaa"]
    for entry in entries:
        assert isinstance(entry, tuple)
        assert len(entry) == 3
        assert isinstance(entry[0], str)
        assert isinstance(entry[1], float)
        assert isinstance(entry[2], int)


def test_list_sessions_counts_non_empty_lines_only(tmp_path: Path) -> None:
    """A trailing empty line is not counted by ``message_count``."""
    store = SessionStore(tmp_path)
    # Three non-empty lines and one trailing empty line.
    _write_jsonl(
        store.path("sid"),
        [
            '{"role":"user","content":"a"}',
            '{"role":"assistant","content":"b"}',
            '{"role":"user","content":"c"}',
            "",  # trailing empty line — must not be counted
        ],
    )

    entries = store.list_sessions()

    assert entries == [("sid", entries[0][1], 3)]


def test_list_sessions_does_not_read_message_bodies(tmp_path: Path) -> None:
    """A malformed JSON line is still counted; the listing never parses."""
    store = SessionStore(tmp_path)
    _write_jsonl(
        store.path("sid"),
        [
            "not valid json",
            '{"role":"user","content":"hi"}',
        ],
    )

    entries = store.list_sessions()

    # Both lines counted (the listing is metadata-only). The read
    # path is what rejects malformed JSON; ``/chats`` never sees it.
    assert entries[0][2] == 2


def test_list_sessions_ignores_non_jsonl_files(tmp_path: Path) -> None:
    """Files that are not ``.jsonl`` (e.g. ``.compacted.json``) are ignored."""
    store = SessionStore(tmp_path)
    _write_jsonl(store.path("real"), ['{"role":"user","content":"hi"}'])
    # A sibling ``.compacted.json`` must not appear in the listing.
    (tmp_path / "real.compacted.json").write_text("{}", encoding="utf-8")
    # A stray file with a different extension must also be ignored.
    (tmp_path / "stray.txt").write_text("ignored", encoding="utf-8")

    entries = store.list_sessions()

    assert [sid for sid, _mtime, _count in entries] == ["real"]


def test_list_sessions_handles_missing_root(tmp_path: Path) -> None:
    """A root removed after construction returns ``[]`` without raising."""
    store = SessionStore(tmp_path / "s")
    # The constructor created the root; delete it from under the store.
    import shutil

    shutil.rmtree(tmp_path / "s")

    assert store.list_sessions() == []


@pytest.mark.skipif(
    os.geteuid() == 0 if hasattr(os, "geteuid") else False,
    reason="chmod 000 is a no-op for root",
)
def test_list_sessions_skips_unreadable_files_silently(tmp_path: Path) -> None:
    """A file with no read bits is omitted (no exception)."""
    if sys.platform == "win32":
        pytest.skip("POSIX-only chmod semantics")
    store = SessionStore(tmp_path)
    good_path = store.path("good")
    bad_path = store.path("bad")
    _write_jsonl(good_path, ['{"role":"user","content":"hi"}'])
    _write_jsonl(bad_path, ['{"role":"user","content":"hi"}'])
    bad_path.chmod(0o000)

    try:
        entries = store.list_sessions()
    finally:
        # Restore so the test runner can clean up tmp_path.
        bad_path.chmod(0o644)

    assert [sid for sid, _mtime, _count in entries] == ["good"]
