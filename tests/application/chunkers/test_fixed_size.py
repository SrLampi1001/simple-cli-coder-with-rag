"""Tests for the ``FixedSizeChunker`` Strategy implementation.

Pinned by ``agent-development/05-chunker-strategy/tests.md``.

The fixed-size chunker concatenates ``CompactedSession`` records (summary,
errors, decisions) and slides a ``max_chars`` window with ``overlap`` overlap.
It is the default Strategy picked by the composition root when the user
leaves ``CHUNKER_STRATEGY`` unset.
"""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import pairwise

import pytest

from simple_cli_coder_with_rag.application.chunkers.fixed_size import FixedSizeChunker
from simple_cli_coder_with_rag.domain.chunk import Chunk
from simple_cli_coder_with_rag.domain.compacted import (
    CompactedSession,
    DecisionRecord,
    ErrorRecord,
)


def _session(
    *,
    summary: str = "",
    errors: list[ErrorRecord] | None = None,
    decisions: list[DecisionRecord] | None = None,
) -> CompactedSession:
    return CompactedSession(
        session_id="sess-1",
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        summary=summary,
        errors=list(errors or []),
        decisions=list(decisions or []),
    )


def test_fixed_size_rejects_overlap_ge_max_chars() -> None:
    """``overlap >= max_chars`` is an off-by-one trap; ``FixedSizeChunker`` refuses it."""
    with pytest.raises(ValueError, match="overlap"):
        FixedSizeChunker(max_chars=10, overlap=10)
    with pytest.raises(ValueError, match="overlap"):
        FixedSizeChunker(max_chars=10, overlap=11)
    with pytest.raises(ValueError, match="overlap"):
        FixedSizeChunker(max_chars=10, overlap=-1)


def test_fixed_size_rejects_non_positive_max_chars() -> None:
    """``max_chars <= 0`` is rejected — the window never advances otherwise."""
    with pytest.raises(ValueError, match="max_chars"):
        FixedSizeChunker(max_chars=0, overlap=0)
    with pytest.raises(ValueError, match="max_chars"):
        FixedSizeChunker(max_chars=-1, overlap=0)


def test_fixed_size_short_text_single_chunk() -> None:
    """A short summary fits into exactly one chunk with the original text."""
    chunker = FixedSizeChunker(max_chars=512, overlap=64)
    chunks = chunker.chunk(_session(summary="hi"))

    assert len(chunks) == 1
    assert chunks[0].text == "hi"
    assert chunks[0].metadata["source"] == "summary"


def test_fixed_size_long_text_multiple_chunks() -> None:
    """A 5000-char summary produces many chunks; consecutive chunks overlap."""
    chunker = FixedSizeChunker(max_chars=512, overlap=64)
    chunks = chunker.chunk(_session(summary="x" * 5000))

    assert len(chunks) > 1
    # Every chunk except the last must be exactly ``max_chars`` long.
    for chunk in chunks[:-1]:
        assert len(chunk.text) == 512, len(chunk.text)
    # Consecutive chunks overlap by exactly ``overlap`` chars: the tail of
    # ``chunks[i]`` is the head of ``chunks[i+1]``.
    for a, b in pairwise(chunks):
        assert a.text[-64:] == b.text[:64], "consecutive chunks must overlap by 64 chars"


def test_fixed_size_metadata_source_summary() -> None:
    """A summary-only input tags every chunk with ``source == "summary"``."""
    chunks = FixedSizeChunker(max_chars=4, overlap=1).chunk(_session(summary="abcdef"))

    assert chunks
    for chunk in chunks:
        assert chunk.metadata["source"] == "summary"


def test_fixed_size_metadata_source_error() -> None:
    """An error record produces at least one chunk with ``source == "error"``.

    ``max_chars=15`` keeps each record's window small enough that the
    single error record yields one error chunk; the chunk's text starts
    with the ``"Error: <signature>"`` prefix.
    """
    chunks = FixedSizeChunker(max_chars=15, overlap=0).chunk(
        _session(
            errors=[ErrorRecord(signature="E", message="boom", occurrences=1)],
        )
    )

    error_chunks = [c for c in chunks if c.metadata["source"] == "error"]
    assert error_chunks, "expected at least one error chunk"
    # The first error chunk starts with the documented prefix.
    assert error_chunks[0].text.startswith("Error: E"), (
        f"first error chunk must start with 'Error: E': {error_chunks[0].text!r}"
    )


def test_fixed_size_metadata_source_decision() -> None:
    """A decision record produces at least one chunk with ``source == "decision"``.

    ``max_chars=15`` keeps each record's window small enough that the
    single decision record yields one decision chunk; the chunk's text
    starts with the ``"Decision: <summary>"`` prefix.
    """
    chunks = FixedSizeChunker(max_chars=15, overlap=0).chunk(
        _session(
            decisions=[DecisionRecord(summary="Use X", rationale="Because")],
        )
    )

    decision_chunks = [c for c in chunks if c.metadata["source"] == "decision"]
    assert decision_chunks, "expected at least one decision chunk"
    assert decision_chunks[0].text.startswith("Decision: Use X"), (
        f"first decision chunk must start with 'Decision: Use X': {decision_chunks[0].text!r}"
    )


def test_fixed_size_session_id_propagates() -> None:
    """Every chunk inherits the parent compacted session's ``session_id``."""
    session = _session(
        summary="a long summary " * 50,
        errors=[ErrorRecord(signature="E", message="boom", occurrences=1)],
    )
    chunks = FixedSizeChunker().chunk(session)

    assert chunks
    for chunk in chunks:
        assert chunk.session_id == session.session_id


def test_fixed_size_empty_compacted_returns_empty() -> None:
    """A compacted session with no records yields ``[]``, not a single empty chunk."""
    chunks = FixedSizeChunker().chunk(_session())

    assert chunks == []


def test_fixed_size_returns_chunk_instances() -> None:
    """The chunker returns ``Chunk`` instances (Pydantic model with the right shape)."""
    chunks = FixedSizeChunker().chunk(_session(summary="hi"))

    assert all(isinstance(c, Chunk) for c in chunks)
