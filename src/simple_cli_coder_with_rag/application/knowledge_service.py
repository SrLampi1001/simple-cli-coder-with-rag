"""Application-layer Facade for the LLM-powered chat loop and RAG hooks.

:class:`KnowledgeService` is the single seam between the REPL (presentation
layer) and the LLM-backed ``LLMClient`` Protocol (domain layer). It
exposes three operations:

* :meth:`KnowledgeService.chat` — plain chat turn (DO-03).
* :meth:`KnowledgeService.learn` — read the on-disk session, compact it
  via the compactor, chunk it via the Strategy-picked chunker, embed
  the chunks via the Strategy-picked embedder (DO-06), and persist them
  to the Strategy-picked vector store (DO-07). Returns the chunk count.
* :meth:`KnowledgeService.recall` — return relevant chunks via the
  injected ``Retriever`` (DO-08). Returns ``[]`` when no retriever is
  wired or when the retriever signals a transient failure (timeout,
  embedder still loading).

Architectural notes:

* This module imports from :mod:`domain` and from other ``application``
  modules (the compactor, the chunkers, and the session store). It does
  **not** import from :mod:`infrastructure` — no vendor SDKs and no
  ``Settings`` type. The composition root in
  :mod:`simple_cli_coder_with_rag.cli` resolves ``chat_model`` /
  ``compactor_model`` from ``Settings`` and passes the resolved strings
  into the constructor.
* ``LLMError`` is **not** caught here. The REPL catches it and prints a
  one-line message; any wrapping would only duplicate work and risk
  swallowing the wrong exception type.
* ``CompactionError`` is likewise propagated verbatim so the REPL sees a
  single failure type.
* Message persistence happens in the REPL (one ``session_store.append``
  per chat turn). ``learn`` therefore reads the full transcript from
  disk via :class:`SessionStore` — it does not need an in-memory
  message list to be passed in.
* ``embedder`` and ``vector_store`` are **optional**. When either is
  ``None`` (legacy wiring from DO-04-DO-06 that has not yet been
  upgraded to DO-07) the service still compacts and chunks, but skips
  the embed -> upsert stage. This keeps the DO-04 and DO-06 test
  suites passing without modification.
* ``retriever`` (DO-08) is also **optional**. When ``None``,
  :meth:`recall` short-circuits to ``[]`` — keeps the pre-DO-08 test
  suites passing without modification. When set, the composition root
  is responsible for wrapping the bare :class:`BaseRetriever` in the
  :class:`~simple_cli_coder_with_rag.infrastructure.retrievers.timeout_retriever.TimeoutRetriever`
  Decorator **before** injecting it here. That keeps the timeout
  deadline scoped to the single seam and prevents ``recall`` from
  needing its own timeout wrapper.
* :meth:`recall` catches the wider ``RuntimeError`` (not
  :class:`EmbedderNotReady` directly) so this module stays decoupled
  from the embedder module — same trick ``cli.py`` uses for
  :class:`VectorStoreBackendUnavailable`. The base retriever raises
  :class:`EmbedderNotReady`; that IS a ``RuntimeError`` per
  :mod:`domain.embedder`. The ``TimeoutRetriever`` returns ``[]`` on
  timeout instead of raising, so a timeout shows up as ``[]`` from the
  retriever — never a second ``RuntimeError`` here.
"""

from __future__ import annotations

from simple_cli_coder_with_rag.application.chunkers import (
    FixedSizeChunker,
    SemanticChunker,
)
from simple_cli_coder_with_rag.application.compactor import Compactor
from simple_cli_coder_with_rag.application.prompts import build_chat_messages
from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.domain.chunk import Chunk
from simple_cli_coder_with_rag.domain.chunker import Chunker
from simple_cli_coder_with_rag.domain.embedder import Embedder
from simple_cli_coder_with_rag.domain.llm_client import LLMClient
from simple_cli_coder_with_rag.domain.messages import Message
from simple_cli_coder_with_rag.domain.retriever import Retriever
from simple_cli_coder_with_rag.domain.vector_store import VectorStore


