"""Tests for the compacted-session Pydantic models.

Pinned by ``agent-development/04-learn-compaction/tests.md``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from simple_cli_coder_with_rag.domain.compacted import (
    CompactedSession,
    DecisionRecord,
    ErrorRecord,
)


def test_compacted_session_round_trip() -> None:
    """A fully-populated ``CompactedSession`` survives a JSON round trip."""
    created = datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)
    c = CompactedSession(
        session_id="abc123",
        created_at=created,
        summary="Implemented /learn compaction.",
        errors=[ErrorRecord(signature="E", message="boom", occurrences=2)],
        decisions=[DecisionRecord(summary="Use Haiku", rationale="Cheap")],
    )

    rebuilt = CompactedSession.model_validate_json(c.model_dump_json())

    assert rebuilt == c


def test_error_record_occurrences_ge_one() -> None:
    """``occurrences`` must be at least 1; zero is a validation error."""
    with pytest.raises(ValidationError):
        ErrorRecord(signature="x", message="m", occurrences=0)


def test_decision_record_round_trip() -> None:
    """``DecisionRecord.model_dump_json()`` produces a stable string."""
    d = DecisionRecord(summary="s", rationale="r")
    payload = d.model_dump_json()
    assert isinstance(payload, str)
    assert payload  # non-empty
    # Round trip as a belt-and-braces check.
    assert DecisionRecord.model_validate_json(payload) == d


def test_compacted_default_empty_lists() -> None:
    """``errors`` and ``decisions`` default to empty lists."""
    c = CompactedSession(
        session_id="x",
        created_at=datetime.now(UTC),
        summary="s",
    )

    assert c.errors == []
    assert c.decisions == []
