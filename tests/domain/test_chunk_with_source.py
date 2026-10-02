"""Tests for the ``Chunk`` schema patch (DO-13).

Pinned by ``agent-development/13-rag-over-documents-supabase/tests.md``.

The ``source`` and ``chunk_index`` fields default to empty / zero so
the pre-DO-13 ``Chunk(text=..., session_id=...)`` call sites still
work. The new fields surface the canonical file path + per-source
index the chat-time prompt uses for citations.
"""

from __future__ import annotations

from simple_cli_coder_with_rag.domain.chunk import Chunk


def test_chunk_default_source_empty() -> None:
    """``Chunk(text=...)`` defaults ``source=''`` and ``chunk_index=0``."""
    chunk = Chunk(text="x", session_id="s")

    assert chunk.source == ""
    assert chunk.chunk_index == 0


def test_chunk_with_source_round_trips() -> None:
    """``Chunk(text=, source=, chunk_index=)`` validates and dumps both fields."""
    chunk = Chunk(text="x", session_id="s", source="foo.md", chunk_index=2)

    assert chunk.source == "foo.md"
    assert chunk.chunk_index == 2

    rebuilt = Chunk.model_validate_json(chunk.model_dump_json())
    assert rebuilt == chunk


def test_chunk_validate_omitted_source() -> None:
    """``model_validate`` with ``chunk_index`` succeeds with the default source."""
    chunk = Chunk.model_validate({"text": "x", "session_id": "s", "chunk_index": 3})

    assert chunk.source == ""
    assert chunk.chunk_index == 3
