"""Tests for ``RecallCoordinator`` (DO-09).

Pinned by ``agent-development/09-recall-integration/tests.md``.

``RecallCoordinator`` is the application-layer seam between the REPL
and the (already-``TimeoutRetriever``-wrapped) ``Retriever``. It
applies the :class:`TrivialGate` short-circuit and the similarity
threshold, and degrades to ``[]`` on any failure path the contract
defines.

The latency test at the bottom is the **UX gate**: it pins end-to-end
recall at < 100 ms with the production wiring path (fake components
inside a real ``TimeoutRetriever`` + ``RetrievalExecutor``). A failure
there means DO-09 has regressed vs. the OBJECTIVES latency tip and the
LLM-call overlap sketch in ``workflow.md`` step 10 must be implemented.
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from simple_cli_coder_with_rag.application.recall_coordinator import (
    RecallCoordinator,
)
from simple_cli_coder_with_rag.application.trivial_gate import TrivialGate
from simple_cli_coder_with_rag.domain.chunk import Chunk
from simple_cli_coder_with_rag.domain.embedder import EmbedderNotReady
from simple_cli_coder_with_rag.domain.retriever import RetrievedChunk, Retriever
from simple_cli_coder_with_rag.infrastructure.retrievers.executor import (
    RetrievalExecutor,
)
from simple_cli_coder_with_rag.infrastructure.retrievers.timeout_retriever import (
    TimeoutRetriever,
)

if TYPE_CHECKING:
    pass


class _RecorderRetriever:
    """Fake ``Retriever`` that records every call and returns canned results."""

    def __init__(
        self,
        results: list[RetrievedChunk] | None = None,
        raise_exc: Exception | None = None,
        delay_seconds: float = 0.0,
    ) -> None:
        self._results = results or []
        self._raise = raise_exc
        self._delay = delay_seconds
        self.calls: list[tuple[str, int]] = []
        self._started = threading.Event()

    def retrieve(self, query: str, *, top_k: int) -> list[RetrievedChunk]:
        self.calls.append((query, top_k))
        if self._delay > 0:
            self._started.set()
            time.sleep(self._delay)
        if self._raise is not None:
            raise self._raise
        return list(self._results)


def test_trivial_prompt_skips_retriever() -> None:
    """``is_trivial`` short-circuits before the retriever is touched."""
    retriever = _RecorderRetriever()
    gate = TrivialGate()
    coordinator = RecallCoordinator(
        retriever=retriever,  # type: ignore[arg-type]
        gate=gate,
        top_k=3,
        similarity_threshold=0.5,
    )

    result = coordinator.recall("hi")

    assert result == []
    assert retriever.calls == []  # retriever never called


def test_long_prompt_calls_retriever_with_top_k() -> None:
    """Non-trivial prompt forwards ``top_k`` to the retriever."""
    chunk = Chunk(text="memory", session_id="s")
    retriever = _RecorderRetriever(results=[RetrievedChunk(chunk, 0.9)])
    gate = TrivialGate()
    coordinator = RecallCoordinator(
        retriever=retriever,  # type: ignore[arg-type]
        gate=gate,
        top_k=3,
        similarity_threshold=0.5,
    )

    # 32 chars / 8 words — comfortably above the trivial-gate boundaries.
    result = coordinator.recall("why does this fail for foo and bar too")

    assert retriever.calls == [("why does this fail for foo and bar too", 3)]
    assert result == [("", 0, "memory")]


def test_similarity_threshold_filters_chunks() -> None:
    """Chunks below ``similarity_threshold`` are dropped."""
    c1 = Chunk(text="strong", session_id="s")
    c2 = Chunk(text="weak", session_id="s")
    retriever = _RecorderRetriever(results=[RetrievedChunk(c1, 0.9), RetrievedChunk(c2, 0.3)])
    gate = TrivialGate()
    coordinator = RecallCoordinator(
        retriever=retriever,  # type: ignore[arg-type]
        gate=gate,
        top_k=3,
        similarity_threshold=0.5,
    )

    result = coordinator.recall("a sufficiently long prompt to skip the gate")

    assert result == [("", 0, "strong")]


def test_recall_passes_source_and_chunk_index() -> None:
    """The (source, chunk_index, text) tuple carries the chunk's source metadata.

    DO-13: document chunks carry a non-empty ``source`` (the file
    path) and a per-source ``chunk_index``. The coordinator passes
    them through verbatim.
    """
    c1 = Chunk(text="alpha", session_id="", source="docs/foo.md", chunk_index=0)
    c2 = Chunk(text="beta", session_id="", source="docs/foo.md", chunk_index=1)
    retriever = _RecorderRetriever(results=[RetrievedChunk(c1, 0.9), RetrievedChunk(c2, 0.8)])
    gate = TrivialGate()
    coordinator = RecallCoordinator(
        retriever=retriever,  # type: ignore[arg-type]
        gate=gate,
        top_k=3,
        similarity_threshold=0.5,
    )

    result = coordinator.recall("a sufficiently long prompt to skip the gate")

    assert result == [
        ("docs/foo.md", 0, "alpha"),
        ("docs/foo.md", 1, "beta"),
    ]


def test_embedder_not_ready_returns_empty() -> None:
    """``EmbedderNotReady`` (a RuntimeError) → ``[]`` and no exception propagates."""
    retriever = _RecorderRetriever(raise_exc=EmbedderNotReady("still loading"))
    gate = TrivialGate()
    coordinator = RecallCoordinator(
        retriever=retriever,  # type: ignore[arg-type]
        gate=gate,
        top_k=3,
        similarity_threshold=0.5,
    )

    result = coordinator.recall("a long enough prompt to bypass the gate")

    assert result == []


def test_runtime_error_returns_empty() -> None:
    """Generic ``RuntimeError`` from the retriever → ``[]`` (no coupling to embedder)."""
    retriever = _RecorderRetriever(raise_exc=RuntimeError("vector store down"))
    gate = TrivialGate()
    coordinator = RecallCoordinator(
        retriever=retriever,  # type: ignore[arg-type]
        gate=gate,
        top_k=3,
        similarity_threshold=0.5,
    )

    result = coordinator.recall("a long enough prompt to bypass the gate")

    assert result == []


def test_timeout_returns_empty() -> None:
    """A blocking retriever wrapped in ``TimeoutRetriever`` yields ``[]`` within ~100 ms."""
    executor = RetrievalExecutor(max_workers=1)
    try:
        blocking = _RecorderRetriever(delay_seconds=1.0)
        wrapped = TimeoutRetriever(
            inner=blocking,  # type: ignore[arg-type]
            timeout_seconds=0.05,
            executor=executor,
        )
        gate = TrivialGate()
        coordinator = RecallCoordinator(
            retriever=wrapped,
            gate=gate,
            top_k=3,
            similarity_threshold=0.5,
        )

        start = time.perf_counter()
        result = coordinator.recall("a long enough prompt to bypass the gate")
        elapsed = time.perf_counter() - start

        assert result == []
        # The decorator returns immediately after the timeout fires; allow some slack.
        assert elapsed < 0.2
    finally:
        executor.shutdown()


def test_top_k_passed_through() -> None:
    """``RecallCoordinator(top_k=5)`` forwards ``top_k=5`` to the retriever."""
    retriever = _RecorderRetriever()
    gate = TrivialGate()
    coordinator = RecallCoordinator(
        retriever=retriever,  # type: ignore[arg-type]
        gate=gate,
        top_k=5,
        similarity_threshold=0.5,
    )

    coordinator.recall("a long enough prompt to bypass the gate")

    assert retriever.calls == [("a long enough prompt to bypass the gate", 5)]


def test_recall_satisfies_retriever_protocol() -> None:
    """The injected ``Retriever`` parameter accepts anything satisfying the Protocol.

    ``Retriever`` is ``@runtime_checkable``; the coordinator must not reject
    compliant retrievers (e.g. test doubles).
    """
    retriever = _RecorderRetriever()
    assert isinstance(retriever, Retriever)


def test_recall_latency_under_threshold() -> None:
    """End-to-end recall < 100 ms with the production wiring path (fakes + real Decorator).

    Pinned by ``contracts.md`` behavioural contract #11 — the deliverable's
    UX budget. If this fails, recall latency is not negligible and DO-09
    must implement LLM-call overlap (see ``workflow.md`` step 10).

    ``FakeEmbedder`` returns a fixed 384-dim vector synchronously in < 1 ms.
    ``FakeVectorStore`` returns 3 ``RetrievedChunk``s in < 1 ms. The fake
    retriever is wrapped in ``TimeoutRetriever(timeout_seconds=0.05)``
    with a real ``RetrievalExecutor`` and passed to
    ``RecallCoordinator(top_k=3, similarity_threshold=0.5)``.
    """
    chunk_a = Chunk(text="memory a", session_id="s")
    chunk_b = Chunk(text="memory b", session_id="s")
    chunk_c = Chunk(text="memory c", session_id="s")

    class _FakeEmbedder:
        def is_ready(self) -> bool:
            return True

        def embed_query(self, text: str) -> list[float]:
            return [0.1] * 384

    class _FakeVectorStore:
        def query(self, vector: list[float], top_k: int) -> list[tuple[Chunk, float]]:
            return [
                (chunk_a, 0.9),
                (chunk_b, 0.7),
                (chunk_c, 0.6),
            ]

        def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
            pass

    from simple_cli_coder_with_rag.application.retrievers.base_retriever import (
        BaseRetriever,
    )

    executor = RetrievalExecutor(max_workers=2)
    try:
        base = BaseRetriever(
            embedder=_FakeEmbedder(),  # type: ignore[arg-type]
            vector_store=_FakeVectorStore(),  # type: ignore[arg-type]
        )
        wrapped = TimeoutRetriever(
            inner=base,
            timeout_seconds=0.05,
            executor=executor,
        )
        coordinator = RecallCoordinator(
            retriever=wrapped,
            gate=TrivialGate(),
            top_k=3,
            similarity_threshold=0.5,
        )

        start = time.perf_counter()
        result = coordinator.recall("why does ModuleNotFoundError happen for foo")
        elapsed = time.perf_counter() - start

        assert result == [
            ("", 0, "memory a"),
            ("", 0, "memory b"),
            ("", 0, "memory c"),
        ]
        assert elapsed < 0.1, f"recall latency {elapsed * 1000:.1f} ms exceeded 100 ms budget"
    finally:
        executor.shutdown()
