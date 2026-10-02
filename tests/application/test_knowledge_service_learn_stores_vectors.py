"""Tests for ``KnowledgeService.learn`` wiring to the embedder + vector store.

Pinned by ``agent-development/07-vector-store-strategy/tests.md``.

The ``Embedder`` is a ``FakeEmbedder`` returning deterministic 384-dim
vectors from a hash of the text. The ``VectorStore`` is an in-memory
recording fake. The assertions verify that ``learn`` plumbs chunks
through the embedder and into the store exactly once.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

from simple_cli_coder_with_rag.application.chunkers.fixed_size import FixedSizeChunker
from simple_cli_coder_with_rag.application.compactor import Compactor
from simple_cli_coder_with_rag.application.knowledge_service import KnowledgeService
from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.domain.chunk import Chunk
from simple_cli_coder_with_rag.domain.embedder import Embedder
from simple_cli_coder_with_rag.domain.messages import (
    AssistantMessage,
    UserMessage,
)
from simple_cli_coder_with_rag.domain.vector_store import VectorStore

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


_EMBEDDING_DIM = 384


class _FakeEmbedder:
    """Deterministic 384-dim embedder for tests.

    Each text is hashed to seed a 384-dim unit-ish vector. Different
    texts produce different vectors; the same text always produces the
    same vector. ``is_ready`` is always ``True`` so the service never
    short-circuits.
    """

    def embed_query(self, text: str) -> list[float]:
        return _deterministic_vector(text)

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [_deterministic_vector(text) for text in texts]

    def warmup(self, *, timeout: float | None = None) -> None:
        return None

    def is_ready(self) -> bool:
        return True


class _RecordingVectorStore:
    """In-memory vector store that records every ``upsert`` invocation.

    ``upsert`` is replaceable: ``upsert(chunks, vectors)`` simply stores
    the inputs. ``query`` returns every stored chunk with similarity
    1.0 (the assertions only check ``upsert``).
    """

    def __init__(self) -> None:
        self.upsert_calls: list[tuple[list[Chunk], list[list[float]]]] = []
        self._stored: list[tuple[list[float], Chunk]] = []

    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        self.upsert_calls.append((list(chunks), [list(v) for v in vectors]))
        # Idempotent by session id (mirrors SqliteVecStore's contract).
        session_ids = {chunk.session_id for chunk in chunks}
        self._stored = [
            (vec, chunk) for vec, chunk in self._stored if chunk.session_id not in session_ids
        ]
        for chunk, vec in zip(chunks, vectors, strict=True):
            self._stored.append((list(vec), chunk))

    def query(self, vector: list[float], top_k: int) -> list[tuple[Chunk, float]]:
        return [(chunk, 1.0) for _vec, chunk in self._stored[:top_k]]


def _deterministic_vector(text: str) -> list[float]:
    """Return a deterministic 384-dim vector seeded from ``text``.

    Different texts produce different vectors. The values are not unit
    vectors on purpose — the tests do not check magnitudes.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    # Repeat the digest to fill 384 floats; each float is mapped from a
    # byte pair ``[0, 255]`` → ``[-1.0, 1.0]``.
    out: list[float] = []
    for i in range(_EMBEDDING_DIM):
        byte = digest[(i * 2) % len(digest)] ^ digest[(i * 3 + 1) % len(digest)]
        out.append((byte / 255.0) * 2.0 - 1.0)
    return out


def _build_service(
    tmp_path: Path,
    fake_llm: object,
    *,
    embedder: Embedder | None = None,
    vector_store: VectorStore | None = None,
) -> tuple[KnowledgeService, SessionStore]:
    """Build a ``KnowledgeService`` wired to a real session store and the given fakes."""
    store = SessionStore(tmp_path)
    compactor = Compactor(llm=fake_llm, compactor_model="test")  # type: ignore[arg-type]
    service = KnowledgeService(
        llm=fake_llm,  # type: ignore[arg-type]
        chat_model="chat-model",
        session_store=store,
        compactor=compactor,
        chunker=FixedSizeChunker(),
        embedder=embedder,
        vector_store=vector_store,
    )
    return service, store


