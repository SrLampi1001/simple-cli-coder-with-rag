"""Strategy implementations of the ``Retriever`` Protocol (DO-08).

This package holds the concrete retriever adapters the composition root
wires behind the :class:`~simple_cli_coder_with_rag.domain.retriever.Retriever`
Protocol. The first implementation shipped is :class:`BaseRetriever`,
which orchestrates :class:`Embedder.embed_query` and
:class:`VectorStore.query` — no other dependency. Future Strategies
(e.g. a cached variant behind the same seam) would land alongside it.

Decorator wrappers (``TimeoutRetriever``) live in
:mod:`simple_cli_coder_with_rag.infrastructure.retrievers` because they
depend on :class:`concurrent.futures.ThreadPoolExecutor`, which is the
composition root's concern. Composition order in the composition root is
``TimeoutRetriever(BaseRetriever(...))`` — the timeout sits on the
outside so its deadline covers both the embed call and the store query.

Architectural note: this package imports from :mod:`domain` only. The
implementation classes live in :mod:`application.retrievers` so the
layered-architecture contract (``pyproject.toml`` ``[tool.importlinter]``)
stays clean: ``application`` may depend on ``domain``, never the reverse.
"""

from simple_cli_coder_with_rag.application.retrievers.base_retriever import BaseRetriever

__all__ = ["BaseRetriever"]
