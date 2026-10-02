"""Default :class:`Retriever` Strategy: embed the query, then query the store.

``BaseRetriever`` is the **Strategy implementation** behind the
:class:`~simple_cli_coder_with_rag.domain.retriever.Retriever` Protocol.
It is the only retriever class that talks to the embedder and the
vector store directly — every other class in the retriever chain (the
timeout decorator, a future cached decorator) sits on top of this one.

Algorithm (per ``retrieve`` call):

1. **Gate on ``embedder.is_ready()``.** The local BGE model loads on a
   background thread (``docs/development-tools.md`` §5). Calling
   ``embed_query`` before the model is ready raises
   :class:`~simple_cli_coder_with_rag.domain.embedder.EmbedderNotReady`
   (a :class:`RuntimeError`), which this module **propagates verbatim**
   so the composition root can decide how to react. We do not sleep,
   poll, or block — the gate is the embedder's responsibility and the
   caller (``KnowledgeService.recall`` in DO-09) catches
   ``RuntimeError`` and degrades to ``[]``.
2. **Embed the query.** ``embedder.embed_query(query)`` returns a single
   ``list[float]``. We deliberately do NOT call ``embed_passages`` —
   that entry point is for stored chunks during ``/learn``; queries
   must carry the model's instruction prefix for BGE-family models.
3. **Query the store.** ``vector_store.query(vector, top_k=top_k)``
   returns ``list[tuple[Chunk, float]]`` sorted by cosine similarity
   descending per the ``VectorStore`` contract. We map each pair to a
   :class:`RetrievedChunk` preserving order — the store does the
   ranking, the retriever just decorates.

An alternative implementation (e.g. a hybrid BM25 + dense retriever, a
two-tower with reranker) would slot in alongside this one by satisfying
the same :class:`Retriever` Protocol and being selected at the
composition root in ``cli.py``. The shape of ``BaseRetriever`` is the
floor: any retriever worth its name needs the embed-then-query pair.

Architectural note: this module imports from :mod:`domain` only (no
infrastructure, no vendor SDKs). It is part of the application layer
and may be replaced at the composition root in ``cli.py``.
"""

from __future__ import annotations

from simple_cli_coder_with_rag.domain.chunk import Chunk
from simple_cli_coder_with_rag.domain.embedder import Embedder, EmbedderNotReady
from simple_cli_coder_with_rag.domain.retriever import RetrievedChunk
from simple_cli_coder_with_rag.domain.vector_store import VectorStore


class BaseRetriever:
    """Embed the query, then ask the vector store for the top-k matches.

    Parameters
    ----------
    embedder:
        The configured :class:`Embedder`. ``is_ready()`` is checked
        before every ``retrieve`` call so a still-loading model never
        reaches ``embed_query``.
    vector_store:
        The configured :class:`VectorStore`. ``query(vector, top_k=)``
        is expected to return chunks sorted by similarity descending.
    """

    def __init__(self, embedder: Embedder, vector_store: VectorStore) -> None:
        self._embedder = embedder
        self._vector_store = vector_store

    def retrieve(self, query: str, *, top_k: int) -> list[RetrievedChunk]:
        """Return up to ``top_k`` chunks relevant to ``query``.

        Raises :class:`EmbedderNotReady` (a :class:`RuntimeError`) when
        the embedder is still loading. The caller
        (``KnowledgeService.recall``) catches the wider
        :class:`RuntimeError` and degrades gracefully — it does not
        need to import this domain exception type.
        """
        if not self._embedder.is_ready():
            raise EmbedderNotReady("embedder is not ready")

        vector = self._embedder.embed_query(query)
        rows: list[tuple[Chunk, float]] = self._vector_store.query(vector, top_k=top_k)
        # ``VectorStore`` may return up to ``top_k`` rows; some
        # implementations return more (e.g. when they group by
        # ``session_id`` and de-duplicate after). Enforce the bound
        # here so the caller's contract ("length <= top_k") holds
        # regardless of the store.
        truncated = rows[:top_k]
        return [RetrievedChunk(chunk, similarity) for chunk, similarity in truncated]


__all__ = ["BaseRetriever"]
