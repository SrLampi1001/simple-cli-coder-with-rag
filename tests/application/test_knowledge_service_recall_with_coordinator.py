"""Tests for ``KnowledgeService.recall`` after DO-09 wires the coordinator.

Pinned by ``agent-development/09-recall-integration/tests.md``. Replaces
``test_knowledge_service_recall.py`` from DO-08 — the facade now
delegates to a :class:`RecallCoordinator` and exposes an optional
``top_k`` override.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from simple_cli_coder_with_rag.application.chunkers.fixed_size import FixedSizeChunker
from simple_cli_coder_with_rag.application.compactor import Compactor
from simple_cli_coder_with_rag.application.knowledge_service import KnowledgeService
from simple_cli_coder_with_rag.application.recall_coordinator import (
    RecallCoordinator,
)
from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.application.trivial_gate import TrivialGate

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _build_service_with_coordinator(
    tmp_path: Path, fake_llm: object, coordinator: RecallCoordinator
) -> KnowledgeService:
    """Build a ``KnowledgeService`` that delegates ``recall`` to ``coordinator``."""
    store = SessionStore(tmp_path)
    compactor = Compactor(llm=fake_llm, compactor_model="test")  # type: ignore[arg-type]
    return KnowledgeService(
        llm=fake_llm,  # type: ignore[arg-type]
        chat_model="m",
        session_store=store,
        compactor=compactor,
        chunker=FixedSizeChunker(),
        coordinator=coordinator,
    )


def test_recall_delegates_to_coordinator(tmp_path: Path, mocker: MockerFixture) -> None:
    """``KnowledgeService.recall`` returns whatever ``RecallCoordinator.recall`` returns."""
    fake_llm = mocker.MagicMock()
    coordinator = mocker.MagicMock(spec=RecallCoordinator)
    coordinator.recall.return_value = ["memory-1", "memory-2"]

    service = _build_service_with_coordinator(tmp_path, fake_llm, coordinator)

    assert service.recall("why does this fail") == ["memory-1", "memory-2"]
    coordinator.recall.assert_called_once()
    call = coordinator.recall.call_args
    assert call.args == ("why does this fail",)
    # ``top_k`` is forwarded to the coordinator (None → coordinator's default;
    # explicit override → override). We only assert the kwarg key exists here
    # — see ``test_recall_top_k_override`` for the override forwarding.
    assert "top_k" in call.kwargs


def test_recall_top_k_override(tmp_path: Path, mocker: MockerFixture) -> None:
    """``recall("q", top_k=7)`` forwards the override to the coordinator."""
    fake_llm = mocker.MagicMock()
    coordinator = mocker.MagicMock(spec=RecallCoordinator)
    coordinator.recall.return_value = []

    service = _build_service_with_coordinator(tmp_path, fake_llm, coordinator)

    service.recall("q", top_k=7)

    coordinator.recall.assert_called_once_with("q", top_k=7)


def test_recall_without_coordinator_returns_empty(tmp_path: Path) -> None:
    """When no coordinator is wired, ``recall`` returns ``[]`` (legacy / tests)."""
    fake_llm = MagicMock()
    store = SessionStore(tmp_path)
    compactor = Compactor(llm=fake_llm, compactor_model="m")
    service = KnowledgeService(
        llm=fake_llm,
        chat_model="m",
        session_store=store,
        compactor=compactor,
        chunker=FixedSizeChunker(),
    )

    assert service.recall("any") == []


def test_real_coordinator_with_real_trivial_gate(tmp_path: Path) -> None:
    """A real ``RecallCoordinator`` with a real ``TrivialGate`` short-circuits short prompts.

    Wires an empty retriever and asserts that ``recall("hi")`` returns
    ``[]`` without raising — the gate short-circuits before the retriever.
    """
    fake_llm = MagicMock()

    class _EmptyRetriever:
        def retrieve(self, query: str, *, top_k: int) -> list[object]:
            raise AssertionError("retriever must not be called for trivial prompts")

    coordinator = RecallCoordinator(
        retriever=_EmptyRetriever(),  # type: ignore[arg-type]
        gate=TrivialGate(),
        top_k=3,
        similarity_threshold=0.5,
    )
    service = _build_service_with_coordinator(tmp_path, fake_llm, coordinator)

    assert service.recall("hi") == []
