"""``SqliteVecStore`` — persistent vector store using the ``sqlite-vec`` extension.

This module is the **only** place in the codebase that imports
``sqlite_vec``. The ``import-linter`` ``forbidden_imports`` contract in
``pyproject.toml`` enforces this; the
``tests/infrastructure/vector_stores/test_sqlite_vec_store.py`` test
suite is a redundant safeguard.

Design notes (``docs/development-tools.md`` §4):

* Default schema: ``vec0`` virtual table with ``float[384]`` (the BGE
  dimensionality), ``distance_metric=cosine``, ``+text`` auxiliary
  column, and ``session_id`` / ``created_at`` metadata columns.
* Startup time runs the ``enable_load_extension`` check documented in
  dev-tools.md §4 — if the host Python's SQLite build lacks
  ``SQLITE_OMIT_LOAD_EXTENSION`` we raise
  :class:`~simple_cli_coder_with_rag.domain.vector_store.VectorStoreBackendUnavailable`
  so the composition root can fall back to ``NumpyBruteForceStore``.
* ``upsert`` is **delete-then-insert by ``session_id``** for idempotency
  — repeated ``/learn`` on the same session must not duplicate rows.
* ``query`` opens a fresh connection inside the worker. The "open
  inside the worker" guidance (dev-tools.md §4 thread-safety note) lets
  the retriever run on a different thread without the
  ``check_same_thread=False`` ceremony.
* The ``distance`` column from ``MATCH`` queries is converted to
  cosine similarity (``1 - distance``) and clamped to ``[-1, 1]`` to
  defend against floating-point error on near-aligned vectors.
"""

from __future__ import annotations

import contextlib
import sqlite3
import struct
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from simple_cli_coder_with_rag.domain.chunk import Chunk
from simple_cli_coder_with_rag.domain.vector_store import (
    VectorStoreBackendUnavailable,
)

# ``sqlite_vec`` is the Python helper package that registers ``vec0``.
# It is only imported lazily inside ``__init__`` after the startup
# check passes. The import statement below is the **only** place the
# symbol appears in the package — ``import-linter`` enforces this with
# a ``forbidden_imports`` contract.
with contextlib.suppress(ImportError):  # pragma: no cover
    import sqlite_vec  # noqa: F401  -- presence signals "vec0 is loadable"


# Embedding dimensionality. Pinned by dev-tools.md §4 and by the BGE
# model ``bge-small-en-v1.5`` default. Changing this requires a
# migration.
_EMBEDDING_DIM: Final = 384

# Schema statement. Verbatim from ``docs/development-tools.md`` §4 —
# do not edit in isolation; the test
# ``test_init_creates_schema_with_cosine_aux_and_metadata`` pins the
# columns and their ``+`` prefix.
_SCHEMA_DDL: Final = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING vec0(\n"
    "    embedding float[384] distance_metric=cosine,\n"
    "    +text      TEXT,\n"
    "    session_id TEXT,\n"
    "    created_at INTEGER\n"
    ")"
)

# Startup-check failure message. Mentions the ``VECTOR_STORE=brute_force``
# workaround so the user has a one-line path to recovery.
_STARTUP_FAILURE_MSG: Final = (
    "This Python build does not support sqlite3 extension loading, "
    "so sqlite-vec cannot be used. Install CPython from python.org "
    "or a build with --enable-loadable-sqlite-extensions. "
    "Alternatively, set VECTOR_STORE=brute_force to use the numpy fallback."
)

# Exceptions that mean "this Python build cannot load sqlite-vec" —
# we catch them in one place and re-raise as the documented exception
# so the composition root's fallback path activates uniformly.
#
# ``AttributeError`` covers the case where the C-level method is not
# registered at all (typical ``SQLITE_OMIT_LOAD_EXTENSION`` build).
# ``TypeError`` covers the case where the method descriptor is present
# but resolves to ``None`` and cannot be called.
# ``NotSupportedError`` / ``OperationalError`` cover the cases where
# the method exists but the runtime refuses the call.
_LOAD_EXT_EXC: Final = (
    AttributeError,
    TypeError,
    sqlite3.NotSupportedError,
    sqlite3.OperationalError,
)


def _vector_to_bytes(vector: list[float]) -> bytes:
    """Pack ``vector`` as little-endian float32 bytes for ``vec0`` storage.

    ``sqlite-vec`` accepts vectors either as a JSON string or as packed
    float32 bytes. We use the bytes form so the Python→SQLite boundary
    has no parsing overhead and so the round-trip preserves the exact
    bit pattern (no JSON rounding).
    """
    return struct.pack(f"<{len(vector)}f", *vector)