class KnowledgeService:
    """Facade exposing ``chat`` / ``learn`` / ``recall`` to the REPL."""

    def __init__(
        self,
        llm: LLMClient,
        chat_model: str,
        session_store: SessionStore,
        compactor: Compactor,
        chunker: Chunker,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
        retriever: Retriever | None = None,
    ) -> None:
        self._llm = llm
        self._chat_model = chat_model
        self._session_store = session_store
        self._compactor = compactor
        self._chunker = chunker
        self._embedder = embedder
        self._vector_store = vector_store
        self._retriever = retriever
        # Most recent ``chunk`` result, populated by ``learn``. ``[]``
        # before the first ``/learn``. DO-06 (embedder) and DO-07
        # (vector store) read this so they can embed and persist
        # exactly the chunks that ``learn`` produced.
        self.last_chunks: list[Chunk] = []

    def chat(self, user_message: str, history: list[Message]) -> str:
        """Send ``user_message`` (with prior ``history``) to the LLM and return the reply.

        ``LLMError`` propagates verbatim so the caller (the REPL) can decide
        how to surface it.
        """
        messages = build_chat_messages(user_message, history, recalled=[])
        return self._llm.complete(messages, model=self._chat_model)

    def learn(self, session_id: str) -> int:
        """Compact, chunk, embed, and persist the on-disk session for ``session_id``.

        Algorithm:

        1. Read the on-disk transcript (returns ``[]`` on a fresh
           session).
        2. Ask the compactor for a structured :class:`CompactedSession`.
           The compactor short-circuits on an empty list without
           contacting the LLM.
        3. Persist the compacted document via ``write_compacted`` (which
           overwrites any prior file — the second ``/learn`` replaces
           the first).
        4. Chunk the compacted document with the configured Strategy
           chunker. Store the result on :attr:`last_chunks`.
        5. **If** an embedder + vector store are configured, embed the
           chunks and upsert them in one batch. The embedder and store
           are wired together because they are the only place that
           knows the embedding dimensionality (``bge-small-en-v1.5`` is
           384-d by default; the embedder publishes the contract).
        6. Return ``len(chunks)`` so the caller (``LearnCommand``) can
           display the count.

        ``LLMError`` and :class:`~simple_cli_coder_with_rag.application.compactor.CompactionError`
        propagate verbatim.
        """
        all_messages = self._session_store.read(session_id)
        compacted = self._compactor.compact(session_id, all_messages)
        self._session_store.write_compacted(session_id, compacted)
        self.last_chunks = self._chunker.chunk(compacted)
        if self._embedder is not None and self._vector_store is not None:
            vectors = self._embedder.embed_passages([c.text for c in self.last_chunks])
            self._vector_store.upsert(self.last_chunks, vectors)
        return len(self.last_chunks)

    def recall(self, query: str, *, top_k: int = 3) -> list[str]:
        """Return up to ``top_k`` most relevant chunk texts for ``query``.

        Behaviour:

        * No retriever wired (``self._retriever is None``) → returns
          ``[]``. Keeps the pre-DO-08 test suites passing without
          modification.
        * Retriever raises ``RuntimeError`` (e.g. the embedder is still
          loading — :class:`EmbedderNotReady` is a ``RuntimeError``) →
          catches and returns ``[]``. The composition root wires the
          ``TimeoutRetriever`` Decorator outside this method, so a
          timeout surfaces as ``[]`` from the retriever instead of a
          second ``RuntimeError`` here.
        * Otherwise → returns ``[r.chunk.text for r in results]`` in
          retrieval order (vector store ranks by similarity descending).

        ``top_k`` defaults to ``3`` — a small enough window that the
        chat prompt stays under the LLM's context budget but large
        enough that "obvious" hits land inside the slice.
        """
        if self._retriever is None:
            return []
        try:
            results = self._retriever.retrieve(query, top_k=top_k)
        except RuntimeError:
            # EmbedderNotReady (the base retriever's own signal). The composition root
            # wires the TimeoutRetriever-wrapped retriever, so a timeout surfaces as
            # [] from the retriever — not a second timeout wrapper here.
            return []
        return [r.chunk.text for r in results]


def build_chunker(strategy: str) -> Chunker:
    """Resolve a chunker Strategy from ``strategy``.

    Pulled out of the composition root so unit tests can exercise the
    same selection logic without spinning up a Settings instance. New
    strategies are added by extending the ``if`` chain here.
    """
    if strategy == "semantic":
        return SemanticChunker()
    if strategy == "fixed":
        return FixedSizeChunker()
    raise ValueError(f"unknown chunker strategy: {strategy!r}")


__all__ = ["KnowledgeService", "build_chunker"]
