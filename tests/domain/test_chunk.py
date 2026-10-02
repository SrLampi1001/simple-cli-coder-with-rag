"""Tests for the ``Chunk`` Pydantic model.

Pinned by ``agent-development/05-chunker-strategy/tests.md``.

A ``Chunk`` is the unit the embedder (DO-06) and the vector store (DO-07)
operate on. The schema is intentionally narrow — everything that flows into
the vector store is wrapped in one of these.
"""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from simple_cli_coder_with_rag.domain.chunk import Chunk

_UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def test_chunk_id_is_uuid_v4() -> None:
    """``Chunk.id`` defaults to a freshly-generated UUIDv4 string."""
    chunk = Chunk(text="x", session_id="s", metadata={})

    assert isinstance(chunk.id, str)
    assert _UUID_V4_RE.match(chunk.id), f"not a UUIDv4: {chunk.id!r}"


def test_chunk_round_trip() -> None:
    """``model_dump_json`` round-trips back into an equal ``Chunk``."""
    chunk = Chunk(
        text="hello",
        session_id="sess-1",
        metadata={"source": "summary", "index": 0},
    )

    rebuilt = Chunk.model_validate_json(chunk.model_dump_json())

    assert rebuilt == chunk


def test_chunk_rejects_empty_text() -> None:
    """``text=""`` is rejected — an empty chunk would embed to nonsense space."""
    with pytest.raises(ValidationError):
        Chunk(text="", session_id="s", metadata={})


def test_chunk_unique_ids_by_default() -> None:
    """Two independently-constructed chunks get distinct UUIDv4 ids."""
    a = Chunk(text="a", session_id="s", metadata={})
    b = Chunk(text="b", session_id="s", metadata={})

    assert a.id != b.id


def test_chunk_accepts_empty_metadata() -> None:
    """``metadata`` defaults to an empty dict so callers don't have to pass one."""
    chunk = Chunk(text="x", session_id="s")

    assert chunk.metadata == {}
