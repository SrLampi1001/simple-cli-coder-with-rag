"""Tests for the ``SemanticChunker`` Strategy implementation.

Pinned by ``agent-development/05-chunker-strategy/tests.md``.

The semantic chunker is the alternative Strategy: one chunk per logical
record (summary, error, decision). It is selected by setting
``CHUNKER_STRATEGY=semantic`` in the environment.
"""

from __future__ import annotations

from datetime import UTC, datetime

from simple_cli_coder_with_rag.application.chunkers.semantic import SemanticChunker
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


def test_semantic_one_chunk_per_record() -> None:
    """One summary + two errors + one decision → exactly four chunks."""
    chunks = SemanticChunker().chunk(
        _session(
            summary="s",
            errors=[
                ErrorRecord(signature="E1", message="m1", occurrences=1),
                ErrorRecord(signature="E2", message="m2", occurrences=1),
            ],
            decisions=[DecisionRecord(summary="D", rationale="r")],
        )
    )

    assert len(chunks) == 4


def test_semantic_metadata_summary() -> None:
    """The summary chunk carries ``source == "summary"``."""
    chunks = SemanticChunker().chunk(_session(summary="only-summary"))

    assert len(chunks) == 1
    assert chunks[0].metadata["source"] == "summary"
    assert chunks[0].text == "only-summary"


def test_semantic_metadata_errors() -> None:
    """Every error becomes a chunk with ``source == "error"`` and the ``Error:`` prefix."""
    chunks = SemanticChunker().chunk(
        _session(
            errors=[
                ErrorRecord(signature="E1", message="boom one", occurrences=1),
                ErrorRecord(signature="E2", message="boom two", occurrences=1),
            ]
        )
    )

    assert len(chunks) == 2
    assert all(c.metadata["source"] == "error" for c in chunks)
    assert chunks[0].text.startswith("Error: E1")
    assert "boom one" in chunks[0].text
    assert chunks[1].text.startswith("Error: E2")


def test_semantic_metadata_decisions() -> None:
    """Every decision becomes a chunk with ``source == "decision"`` and the ``Decision:`` prefix."""
    chunks = SemanticChunker().chunk(
        _session(decisions=[DecisionRecord(summary="Use X", rationale="Why")])
    )

    assert len(chunks) == 1
    assert chunks[0].metadata["source"] == "decision"
    assert chunks[0].text.startswith("Decision: Use X")
    assert "Why" in chunks[0].text


def test_semantic_session_id_propagates() -> None:
    """Every chunk inherits the parent compacted session's ``session_id``."""
    session = _session(
        summary="s",
        errors=[ErrorRecord(signature="E", message="m", occurrences=1)],
        decisions=[DecisionRecord(summary="D", rationale="r")],
    )
    chunks = SemanticChunker().chunk(session)

    assert len(chunks) == 3
    for chunk in chunks:
        assert chunk.session_id == session.session_id


def test_semantic_empty_compacted_returns_empty() -> None:
    """A compacted session with no records yields ``[]``."""
    assert SemanticChunker().chunk(_session()) == []


def test_semantic_returns_chunk_instances() -> None:
    """The chunker returns ``Chunk`` instances."""
    chunks = SemanticChunker().chunk(_session(summary="x"))

    assert len(chunks) == 1
    assert isinstance(chunks[0], Chunk)


def test_semantic_metadata_index_is_sequential() -> None:
    """Each chunk carries an ``index`` field counting from zero, in source order."""
    chunks = SemanticChunker().chunk(
        _session(
            summary="s",
            errors=[ErrorRecord(signature="E", message="m", occurrences=1)],
            decisions=[DecisionRecord(summary="D", rationale="r")],
        )
    )

    assert [c.metadata["index"] for c in chunks] == [0, 1, 2]
