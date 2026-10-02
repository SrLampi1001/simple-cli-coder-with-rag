"""Tests for the ``Retriever`` Protocol and ``RetrievedChunk`` NamedTuple.

Pinned by ``agent-development/08-retriever-with-decorator/tests.md``.
"""

from __future__ import annotations

from simple_cli_coder_with_rag.domain.chunk import Chunk
from simple_cli_coder_with_rag.domain.retriever import RetrievedChunk, Retriever


def test_protocol_declares_retrieve() -> None:
    assert hasattr(Retriever, "retrieve")


def test_runtime_checkable() -> None:
    """Any class with the right method passes ``isinstance(x, Retriever)``."""

    class _Fake:
        def retrieve(self, query: str, *, top_k: int) -> list[RetrievedChunk]:
            return []

    assert isinstance(_Fake(), Retriever)


def test_retrieved_chunk_is_named_tuple() -> None:
    """``RetrievedChunk(chunk, similarity)`` is unpackable as ``(chunk, similarity)``."""
    chunk = Chunk(text="x", session_id="s")
    rc = RetrievedChunk(chunk=chunk, similarity=0.42)
    c, s = rc
    assert c is chunk
    assert s == 0.42
