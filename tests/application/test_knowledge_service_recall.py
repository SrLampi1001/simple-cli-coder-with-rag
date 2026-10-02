"""Tests for ``KnowledgeService.recall`` after DO-08 wires the retriever.

Pinned by ``agent-development/08-retriever-with-decorator/tests.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from simple_cli_coder_with_rag.application.chunkers.fixed_size import FixedSizeChunker
from simple_cli_coder_with_rag.application.compactor import Compactor
from simple_cli_coder_with_rag.application.knowledge_service import KnowledgeService
from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.domain.chunk import Chunk
from simple_cli_coder_with_rag.domain.embedder import EmbedderNotReady
from simple_cli_coder_with_rag.domain.retriever import RetrievedChunk

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _build_service(
    tmp_path: Path, fake_llm: object, *, retriever: object | None = None
) -> KnowledgeService:
    """Build a ``KnowledgeService`` with optional ``retriever`` wired in."""
    store = SessionStore(tmp_path)
    compactor = Compactor(llm=fake_llm, compactor_model="test")  # type: ignore[arg-type]
    return KnowledgeService(
        llm=fake_llm,  # type: ignore[arg-type]
        chat_model="m",
        session_store=store,
        compactor=compactor,
        chunker=FixedSizeChunker(),
        retriever=retriever,  # type: ignore[arg-type]
    )


def test_recall_returns_chunk_texts(tmp_path: Path, mocker: MockerFixture) -> None:
    """``recall`` returns the chunk texts in retrieval order."""
    fake_llm = mocker.MagicMock()

    class _Ret:
        def retrieve(self, query: str, *, top_k: int) -> list[RetrievedChunk]:
            return [
                RetrievedChunk(Chunk(text="a", session_id="s"), 0.9),
                RetrievedChunk(Chunk(text="b", session_id="s"), 0.5),
            ]

    service = _build_service(tmp_path, fake_llm, retriever=_Ret())

    assert service.recall("q") == ["a", "b"]


def test_recall_returns_empty_on_embedder_not_ready(tmp_path: Path, mocker: MockerFixture) -> None:
    """When the retriever raises ``EmbedderNotReady`` (a RuntimeError), recall returns ``[]``."""
    fake_llm = mocker.MagicMock()

    class _Ret:
        def retrieve(self, query: str, *, top_k: int) -> list[RetrievedChunk]:
            raise EmbedderNotReady("still loading")

    service = _build_service(tmp_path, fake_llm, retriever=_Ret())

    assert service.recall("q") == []


def test_recall_returns_empty_on_timeout(tmp_path: Path, mocker: MockerFixture) -> None:
    """When a wrapped TimeoutRetriever returns ``[]`` (timeout fired), recall returns ``[]``."""
    fake_llm = mocker.MagicMock()

    class _TimeoutRet:
        def retrieve(self, query: str, *, top_k: int) -> list[RetrievedChunk]:
            return []

    service = _build_service(tmp_path, fake_llm, retriever=_TimeoutRet())

    assert service.recall("q") == []


def test_recall_returns_empty_when_retriever_is_none(tmp_path: Path, mocker: MockerFixture) -> None:
    """When no retriever is wired, recall is a no-op."""
    fake_llm = mocker.MagicMock()
    service = _build_service(tmp_path, fake_llm, retriever=None)

    assert service.recall("q") == []
