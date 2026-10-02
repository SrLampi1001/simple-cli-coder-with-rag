"""Append-only session storage and overwrite-on-write compacted JSON.

Responsibilities:

* Write chat messages to ``<root>/<session_id>.jsonl`` — one JSON line per
  message, in append order. The file is the on-disk transcript of a single
  REPL session; nothing in this module truncates it.
* Write the structured result of ``/learn`` to
  ``<root>/<session_id>.compacted.json`` — a single JSON document that is
  replaced on every compaction (idempotent ``/learn``).
* List every saved ``<id>.jsonl`` transcript in the store by
  ``(session_id, mtime, message_count)`` (DO-12). The listing is
  metadata-only — message bodies are never parsed.

Architectural constraint: this module imports from :mod:`domain` only.
It must not import anything from :mod:`infrastructure` (no ``LocalPaths``,
no ``platformdirs``, no vendor SDKs). The composition root in
``cli.py`` is the only place that resolves a concrete root path and wires
``SessionStore(LocalPaths.data_dir() / "sessions")``. This keeps the
storage layer cheap to test (``tmp_path`` is enough) and prevents the
platform-dependent data directory from leaking into the application layer.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from loguru import logger

from simple_cli_coder_with_rag.domain.compacted import CompactedSession
from simple_cli_coder_with_rag.domain.messages import Message


class SessionStore:
    """On-disk store for session transcripts and their compacted summaries.

    The store never holds the session list in memory — every operation goes
    straight to disk so a crash mid-session leaves a readable transcript.
    """

    def __init__(self, root: Path) -> None:
        """Create ``root`` (and any missing parents) and remember it."""
        root.mkdir(parents=True, exist_ok=True)
        self._root = root

    def current_id(self) -> str:
        """Return a fresh UUIDv4 hex string for a new session."""
        return uuid.uuid4().hex

    def path(self, session_id: str) -> Path:
        """Return the ``.jsonl`` transcript path for ``session_id``."""
        return self._root / f"{session_id}.jsonl"

    def append(self, session_id: str, message: Message) -> None:
        """Append ``message`` as one JSON line to the session's transcript.

        Each call writes exactly one line terminated by ``\\n``. Concatenated
        over a session, the file is a valid ``.jsonl`` document parsable
        line-by-line.
        """
        with self.path(session_id).open("a", encoding="utf-8") as f:
            f.write(message.model_dump_json() + "\n")

    def read(self, session_id: str) -> list[Message]:
        """Return every message previously appended to ``session_id``.

        Returns ``[]`` when the transcript does not exist (e.g. brand-new
        session or already deleted). Empty lines are skipped defensively
        so a stray trailing newline at the end of the file does not break
        the load.
        """
        path = self.path(session_id)
        if not path.exists():
            return []
        return [
            Message.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line
        ]

    def delete(self, session_id: str) -> None:
        """Remove the transcript for ``session_id`` if it exists.

        Idempotent: calling ``delete`` on a missing id is a no-op.
        """
        self.path(session_id).unlink(missing_ok=True)

    def write_compacted(self, session_id: str, compacted: CompactedSession) -> Path:
        """Persist ``compacted`` as ``<session_id>.compacted.json`` and return the path.

        Overwrites any existing file — ``/learn`` is idempotent. Returns the
        :class:`Path` so the caller (or the chunker in DO-05) can read the
        document back without recomputing the location.
        """
        target = self._root / f"{session_id}.compacted.json"
        target.write_text(compacted.model_dump_json(indent=2), encoding="utf-8")
        return target

    def list_sessions(self) -> list[tuple[str, float, int]]:
        """Return one ``(session_id, mtime, message_count)`` tuple per saved session.

        DO-12 backs ``/chats`` with this listing. One tuple per
        ``<id>.jsonl`` file under ``self._root``, sorted by ``mtime``
        descending. ``message_count`` is the number of non-empty lines
        in the file — a trailing newline does not count. The listing
        is **metadata-only**: message bodies are never parsed, which
        keeps the cost bounded even on long-running ones. The
        implementation is resilient to a missing root (returns ``[]``)
        and to unreadable files (logged at DEBUG, entry omitted).

        Returns:
            ``[(session_id, mtime, message_count), ...]`` sorted by
            ``mtime`` descending. Empty root → ``[]``.
        """
        if not self._root.exists():
            return []
        entries: list[tuple[str, float, int]] = []
        try:
            iterator = os.scandir(self._root)
        except OSError as exc:
            logger.debug("session store: cannot scan {}: {}", self._root, exc)
            return []
        for dir_entry in iterator:
            name = dir_entry.name
            if not name.endswith(".jsonl"):
                # ``.compacted.json`` and other sibling artefacts are ignored.
                pass
            if not dir_entry.is_file() or not name.endswith(".jsonl"):
                continue
            session_id = name[: -len(".jsonl")]
            try:
                stat = dir_entry.stat()
            except OSError as exc:
                logger.debug("session store: cannot stat {}: {}", dir_entry.path, exc)
                continue
            mtime = stat.st_mtime
            try:
                with open(dir_entry.path, encoding="utf-8") as f:
                    message_count = sum(1 for line in f if line.strip())
            except OSError as exc:
                logger.debug("session store: cannot read {}: {}", dir_entry.path, exc)
                continue
            entries.append((session_id, mtime, message_count))
        # Sort by mtime descending — most recently active session first.
        entries.sort(key=lambda entry: entry[1], reverse=True)
        return entries


__all__ = ["SessionStore"]
