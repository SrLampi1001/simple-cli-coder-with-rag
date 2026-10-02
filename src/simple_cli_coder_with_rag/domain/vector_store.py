"""Strategy interface for the vector store.

The vector store is the **fourth Strategy seam** in the RAG pipeline
(``OBJECTIVES.md`` — "the vector store (Chroma, FAISS, SQLite-vec)").
Two implementations live in
:mod:`simple_cli_coder_with_rag.infrastructure.vector_stores`:

* ``SqliteVecStore`` — default. Uses ``sqlite-vec``'s ``vec0`` virtual
  table with ``distance_metric=cosine``. Persists across runs.
* ``NumpyBruteForceStore`` — fallback. In-memory list of
  ``(vector, chunk)`` tuples; cosine similarity in pure Python+``numpy``.
  Activated when ``sqlite-vec`` cannot load (build lacks
  ``SQLITE_OMIT_LOAD_EXTENSION``) or when
  ``Settings.vector_store == "brute_force"``.

Adding a third implementation (e.g. an in-memory HNSW index) is a matter
of writing the class and registering it in the composition root in
``cli.py``. The interface below is the seam.

``VectorStoreBackendUnavailable`` is raised by
:class:`~simple_cli_coder_with_rag.infrastructure.vector_stores.sqlite_vec_store.SqliteVecStore`
when the host Python's ``sqlite3`` build cannot load extensions. It is a
:class:`RuntimeError` so the composition root can catch it and fall
back to ``NumpyBruteForceStore`` without importing this domain module.

Architectural note: this module imports from :mod:`domain` only. It
does not import from :mod:`infrastructure` or from vendor SDKs. The
two ``import-linter`` contracts (``layered-architecture`` and
``forbidden_imports`` for ``sqlite_vec``) keep it that way.
"""

from __future__ import annotations

from typing import Protocol

from simple_cli_coder_with_rag.domain.chunk import Chunk


class VectorStore(Protocol):
    """Strategy interface for persisting chunks and querying by similarity."""

    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Persist ``chunks`` together with their pre-computed ``vectors``.

        Implementations MUST be **idempotent by ``session_id``** —
        re-upserting chunks from the same session replaces the previous
        rows. Otherwise cosine rankings inflate on repeated ``/learn``
        calls (two copies of the same chunk tie for top-1).

        The two lists MUST have the same length; the contract is that
        ``vectors[i]`` is the embedding of ``chunks[i].text`` produced
        by :class:`~simple_cli_coder_with_rag.domain.embedder.Embedder`.
        """
        ...

    def query(self, vector: list[float], top_k: int) -> list[tuple[Chunk, float]]:
        """Return up to ``top_k`` chunks sorted by cosine similarity descending.

        The score is **cosine similarity** (``-1`` to ``1``, larger is
        better), not the underlying distance. ``SqliteVecStore`` with
        ``distance_metric=cosine`` returns ``distance = 1 - similarity``,
        so it computes ``similarity = 1 - row[0]`` internally.

        Returns ``[]`` when the store has no chunks.
        """
        ...


class VectorStoreBackendUnavailable(RuntimeError):  # noqa: N818 -- name pinned by the DO-07 contracts
    """Raised when the configured vector store backend cannot be initialised.

    A ``RuntimeError`` subclass — not a generic ``Exception`` — so the
    composition root in :mod:`simple_cli_coder_with_rag.cli` can catch
    it and fall back to
    :class:`~simple_cli_coder_with_rag.infrastructure.vector_stores.numpy_brute_force_store.NumpyBruteForceStore`
    without importing this domain module. The message carries the
    ``VECTOR_STORE=brute_force`` workaround hint so the user can
    recover with a one-line change to ``.env``.
    """


__all__ = ["VectorStore", "VectorStoreBackendUnavailable"]