def test_learn_calls_embedder_for_each_chunk(tmp_path: Path, mocker: MockerFixture) -> None:
    """After ``learn``, the embedder was called once per chunk with that chunk's text."""
    embedder = _FakeEmbedder()
    spy = mocker.MagicMock(wraps=embedder)
    vector_store = _RecordingVectorStore()

    fake_llm = mocker.MagicMock()
    fake_llm.complete.return_value = (
        '{"session_id":"stub","created_at":"2026-10-01T00:00:00Z",'
        '"summary":"a real summary","errors":[],"decisions":[]}'
    )

    service, store = _build_service(tmp_path, fake_llm, embedder=spy, vector_store=vector_store)

    session_id = "sess-embed"
    store.append(session_id, UserMessage(content="hi"))
    store.append(session_id, AssistantMessage(content="hello"))

    count = service.learn(session_id)
    assert count >= 1

    # The embedder was called once with the batched text list — verify
    # the embedder received one entry per chunk produced by the chunker.
    embed_passages_calls = spy.embed_passages.call_args_list
    assert embed_passages_calls, "embedder.embed_passages was never called"
    batched_texts = embed_passages_calls[0].args[0]
    assert len(batched_texts) == len(service.last_chunks)
    # Every chunk's text was in the batch.
    assert set(batched_texts) == {c.text for c in service.last_chunks}


def test_learn_calls_vector_store_upsert_with_chunks_and_vectors(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """``vector_store.upsert(chunks, vectors)`` receives the chunks and their embedded vectors."""
    embedder = _FakeEmbedder()
    vector_store = _RecordingVectorStore()

    fake_llm = mocker.MagicMock()
    fake_llm.complete.return_value = (
        '{"session_id":"stub","created_at":"2026-10-01T00:00:00Z",'
        '"summary":"another summary","errors":[],"decisions":[]}'
    )

    service, store = _build_service(
        tmp_path, fake_llm, embedder=embedder, vector_store=vector_store
    )

    session_id = "sess-upsert"
    store.append(session_id, UserMessage(content="x"))
    store.append(session_id, AssistantMessage(content="y"))

    service.learn(session_id)

    assert vector_store.upsert_calls, "vector_store.upsert was never called"
    chunks_arg, vectors_arg = vector_store.upsert_calls[0]

    # The chunks and vectors match: same length, each vector was
    # produced by the embedder for that chunk's text.
    assert len(chunks_arg) == len(service.last_chunks)
    assert len(vectors_arg) == len(chunks_arg)

    for chunk, vec in zip(chunks_arg, vectors_arg, strict=True):
        assert chunk.text in {c.text for c in service.last_chunks}
        # The embedder is deterministic — verify each vector matches.
        assert vec == _deterministic_vector(chunk.text)


def test_learn_passes_through_when_embedder_missing(tmp_path: Path, mocker: MockerFixture) -> None:
    """No embedder / vector store: ``learn`` still chunks but skips the upsert stage.

    The original ``learn`` path (DO-04 / DO-05) is preserved: ``learn``
    returns the chunk count and ``last_chunks`` is populated. Storing is
    skipped when ``vector_store is None``.
    """
    fake_llm = mocker.MagicMock()
    fake_llm.complete.return_value = (
        '{"session_id":"stub","created_at":"2026-10-01T00:00:00Z",'
        '"summary":"plain","errors":[],"decisions":[]}'
    )

    service, store = _build_service(tmp_path, fake_llm)

    session_id = "sess-plain"
    store.append(session_id, UserMessage(content="hi"))

    count = service.learn(session_id)

    assert isinstance(count, int)
    assert count >= 1
    assert service.last_chunks
