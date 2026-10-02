"""Tests for ``KnowledgeService.set_llm``."""

from __future__ import annotations

from pathlib import Path

from simple_cli_coder_with_rag.application.chunkers import FixedSizeChunker
from simple_cli_coder_with_rag.application.compactor import Compactor
from simple_cli_coder_with_rag.application.knowledge_service import KnowledgeService
from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.domain.messages import AssistantTurn


def _service(tmp_path: Path, llm: object) -> KnowledgeService:
    return KnowledgeService(
        llm=llm,  # type: ignore[arg-type]
        chat_model="m",
        session_store=SessionStore(root=tmp_path / "sessions"),
        compactor=Compactor(llm=llm, compactor_model="m"),  # type: ignore[arg-type]
        chunker=FixedSizeChunker(),
    )


def test_knowledge_service_set_llm_swaps_adapter(tmp_path: Path, mocker) -> None:
    old = mocker.MagicMock()
    old.complete_with_tools.return_value = AssistantTurn(content="old", tool_calls=[])
    new = mocker.MagicMock()
    new.complete_with_tools.return_value = AssistantTurn(content="new", tool_calls=[])

    service = _service(tmp_path, old)
    service.set_llm(new)

    assert service.chat("hi", history=[], recalled=[]) == "new"
    new.complete_with_tools.assert_called()
    old.complete_with_tools.assert_not_called()


def test_knowledge_service_set_llm_preserves_other_dependencies(tmp_path: Path, mocker) -> None:
    old = mocker.MagicMock()
    old.complete_with_tools.return_value = AssistantTurn(content="old", tool_calls=[])
    service = _service(tmp_path, old)
    chunker = service._chunker
    session_store = service._session_store
    compactor = service._compactor

    service.set_llm(mocker.MagicMock())

    assert service._chunker is chunker
    assert service._session_store is session_store
    assert service._compactor is compactor
    assert service._embedder is None
    assert service._vector_store is None
    assert service._coordinator is None
    assert service._editor is None
