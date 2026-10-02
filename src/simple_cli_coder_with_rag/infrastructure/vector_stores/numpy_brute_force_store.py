"""``NumpyBruteForceStore`` — in-memory cosine-similarity fallback for ``VectorStore``.

Activated when the host Python's SQLite build cannot load
``sqlite-vec`` (``SQLITE_OMIT_LOAD_EXTENSION``) or when the user opts
in via ``VECTOR_STORE=brute_force``. The store holds a list of
``(vector, chunk)`` tuples and computes cosine similarity in pure
Python+``numpy``.

Design notes:

* ``upsert`` is **delete-then-insert by ``session_id``** to mirror
  :class:`~simple_cli_coder_with_rag.infrastructure.vector_stores.sqlite_vec_store.SqliteVecStore`:
  two ``/learn`` calls on the same session must not duplicate rows
  (cosine distances would otherwise inflate by tying for top-1).
* ``query`` skips zero-norm rows so a malformed chunk never produces a
  ``NaN`` similarity. A zero-norm query vector is also a no-op —
  every similarity would be undefined, so we return ``[]``.
* ``numpy`` is imported **inside the methods** rather than at module
  scope so the cold-start path of the default ``SqliteVecStore``
  install never drags ``numpy`` through the import graph. The
  ``fastembed`` package depends on ``numpy`` already, so this is a
  micro-optimisation — clarity wins.
"""

from __future__ import annotations

from typing import Any

from simple_cli_coder_with_rag.domain.chunk import Chunk


class NumpyBruteForceStore:
    """In-memory ``VectorStore`` backed by ``numpy`` cosine similarity.

    State is per-instance: two stores on the same machine do not share
    data. This is acceptable for v1 because the fallback is a
    per-process safety net — the user has explicitly opted out of
    persistent storage by triggering the fallback.
    """

    def __init__(self) -> None:
        # Stored as ``list[tuple[list[float], Chunk]]`` so each entry is
        # independently mutating without churning the list's backing
        # array. ``numpy`` is only touched inside ``query``.
        self._items: list[tuple[list[float], Chunk]] = []

    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Delete-then-insert ``chunks`` by ``session_id`` (idempotent).

        Mirrors :meth:`SqliteVecStore.upsert` so ``/learn`` is idempotent
        regardless of which Strategy implementation the composition
        root picked.
        """
        if not chunks:
            return
        if len(chunks) != len(vectors):
            raise ValueError(
                f"chunks and vectors length mismatch: {len(chunks)} chunks vs "
                f"{len(vectors)} vectors"
            )

        session_ids = {chunk.session_id for chunk in chunks}
        self._items = [
            (vec, chunk) for vec, chunk in self._items if chunk.session_id not in session_ids
        ]
        for chunk, vector in zip(chunks, vectors, strict=True):
            self._items.append((list(vector), chunk))

    def query(self, vector: list[float], top_k: int) -> list[tuple[Chunk, float]]:
        """Return up to ``top_k`` chunks sorted by cosine similarity descending.

        Zero-norm rows (stored vectors whose magnitude is ``0``) are
        skipped so the cosine denominator never becomes zero. A
        zero-norm query vector is a no-op and returns ``[]``.
        """
        import numpy as np  # local import keeps cold-start slim

        if not self._items:
            return []

        if top_k <= 0:
            return []

        query = np.asarray(vector, dtype=np.float32)
        query_norm = float(np.linalg.norm(query))
        if query_norm == 0.0:
            return []

        vectors_matrix = np.asarray([vec for vec, _chunk in self._items], dtype=np.float32)
        stored_norms = np.linalg.norm(vectors_matrix, axis=1)

        # Cosine similarity is ``dot(a, b) / (||a|| * ||b||)``. The
        # denominator is zero for any zero-norm stored vector — those
        # rows are masked to ``0.0`` similarity and then dropped from
        # the returned list.
        valid = stored_norms > 0.0
        if not np.any(valid):
            return []

        dots = vectors_matrix @ query
        denom = stored_norms * query_norm
        # Where ``denom == 0`` the similarity is undefined; mask to 0
        # so the later sort picks whatever real rows remain. We also
        # exclude those rows from the final list (see below).
        with np.errstate(invalid="ignore", divide="ignore"):
            similarities = np.where(denom > 0.0, dots / denom, 0.0)

        # Drop zero-norm rows entirely — the masked ``0.0`` similarity
        # above would otherwise tie for last place.
        keep_mask = valid & np.isfinite(similarities)
        kept_indices = np.flatnonzero(keep_mask)

        # Sort descending by similarity, take top_k.
        order = kept_indices[np.argsort(-similarities[kept_indices])]
        chosen = order[: int(top_k)]

        results: list[tuple[Chunk, float]] = []
        for idx in chosen:
            # ``idx`` is a 0-D numpy int; cast to plain int for dict /
            # JSON-friendliness.
            chunk = self._items[int(idx)][1]
            sim: Any = float(similarities[int(idx)])
            results.append((chunk, sim))
        return results


__all__ = ["NumpyBruteForceStore"]
