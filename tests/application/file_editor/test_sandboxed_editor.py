"""Behavioural tests for ``SandboxedFileEditor`` (DO-10).

Pinned by ``agent-development/10-file-editing/tests.md``.

The ``tmp_path`` fixture from pytest gives every test a clean, isolated
sandbox root, so path-traversal / symlink-escape tests can probe the
sandbox without leaking state across tests.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from simple_cli_coder_with_rag.application.file_editor.sandboxed_editor import (
    SandboxedFileEditor,
)
from simple_cli_coder_with_rag.domain.file_editor import (
    AmbiguousEdit,
    FileNotFound,
    PathNotAllowed,
    TextNotFound,
)

if TYPE_CHECKING:
    pass


def test_read_returns_contents(tmp_path: Path) -> None:
    """Reading a file inside the sandbox returns its content verbatim."""
    (tmp_path / "foo.txt").write_text("hello", encoding="utf-8")
    editor = SandboxedFileEditor(root=tmp_path)
    assert editor.read("foo.txt") == "hello"


def test_read_missing_raises(tmp_path: Path) -> None:
    """Reading a non-existent file raises ``FileNotFound`` (re-export)."""
    editor = SandboxedFileEditor(root=tmp_path)
    with pytest.raises(FileNotFound):
        editor.read("nope.txt")


def test_write_creates_file(tmp_path: Path) -> None:
    """``write`` creates the file inside the sandbox with the given content."""
    editor = SandboxedFileEditor(root=tmp_path)
    editor.write("foo.txt", "hello")
    assert (tmp_path / "foo.txt").read_text(encoding="utf-8") == "hello"


def test_write_creates_parent_dirs(tmp_path: Path) -> None:
    """``write`` creates missing parent directories (the sandbox is the limit)."""
    editor = SandboxedFileEditor(root=tmp_path)
    editor.write("a/b/c.txt", "x")
    assert (tmp_path / "a" / "b" / "c.txt").read_text(encoding="utf-8") == "x"


def test_edit_replaces_text(tmp_path: Path) -> None:
    """``edit`` replaces ``old_text`` with ``new_text`` when ``old_text`` appears once."""
    (tmp_path / "foo.txt").write_text("hello world", encoding="utf-8")
    editor = SandboxedFileEditor(root=tmp_path)
    editor.edit("foo.txt", "hello", "hi")
    assert (tmp_path / "foo.txt").read_text(encoding="utf-8") == "hi world"


def test_edit_missing_text_raises(tmp_path: Path) -> None:
    """``edit`` raises ``TextNotFound`` when ``old_text`` is absent."""
    (tmp_path / "foo.txt").write_text("hello", encoding="utf-8")
    editor = SandboxedFileEditor(root=tmp_path)
    with pytest.raises(TextNotFound):
        editor.edit("foo.txt", "bye", "x")


def test_edit_ambiguous_text_raises(tmp_path: Path) -> None:
    """``edit`` raises ``AmbiguousEdit`` when ``old_text`` appears more than once."""
    (tmp_path / "foo.txt").write_text("a a", encoding="utf-8")
    editor = SandboxedFileEditor(root=tmp_path)
    with pytest.raises(AmbiguousEdit):
        editor.edit("foo.txt", "a", "b")


def test_edit_is_atomic(tmp_path: Path) -> None:
    """A failed ``edit`` leaves the file content untouched (read -> assert -> write)."""
    (tmp_path / "foo.txt").write_text("hello", encoding="utf-8")
    editor = SandboxedFileEditor(root=tmp_path)
    with pytest.raises(TextNotFound):
        editor.edit("foo.txt", "absent", "x")
    assert (tmp_path / "foo.txt").read_text(encoding="utf-8") == "hello"


def test_read_path_traversal_raises(tmp_path: Path) -> None:
    """Path traversal (``../foo``) is rejected by the sandbox."""
    editor = SandboxedFileEditor(root=tmp_path)
    with pytest.raises(PathNotAllowed):
        editor.read("../foo")


def test_read_absolute_outside_root_raises(tmp_path: Path) -> None:
    """An absolute path outside the sandbox root is rejected."""
    editor = SandboxedFileEditor(root=tmp_path)
    with pytest.raises(PathNotAllowed):
        editor.read("/etc/passwd")


def test_symlink_escape_raises(tmp_path: Path) -> None:
    """A symlink inside the sandbox that points outside is rejected.

    ``Path.resolve()`` follows symlinks by default — that's the whole point of
    this test. The symlink target (``/etc/passwd``) is resolved to an absolute
    path *outside* the sandbox root, so the sandbox rejects the read.
    """
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks unavailable on this platform")
    link = tmp_path / "link"
    # ``/etc/passwd`` exists on virtually every Unix; pick a portable target.
    target = "/etc/passwd"
    if not Path(target).exists():  # pragma: no cover - platform-specific guard
        pytest.skip(f"symlink target {target!r} not present on this host")
    try:
        os.symlink(target, str(link))
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - platform-specific
        pytest.skip(f"symlink creation not permitted: {exc}")

    editor = SandboxedFileEditor(root=tmp_path)
    with pytest.raises(PathNotAllowed):
        editor.read("link")


def test_allowed_globs_restrict(tmp_path: Path) -> None:
    """``allowed_globs`` narrows the sandbox: non-matching paths are rejected."""
    (tmp_path / "foo.py").write_text("py", encoding="utf-8")
    (tmp_path / "foo.txt").write_text("txt", encoding="utf-8")
    editor = SandboxedFileEditor(root=tmp_path, allowed_globs=["**/*.py"])

    with pytest.raises(PathNotAllowed):
        editor.read("foo.txt")
    assert editor.read("foo.py") == "py"


def test_write_to_disallowed_glob_raises(tmp_path: Path) -> None:
    """``write`` honours ``allowed_globs`` the same way ``read`` does."""
    editor = SandboxedFileEditor(root=tmp_path, allowed_globs=["**/*.py"])
    with pytest.raises(PathNotAllowed):
        editor.write("foo.txt", "x")


def test_default_glob_allows_everything(tmp_path: Path) -> None:
    """The default ``allowed_globs`` is ``["**/*"]``, so any sandbox path is accepted."""
    (tmp_path / "any.ext").write_text("ok", encoding="utf-8")
    editor = SandboxedFileEditor(root=tmp_path)
    assert editor.read("any.ext") == "ok"
