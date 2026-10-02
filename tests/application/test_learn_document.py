"""Tests for ``KnowledgeService.learn_document`` (DO-13).

Pinned by ``agent-development/13-rag-over-documents-supabase/tests.md``.

The integration test stubs the document loader, chunker, embedder,
and vector store; the assertions verify the order of the calls
and the chunks / vectors the service hands off to the store.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from simple_cli_coder_with_rag.application.chunkers.fixed_size import FixedSizeChunker
from simple_cli_coder_with_rag.application.compactor import Compactor
from simple_cli_coder_with_rag.application.knowledge_service import KnowledgeService
from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.domain.document_metadata import DocumentMetadata
from simple_cli_coder_with_rag.domain.embedder import Embedder
from simple_cli_coder_with_rag.domain.vector_store import VectorStore

if TYPE_CHECKING:
    pass


def _build_service(
    tmp_path: Path,
    *,
    embedder: Embedder | None = None,
    vector_store: VectorStore | None = None,
) -> tuple[KnowledgeService, SessionStore]:
    """Build a ``KnowledgeService`` with the given embedder + store."""
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
            embedder=embedder,
            vector_store=vector_store,
        ),
        store,
    )


def test_learn_document_loads_chunks_embeds_upserts(tmp_path: Path) -> None:
    """The pipeline: loader → chunker → embedder → vector store, in that order."""
    embedder = MagicMock(spec=Embedder)
    embedder.warmup.return_value = None
    # ``hello world`` is short enough to fit in one chunk with the
    # default ``chunk_size=800`` so the embedder is called with
    # one text. We stub the vector to match.
    embedder.embed_passages.return_value = [[0.1, 0.2, 0.3]]
    vector_store = MagicMock(spec=VectorStore)

    service, _ = _build_service(tmp_path, embedder=embedder, vector_store=vector_store)

    # Stub the loader to return a known text + metadata.
    loader = MagicMock()
    loader.load.return_value = (
        "hello world",
        DocumentMetadata(source="/abs/foo.md", file_type="md", byte_size=11),
    )

    path = Path("/abs/foo.md")
    count = service.learn_document(path, loader=loader)

    assert count == 1
    loader.load.assert_called_once_with(path)
    embedder.warmup.assert_called_once()
    embedder.embed_passages.assert_called_once()
    chunk_texts = embedder.embed_passages.call_args.args[0]
    assert chunk_texts == ["hello world"]  # short text -> one chunk
    vector_store.upsert.assert_called_once()
    chunks_arg, vectors_arg = vector_store.upsert.call_args.args
    assert len(chunks_arg) == 1
    assert len(vectors_arg) == 1
    assert chunks_arg[0].text == "hello world"
    assert chunks_arg[0].source == "/abs/foo.md"
    assert chunks_arg[0].chunk_index == 0
    assert vectors_arg[0] == [0.1, 0.2, 0.3]


def test_learn_document_returns_zero_on_empty_text(tmp_path: Path) -> None:
    """Empty text from the loader (e.g. blank PDF) returns 0 chunks and skips the upsert."""
    embedder = MagicMock(spec=Embedder)
    vector_store = MagicMock(spec=VectorStore)

    service, _ = _build_service(tmp_path, embedder=embedder, vector_store=vector_store)

    loader = MagicMock()
    loader.load.return_value = (
        "",
        DocumentMetadata(source="/abs/empty.pdf", file_type="pdf", page_count=0, byte_size=10),
    )

    count = service.learn_document(Path("/abs/empty.pdf"), loader=loader)

    assert count == 0
    vector_store.upsert.assert_not_called()
    embedder.embed_passages.assert_not_called()


def test_learn_document_skips_upsert_without_store(tmp_path: Path) -> None:
    """No embedder / vector store: ``learn_document`` still chunks but skips the upsert."""
    service, _ = _build_service(tmp_path, embedder=None, vector_store=None)

    loader = MagicMock()
    loader.load.return_value = (
        "text",
        DocumentMetadata(source="/abs/x.md", file_type="md", byte_size=4),
    )

    count = service.learn_document(Path("/abs/x.md"), loader=loader)

    assert count >= 1
    # last_chunks is populated even without a store.
    assert service.last_chunks
    assert all(c.source == "/abs/x.md" for c in service.last_chunks)
