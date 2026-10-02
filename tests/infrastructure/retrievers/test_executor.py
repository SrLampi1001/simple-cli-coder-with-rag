"""Tests for the ``RetrievalExecutor`` wrapper.

Pinned by ``agent-development/08-retriever-with-decorator/tests.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from simple_cli_coder_with_rag.infrastructure.retrievers.executor import RetrievalExecutor

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_executor_default_two_workers(mocker: MockerFixture) -> None:
    """The default ``max_workers`` is ``2`` (per docs/development-tools.md §9)."""
    fake_cls = mocker.patch(
        "simple_cli_coder_with_rag.infrastructure.retrievers.executor.ThreadPoolExecutor"
    )

    RetrievalExecutor()

    assert fake_cls.call_args.kwargs["max_workers"] == 2


def test_executor_respects_max_workers_kwarg(mocker: MockerFixture) -> None:
    """``max_workers`` is forwarded to the underlying ThreadPoolExecutor."""
    fake_cls = mocker.patch(
        "simple_cli_coder_with_rag.infrastructure.retrievers.executor.ThreadPoolExecutor"
    )

    RetrievalExecutor(max_workers=4)

    assert fake_cls.call_args.kwargs["max_workers"] == 4


def test_executor_rejects_non_positive_max_workers() -> None:
    """``max_workers <= 0`` is rejected — no workers means no work."""
    with pytest.raises(ValueError, match="max_workers"):
        RetrievalExecutor(max_workers=0)
    with pytest.raises(ValueError, match="max_workers"):
        RetrievalExecutor(max_workers=-1)


def test_executor_submit_returns_future() -> None:
    """``submit`` returns the underlying future and runs the function."""
    executor = RetrievalExecutor(max_workers=1)
    try:
        future = executor.submit(lambda x: x + 1, 1)
        assert future.result(timeout=2) == 2
    finally:
        executor.shutdown()


def test_executor_shutdown_calls_with_cancel_futures_true(mocker: MockerFixture) -> None:
    """``shutdown`` forwards ``wait=False, cancel_futures=True`` to ThreadPoolExecutor."""
    fake_executor = mocker.MagicMock()
    mocker.patch(
        "simple_cli_coder_with_rag.infrastructure.retrievers.executor.ThreadPoolExecutor",
        return_value=fake_executor,
    )

    executor = RetrievalExecutor()
    executor.shutdown()

    fake_executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
