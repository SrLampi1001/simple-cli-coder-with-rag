"""Tests for the ``TimeoutRetriever`` Decorator.

Pinned by ``agent-development/08-retriever-with-decorator/tests.md``.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest

from simple_cli_coder_with_rag.domain.chunk import Chunk
from simple_cli_coder_with_rag.domain.retriever import RetrievedChunk
from simple_cli_coder_with_rag.infrastructure.retrievers.executor import RetrievalExecutor
from simple_cli_coder_with_rag.infrastructure.retrievers.timeout_retriever import TimeoutRetriever

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class _Inner:
    """Controllable fake inner retriever.

    ``result`` is the value to return on success. ``block_secs`` is the
    number of seconds to sleep before returning. ``calls`` records the
    invocation count so tests can verify the inner was invoked.
    """

    def __init__(
        self,
        result: list[RetrievedChunk] | None = None,
        *,
        block_secs: float = 0.0,
    ) -> None:
        self._result = result or []
        self._block_secs = block_secs
        self.calls: list[tuple[str, int]] = []

    def retrieve(self, query: str, *, top_k: int) -> list[RetrievedChunk]:
        self.calls.append((query, top_k))
        if self._block_secs > 0:
            time.sleep(self._block_secs)
        return self._result


def _make_retriever(inner: _Inner, *, timeout: float) -> tuple[TimeoutRetriever, RetrievalExecutor]:
    executor = RetrievalExecutor(max_workers=2)
    return (
        TimeoutRetriever(inner=inner, timeout_seconds=timeout, executor=executor),  # type: ignore[arg-type]
        executor,
    )


def test_inner_completes_returns_its_results() -> None:
    """Inner returns within deadline: ``TimeoutRetriever`` passes results verbatim."""
    c1 = Chunk(text="a", session_id="s")
    c2 = Chunk(text="b", session_id="s")
    inner = _Inner(result=[RetrievedChunk(c1, 0.9), RetrievedChunk(c2, 0.5)])
    retriever, executor = _make_retriever(inner, timeout=1.0)
    try:
        results = retriever.retrieve("q", top_k=3)
        assert results == [RetrievedChunk(c1, 0.9), RetrievedChunk(c2, 0.5)]
        assert inner.calls == [("q", 3)]
    finally:
        executor.shutdown()


def test_inner_times_out_returns_empty() -> None:
    """Inner blocks 1 s with timeout 0.05: call returns within ~100 ms with ``[]``."""
    inner = _Inner(result=[], block_secs=1.0)
    retriever, executor = _make_retriever(inner, timeout=0.05)
    try:
        start = time.perf_counter()
        results = retriever.retrieve("q", top_k=3)
        elapsed = time.perf_counter() - start

        assert results == []
        # 100 ms slack for slow CI scheduling.
        assert elapsed < 0.1, f"timeout decorator blocked for {elapsed * 1000:.1f} ms"
    finally:
        executor.shutdown()


def test_timeout_logs_at_debug(mocker: MockerFixture) -> None:
    """When the timeout fires, loguru's ``logger.debug`` is called."""
    import simple_cli_coder_with_rag.infrastructure.retrievers.timeout_retriever as mod

    fake_debug = mocker.patch.object(mod, "logger", create=True)
    # ``logger.debug`` is the attribute we'll assert on, but ``logger`` is the
    # patched MagicMock; reading ``.debug`` gives us its sub-mock.

    inner = _Inner(result=[], block_secs=1.0)
    retriever, executor = _make_retriever(inner, timeout=0.05)
    try:
        retriever.retrieve("q", top_k=3)
    finally:
        executor.shutdown()

    fake_debug.debug.assert_called()
    # The first positional arg of debug() is the message; it should mention
    # timeout. Extract it from call_args.
    call = fake_debug.debug.call_args
    fmt = call.args[0]
    assert "timeout" in fmt.lower(), f"debug message must mention timeout: {fmt!r}"


def test_timeout_does_not_cancel_running_task_but_does_not_wait() -> None:
    """``future.result(timeout=...)`` stops waiting but does not cancel the work.

    Even when the call returns within the deadline, the executor may still
    have a pending future. The shutdown at the end of the test (with
    ``cancel_futures=True``) ensures we don't leak the worker.
    """
    inner = _Inner(result=[], block_secs=5.0)
    retriever, executor = _make_retriever(inner, timeout=0.05)
    try:
        start = time.perf_counter()
        results = retriever.retrieve("q", top_k=3)
        elapsed = time.perf_counter() - start

        assert results == []
        assert elapsed < 0.1, (
            f"TimeoutRetriever must not block on inner: took {elapsed * 1000:.1f} ms"
        )
    finally:
        # ``cancel_futures=True`` on shutdown will drop the still-running
        # future; the daemon worker eventually drains it.
        executor.shutdown()


def test_timeout_retriever_rejects_non_positive_timeout() -> None:
    """``timeout_seconds <= 0`` is rejected — zero would mean "always timeout"."""
    inner = _Inner()
    executor = RetrievalExecutor(max_workers=1)
    try:
        with pytest.raises(ValueError, match="timeout_seconds"):
            TimeoutRetriever(inner=inner, timeout_seconds=0.0, executor=executor)  # type: ignore[arg-type]
    finally:
        executor.shutdown()
