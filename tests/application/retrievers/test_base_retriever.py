"""Tests for the ``BaseRetriever`` Strategy implementation.

Pinned by ``agent-development/08-retriever-with-decorator/tests.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from simple_cli_coder_with_rag.application.retrievers.base_retriever import BaseRetriever
from simple_cli_coder_with_rag.domain.chunk import Chunk
from simple_cli_coder_with_rag.domain.embedder import EmbedderNotReady
from simple_cli_coder_with_rag.domain.retriever import RetrievedChunk

if TYPE_CHECKING:
    pass


class _FakeEmbedder:
    """Recording fake ``Embedder``: records all calls, controls is_ready."""

    def __init__(self, ready: bool = True, vector: list[float] | None = None) -> None:
        self._ready = ready
        self._vector = vector if vector is not None else [0.1, 0.2, 0.3]
        self.embed_calls: list[str] = []

    def is_ready(self) -> bool:
        return self._ready

    def embed_query(self, text: str) -> list[float]:
        self.embed_calls.append(text)
        return list(self._vector)


class _FakeVectorStore:
    """Recording fake ``VectorStore``: returns canned (chunk, similarity) rows."""

    def __init__(self, results: list[tuple[Chunk, float]] | None = None) -> None:
        self._results = results or []
        self.query_calls: list[tuple[list[float], int]] = []

    def query(self, vector: list[float], top_k: int) -> list[tuple[Chunk, float]]:
        self.query_calls.append((list(vector), top_k))
        return list(self._results)

    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        # not used in these tests, but the Protocol requires it.
        ...


def test_retrieve_embeds_then_queries() -> None:
    """``retrieve`` calls ``embed_query`` once, then ``query`` with the embedded vector."""
    chunk = Chunk(text="x", session_id="s")
    store = _FakeVectorStore(results=[(chunk, 0.9)])
    embedder = _FakeEmbedder(vector=[0.5, 0.5])
    retriever = BaseRetriever(embedder=embedder, vector_store=store)  # type: ignore[arg-type]

    retriever.retrieve("hi", top_k=3)

    assert embedder.embed_calls == ["hi"]
    assert len(store.query_calls) == 1
    vector, top_k = store.query_calls[0]
    assert vector == [0.5, 0.5]
    assert top_k == 3


def test_retrieve_returns_retrieved_chunks_sorted() -> None:
    """VectorStore results become ``RetrievedChunk`` preserving order."""
    c1 = Chunk(text="a", session_id="s")
    c2 = Chunk(text="b", session_id="s")
    store = _FakeVectorStore(results=[(c1, 0.9), (c2, 0.5)])
    embedder = _FakeEmbedder()
    retriever = BaseRetriever(embedder=embedder, vector_store=store)  # type: ignore[arg-type]

    results = retriever.retrieve("q", top_k=3)

    assert results == [RetrievedChunk(c1, 0.9), RetrievedChunk(c2, 0.5)]


def test_retrieve_respects_top_k() -> None:
    """``top_k`` is forwarded to ``vector_store.query``."""
    chunks = [(Chunk(text=f"c{i}", session_id="s"), 1.0 - i * 0.1) for i in range(5)]
    store = _FakeVectorStore(results=chunks)
    embedder = _FakeEmbedder()
    retriever = BaseRetriever(embedder=embedder, vector_store=store)  # type: ignore[arg-type]

    results = retriever.retrieve("q", top_k=2)

    assert len(results) == 2
    assert store.query_calls[0][1] == 2


def test_retrieve_raises_when_embedder_not_ready() -> None:
    """When the embedder is still loading, ``retrieve`` raises ``EmbedderNotReady``."""
    store = _FakeVectorStore()
    embedder = _FakeEmbedder(ready=False)
    retriever = BaseRetriever(embedder=embedder, vector_store=store)  # type: ignore[arg-type]

    with pytest.raises(EmbedderNotReady):
        retriever.retrieve("q", top_k=3)


def test_retrieve_passes_through_when_ready() -> None:
    """When the embedder is ready, ``retrieve`` returns the chunks."""
    chunk = Chunk(text="x", session_id="s")
    store = _FakeVectorStore(results=[(chunk, 0.7)])
    embedder = _FakeEmbedder(ready=True)
    retriever = BaseRetriever(embedder=embedder, vector_store=store)  # type: ignore[arg-type]

    results = retriever.retrieve("q", top_k=3)

    assert results == [RetrievedChunk(chunk, 0.7)]
