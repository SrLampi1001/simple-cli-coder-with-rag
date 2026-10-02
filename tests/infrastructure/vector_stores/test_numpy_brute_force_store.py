"""Tests for the ``NumpyBruteForceStore`` fallback implementation.

Pinned by ``agent-development/07-vector-store-strategy/tests.md``.

The numpy store is the **fallback** — activated when
``SqliteVecStore.__init__`` raises ``VectorStoreBackendUnavailable`` or
when ``Settings.vector_store == "brute_force"``. It is an in-memory
list of ``(vector, chunk)`` tuples; ``query`` does cosine similarity in
pure Python+``numpy``.
"""

from __future__ import annotations

import math

import pytest

from simple_cli_coder_with_rag.domain.chunk import Chunk
from simple_cli_coder_with_rag.infrastructure.vector_stores.numpy_brute_force_store import (
    NumpyBruteForceStore,
)


def _chunk(text: str, session_id: str = "s", **metadata: object) -> Chunk:
    """Build a ``Chunk`` for tests."""
    return Chunk(text=text, session_id=session_id, metadata=metadata)


def test_upsert_then_query_returns_chunks() -> None:
    """After upserting 3 chunks, the second chunk is returned with similarity 1.0."""
    store = NumpyBruteForceStore()
    chunks = [
        _chunk("A"),
        _chunk("B"),
        _chunk("C"),
    ]
    vectors = [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]

    store.upsert(chunks, vectors)

    results = store.query([0.0, 1.0, 0.0], top_k=3)

    # The hit with similarity 1.0 is the second chunk.
    by_sim = sorted(results, key=lambda r: -r[1])
    assert by_sim[0][0].text == "B"
    assert by_sim[0][1] == pytest.approx(1.0)


def test_query_cosine_similarity_known_vectors() -> None:
    """Two orthogonal 2-D vectors queried with ``[1, 1]`` each have similarity ``1/sqrt(2)``."""
    store = NumpyBruteForceStore()
    store.upsert(
        [_chunk("A"), _chunk("B")],
        [[1.0, 0.0], [0.0, 1.0]],
    )

    results = store.query([1.0, 1.0], top_k=2)

    assert len(results) == 2
    expected = 1.0 / math.sqrt(2.0)
    for _item, similarity in results:
        assert similarity == pytest.approx(expected, abs=1e-3)


def test_query_respects_top_k() -> None:
    """``query`` returns at most ``top_k`` chunks."""
    store = NumpyBruteForceStore()
    chunks = [_chunk(f"c{i}") for i in range(5)]
    vectors = [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.5, 0.5, 0.0],
        [0.5, 0.0, 0.5],
    ]

    store.upsert(chunks, vectors)

    assert len(store.query([1.0, 0.0, 0.0], top_k=2)) == 2
    assert len(store.query([1.0, 0.0, 0.0], top_k=5)) == 5
    assert len(store.query([1.0, 0.0, 0.0], top_k=10)) == 5  # capped at store size


def test_query_empty_store_returns_empty() -> None:
    """``query`` on a fresh store returns ``[]`` without raising."""
    store = NumpyBruteForceStore()

    assert store.query([1.0, 0.0], top_k=3) == []


def test_upsert_is_idempotent_by_session() -> None:
    """Two ``upsert`` calls for the same ``session_id`` leave exactly one stored copy.

    Mirrors ``SqliteVecStore``'s delete-then-insert contract; the cosine
    ranking would otherwise inflate if duplicates were kept (two copies
    of the same chunk would tie for top-1).
    """
    store = NumpyBruteForceStore()
    store.upsert(
        [_chunk("first", session_id="shared")],
        [[1.0, 0.0, 0.0]],
    )
    store.upsert(
        [_chunk("second", session_id="shared")],
        [[0.0, 1.0, 0.0]],
    )

    # Total stored items = 1 (the second upsert replaced the first).
    assert len(store._items) == 1, (
        f"idempotent upsert must leave one item per session_id, got {len(store._items)}"
    )

    results = store.query([1.0, 0.0, 0.0], top_k=3)
    # The remaining chunk is "second"; its similarity to ``[1, 0, 0]`` is 0.0.
    assert len(results) == 1
    assert results[0][0].text == "second"


