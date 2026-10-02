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

DO-13 added two top-level fields that complement ``metadata``:

* ``source`` — the canonical, **file-level** origin of the chunk. For
  session-compacted chunks (DO-04) it stays empty (``""``); for
  document chunks (``/learn <path>``, DO-13) it is the absolute path
  of the ingested file. The chat-time system prompt uses it to
  format citations (``[Source: docs/foo.md, chunk #2]``) and the
  future Supabase adapter uses it as a dedup key.
* ``chunk_index`` — the zero-based position of the chunk within its
  ``source``. Together with ``source`` it forms the natural primary
  key for the document chunk table (the
  ``ON CONFLICT (source, chunk_index) DO UPDATE`` clause in
  ``supabase_schema.sql``). It defaults to ``0`` so existing
  session-compacted chunks round-trip unchanged.

The chunker Strategy implementations (``FixedSizeChunker``,
``SemanticChunker``) are responsible for setting ``metadata`` and
``session_id`` correctly; the embedder and the store must not have to
guess them. The :class:`DocumentMetadata`-aware code path
(``/learn <path>``) is responsible for setting ``source`` and
``chunk_index``.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    """A single retrievable unit of a compacted session or loaded document.

    Mutable (``frozen=False``) because tests introspect and rewrite
    fields, but production code treats it as effectively immutable
    after construction.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    session_id: str
    # DO-13 additions. Default values keep the pre-DO-13 call sites
    # (``FixedSizeChunker.chunk(compacted)``,
    # ``SemanticChunker.chunk(compacted)``) round-tripping without
    # change — the compactor path produces session-level chunks with
    # no file-level source.
    source: str = ""
    chunk_index: int = 0


__all__ = ["Chunk"]
