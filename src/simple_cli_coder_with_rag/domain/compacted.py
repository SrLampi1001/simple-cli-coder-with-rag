"""Pydantic models for compacted sessions produced by ``/learn``.

This is the **data layer** for the ``/learn`` output. The REPL (DO-04) pipes
``CompactedSession`` JSON into the on-disk store; the chunker (DO-05) and
embedder (DO-06) consume these models and split them into ``Chunk`` records
that the vector store (DO-07) persists.

The schema is intentionally narrow: it carries only what the downstream
stages need (a summary, a list of structured errors, a list of structured
decisions). Anything richer (token budgets, source pointers, …) is added
later behind the same Pydantic v2 surface so the JSON contract is
backwards-compatible.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ErrorRecord(BaseModel):
    """A recurring failure surfaced by the LLM during compaction.

    ``signature`` is the stable, machine-friendly key (e.g.
    ``"ModuleNotFoundError: No module named 'foo'"``); ``message`` is the
    longer human description. ``occurrences`` records how many times the
    signature appeared in the source session and is the basis for ranking
    during the ``/learn`` summary.
    """

    signature: str
    message: str
    occurrences: int = Field(ge=1)


class DecisionRecord(BaseModel):
    """A design or implementation decision extracted from the session."""

    summary: str
    rationale: str


class CompactedSession(BaseModel):
    """The structured result of a single ``/learn`` compaction pass.

    Serialised to ``<session_id>.compacted.json`` and overwritten on every
    call (idempotent — the second ``/learn`` on the same session replaces
    the first file in place).
    """

    session_id: str
    created_at: datetime
    summary: str
    errors: list[ErrorRecord] = Field(default_factory=list)
    decisions: list[DecisionRecord] = Field(default_factory=list)


__all__ = ["CompactedSession", "DecisionRecord", "ErrorRecord"]
