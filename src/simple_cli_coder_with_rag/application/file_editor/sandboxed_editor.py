"""``SandboxedFileEditor`` — the application-layer file-editor Strategy.

Pinned by ``agent-development/10-file-editing/contracts.md`` and
``workflow.md`` (DO-10 implementation notes).

The class enforces four sandbox invariants, in this order:

1. **Resolve against the sandbox root.** Every ``path`` argument is
   joined onto :attr:`root` and then resolved with
   :meth:`Path.resolve`, which follows symlinks. The resolved path
   must equal :attr:`root` or live *underneath* it; anything else is
   rejected with :class:`~simple_cli_coder_with_rag.domain.file_editor.PathNotAllowed`.

2. **Glob allow-list.** When ``allowed_globs`` is supplied, each glob is
   matched against the resolved path *relative to* the sandbox root via
   :func:`fnmatch.fnmatch`. At least one glob must match; otherwise the
   operation is rejected. The default is ``["**/*"]`` — every file
   beneath the root.

3. **Atomic edit.** :meth:`edit` reads the file, asserts that ``old_text``
   appears **exactly once**, and writes the new content. A failed
   assertion leaves the file untouched.

4. **Parent directory creation.** :meth:`write` (and the success path of
   :meth:`edit`) call ``Path.parent.mkdir(parents=True, exist_ok=True)``
   so a single ``write("a/b/c.txt", ...)`` works without a separate
   mkdir.

Architectural notes:

* This module imports from :mod:`simple_cli_coder_with_rag.domain` only
  (the Protocol + exception hierarchy). No vendor SDKs, no
  :mod:`simple_cli_coder_with_rag.infrastructure` imports. The
  ``import-linter`` ``layers`` contract enforces this.
* ``os.system``, ``subprocess``, and any shell-execution library are
  deliberately absent. The agent edits files **through this API** —
  never via a shell — to keep the LLM from running arbitrary commands
  on the user's machine.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING

from simple_cli_coder_with_rag.domain.file_editor import (
    AmbiguousEdit,
    FileNotFound,
    PathNotAllowed,
    TextNotFound,
)

if TYPE_CHECKING:
    pass


_DEFAULT_GLOBS: tuple[str, ...] = ("**/*",)


class SandboxedFileEditor:
    """File editor that confines every operation to a configurable root directory.

    The sandbox is the only thing standing between an LLM-driven tool call
    and the user's filesystem — the four invariants in the module docstring
    are the security boundary.
    """

    def __init__(self, root: Path, *, allowed_globs: list[str] | None = None) -> None:
        """Remember ``root`` (resolved to an absolute path) and the glob allow-list.

        ``root`` is resolved immediately so a ``root`` containing ``..``
        or a symlink cannot smuggle paths outside the intended directory.

        ``allowed_globs`` defaults to ``["**/*"]`` — every file beneath
        the root. Empty lists are rejected (an empty allow-list would
        reject every path, which is almost always a mistake).
        """
        resolved_root = Path(root).expanduser().resolve()
        if not resolved_root.exists():  # pragma: no cover - defensive
            raise FileNotFound(f"editor root does not exist: {resolved_root}")
        if not resolved_root.is_dir():  # pragma: no cover - defensive
            raise NotADirectoryError(f"editor root is not a directory: {resolved_root}")
        self._root = resolved_root
        self._allowed_globs: tuple[str, ...] = (
            tuple(allowed_globs) if allowed_globs is not None else _DEFAULT_GLOBS
        )
        if not self._allowed_globs:  # pragma: no cover - defensive
            raise ValueError("allowed_globs must be a non-empty list")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read(self, path: str) -> str:
        """Return the UTF-8 content of ``path`` inside the sandbox.

        Raises :class:`FileNotFound` when the file does not exist;
        :class:`PathNotAllowed` when ``path`` escapes the sandbox or
        fails the glob allow-list.
        """
        resolved = self._resolve_and_authorize(path)
        if not resolved.exists() or not resolved.is_file():
            raise FileNotFound(str(resolved))
        return resolved.read_text(encoding="utf-8")

    def write(self, path: str, content: str) -> None:
        """Write ``content`` to ``path`` (UTF-8), creating parent directories.

        Raises :class:`PathNotAllowed` when ``path`` escapes the sandbox
        or fails the glob allow-list.
        """
        resolved = self._resolve_and_authorize(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")

    def edit(self, path: str, old_text: str, new_text: str) -> None:
        """Replace ``old_text`` with ``new_text`` in ``path``, atomically.

        Implementation:

        1. Resolve + authorise ``path`` (raises ``PathNotFound`` /
           ``PathNotAllowed`` before any read).
        2. Read the current content (raises ``FileNotFound`` if missing).
        3. Count occurrences of ``old_text``:

           * 0 → raise :class:`TextNotFound`.
           * >1 → raise :class:`AmbiguousEdit`.
           * exactly 1 → fall through.

        4. Compute the new content and write it back. If the read
           succeeds but the write fails for any reason, the original
           file is untouched (no partial write ever reaches disk).

        Raises :class:`PathNotAllowed`, :class:`FileNotFound`,
        :class:`TextNotFound`, or :class:`AmbiguousEdit`.
        """
        resolved = self._resolve_and_authorize(path)
        if not resolved.exists() or not resolved.is_file():
            raise FileNotFound(str(resolved))

        # Read first; an unreadable file must not leave a half-write.
        original = resolved.read_text(encoding="utf-8")
        count = original.count(old_text)
        if count == 0:
            raise TextNotFound(f"old_text not found in {path}")
        if count > 1:
            raise AmbiguousEdit(f"old_text appears {count} times in {path}; refusing to guess")

        # Step 4 — at this point the assertion has passed; the write
        # cannot fail for a content-shape reason (only a permissions
        # failure could happen, which would also have failed on read).
        new_content = original.replace(old_text, new_text, 1)
        resolved.write_text(new_content, encoding="utf-8")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @property
    def root(self) -> Path:
        """Return the resolved sandbox root (read-only)."""
        return self._root

    def _resolve_and_authorize(self, path: str) -> Path:
        """Resolve ``path`` against :attr:`_root` and check the sandbox + globs.

        On success: returns the resolved absolute :class:`Path`.
        On failure: raises :class:`PathNotAllowed` with an informative
        message.

        ``Path.resolve()`` follows symlinks, which is exactly what makes
        the symlink-escape test pass: a symlink inside the sandbox that
        points outside resolves to the outside target, which then fails
        the ``is_relative_to`` check.
        """
        # An empty path would resolve to the root itself, which would
        # then fail ``is_file()`` on read. We reject early.
        if path == "":
            raise PathNotAllowed("path is empty")

        # Build the candidate path. ``Path`` handles both relative and
        # absolute inputs the same way here: ``(root / path).resolve()``
        # treats an absolute ``path`` as overriding ``root`` because
        # ``Path("/abs") / "rel"`` == ``Path("/abs/rel")`` but
        # ``Path("/rel") / "/abs"`` == ``Path("/abs")`` (POSIX semantics).
        # ``os.path.join``-style replacement is what we want — we want
        # the relative ``path`` to be interpreted under the root, and an
        # absolute path to be rejected outright.
        if Path(path).is_absolute():
            raise PathNotAllowed(f"absolute path is outside the sandbox: {path!r}")

        candidate = (self._root / path).resolve()

        # Sandbox check: the candidate must live under the root. ``is_relative_to``
        # was added in Python 3.9; the project pins ``>=3.11`` so it's always present.
        if candidate != self._root and not candidate.is_relative_to(self._root):
            raise PathNotAllowed(f"path {path!r} resolves outside the sandbox: {candidate}")

        # Glob check: match each glob against the path *relative to* the
        # sandbox root, so the globs are written from the user's
        # perspective ("**/*.py", not "/home/user/project/**/*.py").
        try:
            relative = candidate.relative_to(self._root)
        except ValueError as exc:  # pragma: no cover - defensive; covered by is_relative_to above
            raise PathNotAllowed(
                f"path {path!r} resolves outside the sandbox: {candidate}"
            ) from exc

        # ``relative.as_posix()`` is "" when the candidate equals the root;
        # an empty pattern matches the root in our custom matcher (matches
        # ``**/*`` too — see ``_glob_match``).
        relative_str = relative.as_posix()
        if not any(_glob_match(relative_str, glob) for glob in self._allowed_globs):
            raise PathNotAllowed(
                f"path {path!r} does not match any allowed glob {list(self._allowed_globs)}"
            )

        return candidate


def _glob_match(path_str: str, glob: str) -> bool:
    """Match ``path_str`` against ``glob``, with proper ``**`` semantics.

    Python's :func:`pathlib.PurePath.match` interprets ``**`` as "one or
    more directories" — it does NOT match the empty leading portion of a
    relative path, so ``PurePath("foo.py").match("**/*.py")`` returns
    ``False``. Users expect ``**/*.py`` to match any ``*.py`` file at any
    depth (the gitignore convention), so we implement the matcher
    ourselves.

    Algorithm: split both into components. ``**`` matches zero or more
    components; ``*`` and explicit names use :func:`fnmatch.fnmatchcase`.
    The empty path (``""``, when the candidate equals the sandbox root)
    is accepted by ``**/*`` because ``**`` consumes zero components and
    ``*`` then matches the empty trailing portion.
    """
    if path_str == "" and glob == "":
        return True
    glob_parts = glob.split("/") if glob else [""]
    path_parts = path_str.split("/") if path_str else [""]

    def match_parts(g: list[str], p: list[str]) -> bool:
        # Skip empty glob components that arise from leading ``/``.
        if g and g[0] == "":
            return match_parts(g[1:], p)
        if not g:
            return not p
        if g[0] == "**":
            # ``**`` matches zero or more components. Try matching the rest
            # of the glob against every suffix of ``p``.
            rest = g[1:]
            if match_parts(rest, p):
                return True
            return any(match_parts(rest, p[i + 1 :]) for i in range(len(p)))
        if not p:
            return False
        # Single-component glob: match the basename against the next part.
        if fnmatch.fnmatchcase(p[0], g[0]):
            return match_parts(g[1:], p[1:])
        return False

    return match_parts(glob_parts, path_parts)


__all__ = ["SandboxedFileEditor"]