def _now_epoch() -> int:
    """Return the current UTC time as an ``int`` epoch seconds.

    Stored as ``INTEGER`` so the column filters with a plain ``WHERE`` /
    ``ORDER BY`` and so JSON serialisation is trivial.
    """
    return int(datetime.now(tz=UTC).timestamp())


class SqliteVecStore:
    """Persistent ``sqlite-vec``-backed implementation of ``VectorStore``.

    Construction runs the startup check (loads the extension, creates
    the virtual table). On success the store is ready to use; on
    failure a :class:`VectorStoreBackendUnavailable` is raised and the
    composition root falls back to ``NumpyBruteForceStore``.

    ``upsert`` and ``query`` each open a fresh ``sqlite3.Connection``
    rather than caching one on the instance — that follows the
    thread-safety guidance in ``docs/development-tools.md`` §4 (open
    inside the worker) and keeps the store reentrant across threads.
    """

    def __init__(self, db_path: Path) -> None:
        """Open the DB, load ``vec0``, create the schema. Raise on failure.

        Parent directories of ``db_path`` are created if missing — a
        first-run install on a clean machine has no
        ``~/.local/share/...`` directory yet.
        """
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path

        try:
            raw_conn = sqlite3.connect(str(db_path))
        except (sqlite3.Error, OSError) as exc:
            raise VectorStoreBackendUnavailable(_STARTUP_FAILURE_MSG) from exc

        try:
            try:
                raw_conn.enable_load_extension(True)
            except _LOAD_EXT_EXC as exc:
                # ``AttributeError`` covers the case where the build set
                # ``enable_load_extension`` to ``None`` (SQLITE_OMIT_LOAD_EXTENSION).
                raise VectorStoreBackendUnavailable(_STARTUP_FAILURE_MSG) from exc

            try:
                raw_conn.load_extension("vec0")
            except _LOAD_EXT_EXC as exc:
                raise VectorStoreBackendUnavailable(_STARTUP_FAILURE_MSG) from exc

            raw_conn.execute(_SCHEMA_DDL)
            raw_conn.commit()
        finally:
            raw_conn.close()

    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Delete-then-insert ``chunks`` by ``session_id`` (idempotent).

        The unique ``session_id`` set in the incoming batch is deleted
        first; then the new rows are inserted. Two calls for the same
        ``session_id`` leave exactly one set of rows.

        Opens a fresh ``sqlite3.Connection`` so this method is safe to
        call from a worker thread (per dev-tools.md §4 thread-safety
        guidance).
        """
        if not chunks:
            return
        if len(chunks) != len(vectors):
            raise ValueError(
                f"chunks and vectors length mismatch: {len(chunks)} chunks vs "
                f"{len(vectors)} vectors"
            )

        session_ids = sorted({chunk.session_id for chunk in chunks})
        created_at = _now_epoch()
        rows = [
            (
                _vector_to_bytes(vector),
                chunk.text,
                chunk.session_id,
                created_at,
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]

        conn = sqlite3.connect(str(self._db_path))
        try:
            with conn:
                # Delete previous rows for the affected session ids. The
                # IN-list is built with placeholders so SQL injection
                # is impossible regardless of session id format.
                placeholders = ",".join("?" for _ in session_ids)
                conn.execute(
                    f"DELETE FROM chunks WHERE session_id IN ({placeholders})",
                    tuple(session_ids),
                )
                conn.executemany(
                    "INSERT INTO chunks(embedding, text, session_id, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    rows,
                )
        finally:
            conn.close()

    def query(self, vector: list[float], top_k: int) -> list[tuple[Chunk, float]]:
        """Return up to ``top_k`` chunks sorted by cosine similarity descending.

        Opens a fresh ``sqlite3.Connection`` so this method is safe to
        call from a worker thread. ``sqlite-vec`` with
        ``distance_metric=cosine`` returns ``distance = 1 - cosine_similarity``;
        we compute ``similarity = 1 - row[0]`` and clamp to ``[-1, 1]``
        to defend against floating-point error on near-aligned vectors.
        """
        conn = sqlite3.connect(str(self._db_path))
        try:
            rows = conn.execute(
                "SELECT distance, text, session_id, created_at FROM chunks "
                "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                (_vector_to_bytes(vector), int(top_k)),
            ).fetchall()
        finally:
            conn.close()

        results: list[tuple[Chunk, float]] = []
        for row in rows:
            distance, text, session_id, created_at = row
            similarity = 1.0 - float(distance)
            if similarity > 1.0:
                similarity = 1.0
            elif similarity < -1.0:
                similarity = -1.0
            results.append(
                (
                    Chunk(
                        text=text,
                        session_id=str(session_id),
                        metadata={"created_at": int(created_at)},
                    ),
                    similarity,
                )
            )
        return results


__all__ = ["SqliteVecStore"]
