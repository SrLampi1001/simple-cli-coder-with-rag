"""File-editor domain — the ``FileEditor`` Protocol and its exception hierarchy.

Pinned by ``agent-development/10-file-editing/contracts.md``. DO-10 is the
final OBJECTIVES bullet (*"The AI agent can edit files"*); the
``FileEditor`` Protocol is the Strategy seam the application layer talks to,
and the four exceptions are the typed contract that lets the tool-loop in
``KnowledgeService.chat`` distinguish sandbox rejections (``PathNotAllowed``)
from input-shape errors (``TextNotFound`` / ``AmbiguousEdit``).

Architectural notes:

* The Protocol lives in :mod:`simple_cli_coder_with_rag.domain` (the
  upper layer in the ``import-linter`` ``layers`` contract). The concrete
  implementation :class:`SandboxedFileEditor` lives in
  :mod:`simple_cli_coder_with_rag.application.file_editor` — application
  layer below infrastructure, so it can import the Protocol without
  leaking any vendor types upward.
* The exceptions inherit from stdlib base classes
  (``PermissionError`` / ``FileNotFoundError`` / ``ValueError``) so
  generic ``except PermissionError`` / ``except ValueError`` catches them
  when a caller does not know about the project-owned hierarchy. This is
  the standard "raise a specific type, catch a generic type" pattern.
* No ``os`` / ``subprocess`` / shell imports — the Protocol intentionally
  forbids escape hatches. The contract asserts this in
  ``contracts.md`` (*"No application-layer module imports os.system,
  subprocess, or any shell-execution library"*).
"""

from __future__ import annotations

from pathlib import Path  # noqa: F401  -- re-exported below for consumers
from typing import Protocol


class FileEditor(Protocol):
    """Strategy interface for reading and editing files inside an editor sandbox.

    Implementations are responsible for:

    * **Sandboxing** every path against a configured root (rejecting
      ``..`` traversal, symlink escape, and absolute paths outside the
      root).
    * Optionally restricting the sandbox further via an ``allowed_globs``
      allow-list.
    * Creating parent directories for ``write`` / ``edit`` so a single
      ``write("nested/dir/foo.txt", ...)`` call does not require a
      separate mkdir step.
    * Making ``edit`` atomic — a failed assertion (``old_text`` missing
      or ambiguous) must leave the file content untouched.
    """

    def read(self, path: str) -> str:
        """Return the UTF-8 decoded content of ``path`` inside the sandbox.

        Raises :class:`PathNotAllowed` when ``path`` is outside the
        sandbox (traversal, absolute, symlink-escape, or disallowed by
        ``allowed_globs``). Raises :class:`FileNotFound` when the file
        does not exist.
        """
        ...

    def write(self, path: str, content: str) -> None:
        """Write ``content`` to ``path`` (UTF-8), creating parent directories.

        Raises :class:`PathNotAllowed` when ``path`` is outside the sandbox.
        Overwrites any existing file at ``path``.
        """
        ...

    def edit(self, path: str, old_text: str, new_text: str) -> None:
        """Replace ``old_text`` with ``new_text`` in ``path``.

        The edit is **atomic**: the implementation reads the file,
        asserts ``old_text`` appears **exactly once**, then writes the
        new content. If the assertion fails, the original file is left
        untouched.

        Raises:
            PathNotAllowed: ``path`` is outside the sandbox.
            FileNotFound: ``path`` does not exist.
            TextNotFound: ``old_text`` does not appear in the file.
            AmbiguousEdit: ``old_text`` appears more than once.
        """
        ...


class PathNotAllowed(PermissionError):  # noqa: N818 -- name pinned by the DO-10 contracts
    """Raised when a ``FileEditor`` operation targets a path outside the sandbox.

    Inherits from :class:`PermissionError` so a generic
    ``except PermissionError`` catches it without importing the
    project-owned type.
    """


class FileNotFound(FileNotFoundError):  # noqa: N818 -- name pinned by the DO-10 contracts
    """Raised when ``FileEditor.read`` is called on a non-existent path.

    Re-exports the stdlib :class:`FileNotFoundError` under the
    project-owned name so consumers can ``except FileNotFound`` without
    importing ``builtins``. The hierarchy is preserved — a generic
    ``except FileNotFoundError`` catches it too.
    """


class TextNotFound(ValueError):  # noqa: N818 -- name pinned by the DO-10 contracts
    """Raised when ``FileEditor.edit`` cannot find ``old_text`` in the file.

    A :class:`ValueError` subclass — the missing text is a caller-supplied
    argument mistake, so a generic ``except ValueError`` catches it.
    """


class AmbiguousEdit(ValueError):  # noqa: N818 -- name pinned by the DO-10 contracts
    """Raised when ``FileEditor.edit`` finds ``old_text`` more than once.

    Also a :class:`ValueError` subclass — ambiguous matches make the
    intent of the edit undefined, so the caller must re-supply a more
    specific ``old_text``.
    """


__all__ = [
    "AmbiguousEdit",
    "FileEditor",
    "FileNotFound",
    "PathNotAllowed",
    "TextNotFound",
]
