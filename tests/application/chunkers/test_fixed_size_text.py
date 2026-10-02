"""Tests for ``FixedSizeChunker.chunk_text`` (DO-13).

Pinned by ``agent-development/13-rag-over-documents-supabase/tests.md``.

The ``chunk_text`` method is the companion to ``chunk`` for the
``/learn <path>`` document ingestion path. It takes raw text + a
``source`` (the document path) and produces chunks tagged with
``Chunk.source`` and ``Chunk.chunk_index`` so the chat-time
prompt can cite them.
"""

from __future__ import annotations

from simple_cli_coder_with_rag.application.chunkers.fixed_size import FixedSizeChunker
from simple_cli_coder_with_rag.domain.chunk import Chunk
from simple_cli_coder_with_rag.domain.compacted import CompactedSession


def test_chunk_text_short_returns_single_chunk() -> None:
    """Short text produces a single chunk with the original text."""
    chunks = FixedSizeChunker().chunk_text("hello world", source="foo.md")

    assert len(chunks) == 1
    assert chunks[0].text == "hello world"
    assert chunks[0].source == "foo.md"
    assert chunks[0].chunk_index == 0


def test_chunk_text_long_uses_overlap() -> None:
    """Long text produces multiple chunks with the documented overlap."""
    chunks = FixedSizeChunker().chunk_text("a" * 2000, source="x", chunk_size=800, overlap=120)

    # Three chunks: 800, 800, 640 chars. The chunker uses a
    # ``chunk_size``-wide window sliding by
    # ``step = chunk_size - overlap = 680`` characters — so
    # consecutive chunks share an overlap of 120 chars and each
    # full chunk is ``chunk_size`` wide. The last chunk is the
    # tail (640 chars, the rest of the text).
    assert len(chunks) == 3
    assert len(chunks[0].text) == 800
    assert len(chunks[1].text) == 800
    assert len(chunks[2].text) == 640

    # Indices increment.
    assert [c.chunk_index for c in chunks] == [0, 1, 2]

    # The first two chunks share an overlap window of 120 chars —
    # the tail of chunk 0 is the head of chunk 1.
    assert chunks[0].text[-120:] == chunks[1].text[:120]


def test_chunk_text_empty_returns_empty_list() -> None:
    """Empty input returns ``[]`` (the embedder never sees a zero-length input)."""
    chunks = FixedSizeChunker().chunk_text("", source="x")

    assert chunks == []


def test_chunk_text_source_propagates_to_all_chunks() -> None:
    """Every chunk in the output carries the same ``source``."""
    chunks = FixedSizeChunker().chunk_text(
        "x" * 5000, source="docs/foo.md", chunk_size=200, overlap=20
    )

    assert chunks
    for chunk in chunks:
        assert chunk.source == "docs/foo.md"


def test_chunk_text_chunk_index_increments() -> None:
    """``chunk_index`` is 0, 1, 2, … in document order."""
    chunks = FixedSizeChunker().chunk_text("y" * 1500, source="x", chunk_size=500, overlap=50)

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_chunk_text_session_id_empty() -> None:
    """Document chunks have ``session_id=''`` (not session-scoped)."""
    chunks = FixedSizeChunker().chunk_text("hello", source="x")

    assert chunks[0].session_id == ""


def test_chunk_text_rejects_overlap_ge_chunk_size() -> None:
    """``overlap >= chunk_size`` is rejected (would never advance the window)."""
    chunker = FixedSizeChunker()
    with __import__("pytest").raises(ValueError, match="overlap"):
        chunker.chunk_text("hello", source="x", chunk_size=10, overlap=10)


def test_chunk_text_rejects_non_positive_chunk_size() -> None:
    """``chunk_size <= 0`` is rejected."""
    chunker = FixedSizeChunker()
    with __import__("pytest").raises(ValueError, match="chunk_size"):
        chunker.chunk_text("hello", source="x", chunk_size=0, overlap=0)


def test_existing_chunk_compacted_session_unchanged() -> None:
    """Smoke-test the existing ``chunk(compacted)`` path is not regressed by DO-13.

    The ``chunk`` method is unchanged by this DO; these two
    assertions pin the behaviour so a future refactor cannot
    silently break the DO-04 / DO-09 callers.
    """
    chunker = FixedSizeChunker()
    empty = CompactedSession(
        session_id="s",
        created_at=__import__("datetime").datetime(2026, 10, 1, tzinfo=__import__("datetime").UTC),
        summary="",
        errors=[],
        decisions=[],
    )
    assert chunker.chunk(empty) == []

    populated = CompactedSession(
        session_id="s",
        created_at=__import__("datetime").datetime(2026, 10, 1, tzinfo=__import__("datetime").UTC),
        summary="a real summary",
        errors=[],
        decisions=[],
    )
    chunks = chunker.chunk(populated)
    assert len(chunks) == 1
    assert isinstance(chunks[0], Chunk)
    assert chunks[0].text == "a real summary"
    # DO-13: session chunks have empty source / chunk_index 0.
    assert chunks[0].source == ""
    assert chunks[0].chunk_index == 0
