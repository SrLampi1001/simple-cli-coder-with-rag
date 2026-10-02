"""Strategy interface for the retriever.

The retriever is the **fifth Strategy seam** in the RAG pipeline
(``OBJECTIVES.md`` — "the retriever (Strategy + Decorator)"). It sits
on top of the embedder (DO-06) and the vector store (DO-07) and is the
only layer that turns a raw user prompt into a ranked list of memory
chunks.

The shape is intentionally narrow:

* :class:`RetrievedChunk` pairs the underlying :class:`Chunk` with the
  cosine-similarity score the vector store assigned it. The score is
  exposed because DO-09's chat-prompt builder wants it for citation
  ("this came back with similarity 0.83") and because the
  ``TimeoutRetriever`` Decorator (DO-08) and any future
  ``CachedRetriever`` (deferred per ``docs/development-tools.md`` §12)
  pass it through verbatim.
* :class:`Retriever` declares a single ``retrieve(query, *, top_k)``
  method. Implementations may reach for the embedder + vector store
  (``BaseRetriever``), wrap another ``Retriever`` with a timeout
  (``TimeoutRetriever`` in DO-08), or — later — add a cache in front.
  All of them satisfy the same Protocol, so the composition root in
  ``cli.py`` wires them as one chain.

``Retriever`` is :func:`@runtime_checkable <typing.runtime_checkable>`
because the base retriever and the timeout decorator are developed
in parallel by separate subagents and the contract is verified with
``isinstance(obj, Retriever)`` in both unit tests and the composition
root's wiring sanity check.

Architectural note: this module imports from :mod:`domain` only. It
does not import from :mod:`infrastructure` or from vendor SDKs.
``import-linter`` enforces this on the ``layered-architecture``
contract.
"""

from __future__ import annotations

from typing import NamedTuple, Protocol, runtime_checkable

from simple_cli_coder_with_rag.domain.chunk import Chunk


class RetrievedChunk(NamedTuple):
    """A chunk paired with the cosine-similarity score the store assigned it.

    The tuple form is deliberate — callers unpack with
    ``chunk, similarity = retrieved`` (mirrored in
    ``tests/domain/test_retriever.py``) and the type is value-equal to a
    plain ``tuple[Chunk, float]`` for downstream ``list`` operations
    (``len``, ``sorted``, ``zip``, …) without any Pydantic overhead.

    Attributes
    ----------
    chunk:
        The matched :class:`Chunk`. Its ``metadata`` and ``session_id``
        are preserved untouched — the retriever does not annotate or
        rewrite.
    similarity:
        Cosine similarity in ``[-1.0, 1.0]``; larger is better.
        Implementations of :class:`VectorStore` are responsible for
        returning this score, not the underlying distance.
    """

    chunk: Chunk
    similarity: float


@runtime_checkable
class Retriever(Protocol):
    """Strategy interface for turning a user prompt into ranked memory chunks."""

    def retrieve(self, query: str, *, top_k: int) -> list[RetrievedChunk]:
        """Return up to ``top_k`` chunks relevant to ``query``, sorted by similarity descending.

        Implementations may compose — :class:`BaseRetriever` is the
        default, :class:`TimeoutRetriever` wraps it with a deadline,
        future wrappers (e.g. a cached retriever) stack on the same
        seam. Every layer must honour the contract: ``top_k`` is an
        upper bound, results are sorted by ``similarity`` descending,
        and an empty input or empty store returns ``[]`` (never raises
        for the "nothing found" case).

        Implementations MAY raise :class:`RuntimeError` for transient
        failures (e.g. the embedder is still loading — the base
        retriever surfaces :class:`EmbedderNotReady`, a
        ``RuntimeError``). Higher layers (``KnowledgeService.recall``)
        catch ``RuntimeError`` and degrade to ``[]``; they do not need
        to import any specific exception type from this module.
        """
        ...


__all__ = ["RetrievedChunk", "Retriever"]