def test_upsert_keeps_other_sessions() -> None:
    """Re-upserting one ``session_id`` must not evict rows from another ``session_id``."""
    store = NumpyBruteForceStore()
    store.upsert(
        [_chunk("a-1", session_id="alpha"), _chunk("b-1", session_id="beta")],
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
    )

    # Re-upsert only ``alpha``.
    store.upsert(
        [_chunk("a-2", session_id="alpha")],
        [[0.0, 0.0, 1.0]],
    )

    # Two items remain: ``alpha → a-2`` and ``beta → b-1``.
    assert len(store._items) == 2

    results = store.query([0.0, 0.0, 1.0], top_k=3)
    assert len(results) == 2
    assert results[0][0].text == "a-2"
    assert results[1][0].text == "b-1"


def test_query_skips_zero_norm_rows() -> None:
    """A chunk with the zero vector is excluded from results (no ``NaN`` similarity)."""
    store = NumpyBruteForceStore()
    store.upsert(
        [_chunk("non-zero"), _chunk("zero-norm")],
        [[1.0, 0.0], [0.0, 0.0]],
    )

    results = store.query([1.0, 0.0], top_k=3)

    texts = [chunk.text for chunk, _sim in results]
    assert "zero-norm" not in texts, f"zero-norm chunk must be excluded, got {texts}"
    assert "non-zero" in texts
    # No NaN similarities leaked through.
    for _item, similarity in results:
        assert not math.isnan(similarity), f"NaN similarity leaked: {similarity!r}"
        assert -1.0 <= similarity <= 1.0


def test_query_similarity_in_minus_one_one() -> None:
    """Every similarity returned is in ``[-1.0, 1.0]`` (mathematical bound)."""
    store = NumpyBruteForceStore()
    store.upsert(
        [
            _chunk("anti"),
            _chunk("aligned"),
            _chunk("ortho"),
        ],
        [
            [-1.0, 0.0],  # anti-parallel to query
            [1.0, 0.0],  # parallel to query
            [0.0, 1.0],  # orthogonal to query
        ],
    )

    results = store.query([1.0, 0.0], top_k=3)

    for _item, similarity in results:
        assert -1.0 <= similarity <= 1.0, f"similarity {similarity} out of [-1, 1] range"


def test_query_handles_zero_query_norm() -> None:
    """A zero-norm query returns ``[]`` (no division by zero)."""
    store = NumpyBruteForceStore()
    store.upsert([_chunk("x")], [[1.0, 0.0]])

    results = store.query([0.0, 0.0], top_k=3)

    assert results == []


def test_query_sorts_by_similarity_descending() -> None:
    """``query`` returns chunks sorted by cosine similarity descending."""
    store = NumpyBruteForceStore()
    store.upsert(
        [
            _chunk("low"),
            _chunk("high"),
            _chunk("mid"),
        ],
        [
            [0.0, 1.0],  # similarity 0.0 to query
            [1.0, 0.0],  # similarity 1.0 to query
            [0.5, 0.5],  # similarity ~0.707
        ],
    )

    results = store.query([1.0, 0.0], top_k=3)

    sims = [sim for _, sim in results]
    assert sims == sorted(sims, reverse=True), f"not sorted descending: {sims}"
    assert results[0][0].text == "high"
    assert results[-1][0].text == "low"


def test_chunks_round_trip_unchanged() -> None:
    """``upsert`` returns the same ``Chunk`` objects (by identity) via ``query``."""
    store = NumpyBruteForceStore()
    original = _chunk("hello", session_id="s")
    store.upsert([original], [[1.0, 0.0]])

    results = store.query([1.0, 0.0], top_k=1)

    assert results[0][0] is original, (
        "query should return the same Chunk instance that was upserted"
    )
