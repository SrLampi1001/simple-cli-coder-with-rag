"""Replaces the stub learn test from DO-03. Uses real ``SessionStore`` with
``tmp_path`` and real ``Compactor`` with mocked LLM. Pinned by
``agent-development/04-learn-compaction/tests.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from simple_cli_coder_with_rag.application.compactor import Compactor
from simple_cli_coder_with_rag.application.knowledge_service import KnowledgeService
from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.domain.compacted import CompactedSession
from simple_cli_coder_with_rag.domain.llm_client import LLMError
from simple_cli_coder_with_rag.domain.messages import (
    AssistantMessage,
    UserMessage,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _valid_json() -> str:
    """Return a JSON string that the compactor will accept.

    ``session_id`` / ``created_at`` are placeholders the compactor overrides.
    """
    return (
        '{"session_id": "llm-supplied",'
        ' "created_at": "2026-10-01T00:00:00Z",'
        ' "summary": "compacted",'
        ' "errors": [],'
        ' "decisions": []}'
    )


def _build_service(
    tmp_path: Path,
    fake_llm: object,
) -> tuple[KnowledgeService, SessionStore]:
    """Build a ``KnowledgeService`` wired to a real ``SessionStore`` and ``Compactor``."""
    store = SessionStore(tmp_path)
    compactor = Compactor(llm=fake_llm, compactor_model="test")  # type: ignore[arg-type]
    service = KnowledgeService(
        llm=fake_llm,  # type: ignore[arg-type]
        chat_model="chat-model",
        session_store=store,
        compactor=compactor,
    )
    return service, store


def test_learn_appends_messages_and_writes_compacted(tmp_path: Path, mocker: MockerFixture) -> None:
    """``learn`` appends the supplied messages and writes a compacted JSON file."""
    fake_llm = mocker.MagicMock()
    fake_llm.complete.return_value = _valid_json()

    service, _store = _build_service(tmp_path, fake_llm)

    session_id = "session-abc"
    messages = [UserMessage(content="a"), AssistantMessage(content="b")]
    service.learn(session_id, messages)

    target = tmp_path / f"{session_id}.compacted.json"
    assert target.exists()
    parsed = CompactedSession.model_validate_json(target.read_text("utf-8"))
    assert parsed.session_id == session_id
    assert parsed.summary == "compacted"


def test_learn_is_idempotent(tmp_path: Path, mocker: MockerFixture) -> None:
    """Two ``learn`` calls on the same id produce one compacted file and no duplicate appends."""
    fake_llm = mocker.MagicMock()
    fake_llm.complete.return_value = _valid_json()

    service, store = _build_service(tmp_path, fake_llm)

    session_id = "session-idem"
    messages = [UserMessage(content="a"), AssistantMessage(content="b")]

    service.learn(session_id, messages)
    after_first = len(store.read(session_id))
    assert after_first == len(messages)

    service.learn(session_id, messages)
    after_second = len(store.read(session_id))

    # No duplication — the second call must not re-append the same messages.
    assert after_second == after_first

    compacted_files = list(tmp_path.glob(f"{session_id}.compacted.json"))
    assert len(compacted_files) == 1


def test_learn_with_empty_session_writes_empty_compacted(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """``learn`` on a fresh session writes ``(empty session)`` without calling the LLM."""
    fake_llm = mocker.MagicMock()

    service, _store = _build_service(tmp_path, fake_llm)

    session_id = "session-empty"
    service.learn(session_id, [])

    target = tmp_path / f"{session_id}.compacted.json"
    assert target.exists()
    parsed = CompactedSession.model_validate_json(target.read_text("utf-8"))
    assert parsed.summary == "(empty session)"
    assert parsed.errors == []
    assert parsed.decisions == []
    fake_llm.complete.assert_not_called()


def test_learn_propagates_llm_error(tmp_path: Path, mocker: MockerFixture) -> None:
    """When ``LLMClient.complete`` raises ``LLMError``, ``learn`` re-raises verbatim."""
    fake_llm = mocker.MagicMock()
    fake_llm.complete.side_effect = LLMError("boom")

    service, _store = _build_service(tmp_path, fake_llm)

    with pytest.raises(LLMError, match="boom"):
        service.learn("session-boom", [UserMessage(content="hi")])
