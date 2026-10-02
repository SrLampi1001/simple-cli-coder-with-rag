"""Pydantic model for the chunks the RAG pipeline embeds and stores.

A ``Chunk`` is the unit the embedder (DO-06) and the vector store (DO-07)
operate on. The schema is intentionally narrow:

* ``id`` is a UUIDv4 so the vector store can upsert by id and so two
  chunks produced by different strategies can never collide.
* ``text`` is the surface that gets embedded. It must be non-empty — an
  empty string would embed to a zero/nonsense vector.
* ``metadata`` carries the **provenance** the retriever uses to explain
  hits ("this came from the summary", "this came from error #2"). It is
  also where the vector store stores filters (``session_id``, ``source``,
  ``index``) when the schema demands it.
* ``session_id`` is repeated as a top-level field (rather than buried
  in ``metadata``) because every chunk we ever produce belongs to one
  session, and the retriever + vector store filter by it constantly.

The chunker Strategy implementations (``FixedSizeChunker``,
``SemanticChunker``) are responsible for setting ``metadata`` and
``session_id`` correctly; the embedder and the store must not have to
guess them.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    """A single retrievable unit of a compacted session.

    Mutable (``frozen=False``) because tests introspect and rewrite
    fields, but production code treats it as effectively immutable
    after construction.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    session_id: str


__all__ = ["Chunk"]
