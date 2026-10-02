"""Tests for ``KnowledgeService.set_vector_store`` (DO-13).

Pinned by ``agent-development/13-rag-over-documents-supabase/tests.md``.

Mirrors the DO-11 ``set_llm`` pattern: ``set_vector_store`` swaps
the vector store and rebuilds the ``RecallCoordinator`` around the
new retriever. The gate, ``top_k``, and similarity threshold from
the OLD coordinator are preserved on the NEW coordinator — the
user only swapped the backend, not the retrieval tuning.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from simple_cli_coder_with_rag.application.chunkers.fixed_size import FixedSizeChunker
from simple_cli_coder_with_rag.application.compactor import Compactor
from simple_cli_coder_with_rag.application.knowledge_service import KnowledgeService
from simple_cli_coder_with_rag.application.recall_coordinator import (
    RecallCoordinator,
)
from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.application.trivial_gate import TrivialGate
from simple_cli_coder_with_rag.domain.vector_store import VectorStore

if TYPE_CHECKING:
    pass


class _FakeRetriever:
    """Minimal ``Retriever`` stand-in for the set_vector_store test."""

    def __init__(self, name: str = "retriever") -> None:
        self.name = name

    def retrieve(self, query: str, *, top_k: int) -> list[object]:
        return []


def _build_service(
    tmp_path: Path,
    *,
    vector_store: VectorStore | None = None,
    coordinator: RecallCoordinator | None = None,
) -> tuple[KnowledgeService, SessionStore]:
    """Build a ``KnowledgeService`` with optional store + coordinator wiring."""
    store = SessionStore(tmp_path)
    fake_llm = MagicMock()
    compactor = Compactor(llm=fake_llm, compactor_model="m")
    return (
        KnowledgeService(
            llm=fake_llm,
            chat_model="m",
            session_store=store,
            compactor=compactor,
            chunker=FixedSizeChunker(),
            vector_store=vector_store,
            coordinator=coordinator,
        ),
        store,
    )


def _build_coordinator(retriever: _FakeRetriever | None = None) -> RecallCoordinator:
    """Build a real ``RecallCoordinator`` for the service."""
    return RecallCoordinator(
        retriever=retriever or _FakeRetriever(),  # type: ignore[arg-type]
        gate=TrivialGate(),
        top_k=3,
        similarity_threshold=0.5,
    )


def test_set_vector_store_swaps_store_and_retriever(tmp_path: Path) -> None:
    """``set_vector_store`` rebuilds the coordinator around the new retriever."""
    initial_coordinator = _build_coordinator()
    initial_store = MagicMock(spec=VectorStore)
    service, _ = _build_service(
        tmp_path, vector_store=initial_store, coordinator=initial_coordinator
    )

    new_store = MagicMock(spec=VectorStore)
    new_retriever = _FakeRetriever("new")
    service.set_vector_store(new_store, new_retriever)  # type: ignore[arg-type]

    assert service._vector_store is new_store
    assert service._coordinator is not None
    assert service._coordinator is not initial_coordinator
    # The new coordinator was built around the new retriever.
    assert service._coordinator._retriever is new_retriever


def test_set_vector_store_preserves_other_dependencies(tmp_path: Path) -> None:
    """Gate / top_k / threshold from the OLD coordinator are preserved on the NEW coordinator."""
    initial_coordinator = RecallCoordinator(
        retriever=_FakeRetriever("old"),
        gate=TrivialGate(),
        top_k=7,
        similarity_threshold=0.42,
    )
    service, _ = _build_service(
        tmp_path, vector_store=MagicMock(spec=VectorStore), coordinator=initial_coordinator
    )

    new_store = MagicMock(spec=VectorStore)
    new_retriever = _FakeRetriever("new")
    service.set_vector_store(new_store, new_retriever)  # type: ignore[arg-type]

    assert service._coordinator is not None
    assert service._coordinator.top_k == 7
    assert service._coordinator.similarity_threshold == 0.42
    # The gate is the same object — preserved across the swap.
    assert service._coordinator.gate is initial_coordinator.gate
    # The retriever is the new one.
    assert service._coordinator._retriever is new_retriever


def test_set_vector_store_without_coordinator_is_noop(tmp_path: Path) -> None:
    """A service without a coordinator keeps the new store but does not build a coordinator."""
    service, _ = _build_service(tmp_path, vector_store=None, coordinator=None)

    new_store = MagicMock(spec=VectorStore)
    new_retriever = _FakeRetriever("new")
    service.set_vector_store(new_store, new_retriever)  # type: ignore[arg-type]

    assert service._vector_store is new_store
    assert service._coordinator is None
