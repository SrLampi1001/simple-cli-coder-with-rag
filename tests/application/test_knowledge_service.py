"""Tests for the ``KnowledgeService`` facade.

Pinned by ``agent-development/03-agent-responds-baseline/tests.md``. The
``LLMClient`` is mocked via :mod:`pytest_mock`; the tests never hit the
network and never read ``.env``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from simple_cli_coder_with_rag.application.chunkers.fixed_size import FixedSizeChunker
from simple_cli_coder_with_rag.application.compactor import Compactor
from simple_cli_coder_with_rag.application.knowledge_service import KnowledgeService
from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.domain.llm_client import LLMClient, LLMError
from simple_cli_coder_with_rag.domain.messages import UserMessage

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _make_service(
    tmp_path: Path, fake_llm: LLMClient, *, chat_model: str = "m"
) -> KnowledgeService:
    """Build a ``KnowledgeService`` wired to throwaway session-store / compactor.

    The chat-path tests only exercise ``KnowledgeService.chat``; the compactor
    and the session store are real but never invoked, so a single ``fake_llm``
    shared between them is safe. ``FixedSizeChunker`` is the default Strategy
    picked by the composition root.
    """
    store = SessionStore(tmp_path)
    compactor = Compactor(llm=fake_llm, compactor_model="m")
    return KnowledgeService(
        llm=fake_llm,
        chat_model=chat_model,
        session_store=store,
        compactor=compactor,
        chunker=FixedSizeChunker(),
    )


def test_chat_calls_llm_with_messages(tmp_path: Path, mocker: MockerFixture) -> None:
    """``chat`` passes a message list ending with the user's turn to ``complete``."""
    fake_llm = mocker.MagicMock()
    fake_llm.complete.return_value = "hello back"

    service = _make_service(tmp_path, fake_llm, chat_model="chat-model")
    service.chat("hi", history=[])

    fake_llm.complete.assert_called_once()
    call = fake_llm.complete.call_args
    sent_messages = call.args[0]
    assert sent_messages == [UserMessage(content="hi")]
    assert call.kwargs["model"] == "chat-model"


def test_chat_returns_llm_string(tmp_path: Path, mocker: MockerFixture) -> None:
    """``chat`` returns exactly what ``LLMClient.complete`` returns."""
    fake_llm = mocker.MagicMock()
    fake_llm.complete.return_value = "the reply"

    service = _make_service(tmp_path, fake_llm)
    result = service.chat("hi", history=[])

    assert result == "the reply"


def test_chat_uses_chat_model_from_settings(tmp_path: Path, mocker: MockerFixture) -> None:
    """The ``model`` kwarg forwarded to ``complete`` matches ``Settings.chat_model``."""
    from pydantic import SecretStr

    from simple_cli_coder_with_rag.infrastructure.settings import Settings

    settings = Settings(
        default_provider="nvidia",  # type: ignore[arg-type]
        nvidia_api_key=SecretStr("nv"),
        chat_model="settings-chat-model",
    )

    fake_llm = mocker.MagicMock()
    fake_llm.complete.return_value = "ok"

    service = _make_service(tmp_path, fake_llm, chat_model=settings.chat_model)
    service.chat("hi", history=[])

    assert fake_llm.complete.call_args.kwargs["model"] == "settings-chat-model"


def test_recall_returns_empty_list(tmp_path: Path, mocker: MockerFixture) -> None:
    """``recall`` returns ``[]`` until DO-09 implements it."""
    fake_llm = mocker.MagicMock()
    service = _make_service(tmp_path, fake_llm)

    assert service.recall("any") == []


def test_llm_error_is_re_raised_verbatim(tmp_path: Path, mocker: MockerFixture) -> None:
    """When ``LLMClient.complete`` raises ``LLMError``, ``chat`` re-raises verbatim."""
    fake_llm = mocker.MagicMock()
    fake_llm.complete.side_effect = LLMError("boom")

    service = _make_service(tmp_path, fake_llm)

    with pytest.raises(LLMError, match="boom"):
        service.chat("hi", history=[])
