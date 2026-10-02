"""``TimeoutRetriever`` — Decorator that bounds retrieval latency (DO-08).

The retriever is the third Decorator seam in the project
(``OBJECTIVES.md`` — "Retriever -> CachedRetriever -> TimeoutRetriever").
DO-08 ships only ``TimeoutRetriever``; ``CachedRetriever`` is deferred
per ``docs/development-tools.md`` §12 (user requests rarely repeat
verbatim, so hit rates are low; the real cost is the query embedding +
SQLite lookup, both already cheap). Adding the cache later is a
one-line change at the composition root.

Wrapping contract:

* ``TimeoutRetriever`` implements the same ``Retriever`` Protocol as the
  inner retriever. The composition root in :mod:`simple_cli_coder_with_rag.cli`
  wraps ``BaseRetriever`` in ``TimeoutRetriever`` before passing it to
  :class:`~simple_cli_coder_with_rag.application.knowledge_service.KnowledgeService`.

* On a timeout, returns ``[]`` and logs at DEBUG via :mod:`loguru`.
  Does **not** raise — the user's prompt never stalls.

* ``future.result(timeout=...)`` **stops waiting, it does not cancel**
  the running task (per ``docs/development-tools.md`` §9). The task keeps
  running on the worker thread until it naturally completes; we simply
  stop observing it. This is why ``RetrievalExecutor.shutdown`` calls
  ``cancel_futures=True`` on REPL exit — without that, an in-flight
  retrieval at Ctrl-D could prevent the worker from exiting promptly.
"""

from __future__ import annotations

from concurrent.futures import Future

from loguru import logger

from simple_cli_coder_with_rag.domain.retriever import RetrievedChunk, Retriever
from simple_cli_coder_with_rag.infrastructure.retrievers.executor import RetrievalExecutor


class TimeoutRetriever:
    """Wrap ``inner`` so that ``retrieve`` returns ``[]`` after ``timeout_seconds``.

    On a normal completion, returns the inner's results verbatim. On a
    timeout, logs at DEBUG and returns ``[]`` — the caller never sees a
    partial answer and never blocks past the deadline.
    """

    def __init__(
        self,
        inner: Retriever,
        *,
        timeout_seconds: float,
        executor: RetrievalExecutor,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be > 0, got {timeout_seconds}")
        self._inner = inner
        self._timeout_seconds = timeout_seconds
        self._executor = executor

    def retrieve(self, query: str, *, top_k: int) -> list[RetrievedChunk]:
        """Submit ``inner.retrieve`` to ``executor`` and wait up to ``timeout_seconds``."""
        future: Future[list[RetrievedChunk]] = self._executor.submit(
            self._inner.retrieve, query, top_k=top_k
        )
        try:
            return future.result(timeout=self._timeout_seconds)
        except TimeoutError:
            logger.debug(
                "retrieval timeout: inner did not complete within {}s (query length={})",
                self._timeout_seconds,
                len(query),
            )
            return []


__all__ = ["TimeoutRetriever"]
