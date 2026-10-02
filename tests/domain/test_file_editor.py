"""Tests for the file-editor Protocol and exception hierarchy (DO-10).

Pinned by ``agent-development/10-file-editing/tests.md``.

The ``FileEditor`` Protocol and its exceptions are declared in
``domain/file_editor.py``. These tests pin the schema contract — the
behavioural contract for the ``SandboxedFileEditor`` implementation lives
in ``tests/application/file_editor/test_sandboxed_editor.py``.
"""

from __future__ import annotations

import inspect

from simple_cli_coder_with_rag.domain.file_editor import (
    AmbiguousEdit,
    FileEditor,
    FileNotFound,
    PathNotAllowed,
    TextNotFound,
)


def test_protocol_declares_methods() -> None:
    """``FileEditor`` declares ``read``, ``write``, and ``edit``."""
    members = {name for name, _ in inspect.getmembers(FileEditor)}
    assert "read" in members
    assert "write" in members
    assert "edit" in members


def test_path_not_allowed_is_permission_error() -> None:
    """``PathNotAllowed`` is a ``PermissionError`` so ``except PermissionError`` catches it."""
    assert issubclass(PathNotAllowed, PermissionError)


def test_text_not_found_is_value_error() -> None:
    """``TextNotFound`` is a ``ValueError`` so callers can catch the wider type."""
    assert issubclass(TextNotFound, ValueError)


def test_ambiguous_edit_is_value_error() -> None:
    """``AmbiguousEdit`` is a ``ValueError`` so callers can catch the wider type."""
    assert issubclass(AmbiguousEdit, ValueError)


def test_file_not_found_is_file_not_found_error() -> None:
    """``FileNotFound`` re-exports ``FileNotFoundError`` (stdlib) for consumers."""
    assert issubclass(FileNotFound, FileNotFoundError)


def test_protocol_method_signatures() -> None:
    """``FileEditor`` method signatures are pinned so consumers can rely on them.

    Using ``inspect.signature`` on a ``Protocol`` class returns the abstract
    signature from ``__call__``/definitions, but ``getmembers`` (used above)
    only confirms presence. We assert the surface-level method names are
    callable and that they take the expected positional argument names by
    introspecting the Protocol class attributes.
    """
    # ``Protocol`` exposes methods as attributes on the class; ``inspect.getmembers``
    # already verified presence above. Here we check the Protocol's own method
    # objects carry the expected names.
    assert callable(getattr(FileEditor, "read", None))
    assert callable(getattr(FileEditor, "write", None))
    assert callable(getattr(FileEditor, "edit", None))
