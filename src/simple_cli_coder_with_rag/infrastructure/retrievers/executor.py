"""ThreadPoolExecutor wrapper scoped to retrieval work (DO-08)."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")


class RetrievalExecutor:
    """Run retriever calls on a background thread with bounded concurrency.

    The whole point of this wrapper is to be the **only** module in the
    project that imports :mod:`concurrent.futures`. Per
    ``docs/development-tools.md`` §9, ``max_workers=2`` is enough because
    the retriever only blocks while SQLite does vector similarity, which
    is a tiny query on a few-hundred-row table.

    **Scope.** This executor is for the retriever only — its timeout /
    cancellation policy is the one documented in
    :class:`~simple_cli_coder_with_rag.infrastructure.retrievers.timeout_retriever.TimeoutRetriever`.
    Future work that needs to overlap the LLM SDK call with retrieval must
    introduce a separate executor (e.g. ``LLMCallExecutor``) — never
    reuse this one. Mixing the two couples their cancellation and timeout
    policies and would defeat ``TimeoutRetriever``'s bounded-latency
    guarantee.
    """

    def __init__(self, *, max_workers: int = 2) -> None:
        if max_workers <= 0:
            raise ValueError(f"max_workers must be > 0, got {max_workers}")
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def submit(self, fn: Callable[..., T], /, *args: object, **kwargs: object) -> Future[T]:
        """Submit ``fn(*args, **kwargs)`` to the underlying executor."""
        return self._executor.submit(fn, *args, **kwargs)

    def shutdown(self) -> None:
        """Stop accepting tasks and cancel pending ones.

        Per ``docs/development-tools.md`` §9: ``wait=False`` so Ctrl-D
        does not hang waiting for in-flight retrieval; ``cancel_futures=True``
        so tasks queued but not yet started are dropped.
        """
        self._executor.shutdown(wait=False, cancel_futures=True)


__all__ = ["RetrievalExecutor"]
