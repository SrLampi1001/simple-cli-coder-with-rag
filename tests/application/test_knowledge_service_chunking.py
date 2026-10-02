"""Chunking integration tests for ``KnowledgeService``.

Pinned by ``agent-development/05-chunker-strategy/tests.md``.

The chunker is the real ``FixedSizeChunker`` (Strategy default). The compactor
is mocked so the LLM is never called. The assertions verify:

* ``KnowledgeService.learn`` returns an ``int`` chunk count.
* ``LearnCommand`` displays that count in its ``"learned N chunks"`` message.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from simple_cli_coder_with_rag import __version__
from simple_cli_coder_with_rag.application.chunkers.fixed_size import FixedSizeChunker
from simple_cli_coder_with_rag.application.compactor import Compactor
from simple_cli_coder_with_rag.application.knowledge_service import KnowledgeService
from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.domain.messages import (
    AssistantMessage,
    UserMessage,
)
from simple_cli_coder_with_rag.presentation.commands import (
    AppState,
    CommandContext,
)
from simple_cli_coder_with_rag.presentation.commands.learn import LearnCommand

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _compacted_json(summary: str = "compacted") -> str:
    """Return a JSON document the mocked ``Compactor`` will accept."""
    return json.dumps(
        {
            "session_id": "stub",
            "created_at": "2026-10-01T00:00:00Z",
            "summary": summary,
            "errors": [],
            "decisions": [],
        }
    )


def _build_service(
    tmp_path: Path, fake_llm: object, *, chunker: object | None = None
) -> tuple[KnowledgeService, SessionStore]:
    """Build a ``KnowledgeService`` wired to throwaway stores and a fake LLM.

    The chunker is ``FixedSizeChunker`` by default (the Strategy default),
    matching the composition root's behaviour.
    """
    store = SessionStore(tmp_path)
    compactor = Compactor(llm=fake_llm, compactor_model="test")  # type: ignore[arg-type]
    chunker = chunker or FixedSizeChunker()
    service = KnowledgeService(
        llm=fake_llm,  # type: ignore[arg-type]
        chat_model="chat-model",
        session_store=store,
        compactor=compactor,
        chunker=chunker,  # type: ignore[arg-type]
    )
    return service, store


def test_learn_returns_chunk_count(tmp_path: Path, mocker: MockerFixture) -> None:
    """``learn(session_id)`` returns an ``int`` chunk count, not ``None``."""
    fake_llm = mocker.MagicMock()
    fake_llm.complete.return_value = _compacted_json("a real summary")

    service, store = _build_service(tmp_path, fake_llm)

    # Pre-populate the on-disk transcript so ``learn`` only compacts / chunks.
    session_id = "sess-count"
    store.append(session_id, UserMessage(content="hi"))
    store.append(session_id, AssistantMessage(content="hello"))

    count = service.learn(session_id)

    assert isinstance(count, int)
    assert count >= 1


def test_learn_command_message_includes_count(mocker: MockerFixture) -> None:
    """``LearnCommand.execute`` returns ``"learned N chunks"`` with a real count."""
    knowledge = mocker.MagicMock()
    knowledge.learn.return_value = 7

    app_state = AppState(
        version=__version__,
        knowledge=knowledge,  # type: ignore[arg-type]
        session_id="sid",
        history=[UserMessage(content="a"), AssistantMessage(content="b")],
    )

    @dataclass
    class _StubRepl:
        def request_exit(self) -> None:
            pass

    ctx = CommandContext(repl=_StubRepl(), app_state=app_state)
    result = LearnCommand().execute(ctx)

    assert result.action == "continue"
    assert result.message == "learned 7 chunks"
    knowledge.learn.assert_called_once_with("sid")


@dataclass
class _StubRepl:
    """Minimal stand-in for ``Repl`` — only ``request_exit`` is invoked by commands."""

    request_exit_calls: int = 0

    def request_exit(self) -> None:
        self.request_exit_calls += 1


def test_learn_command_passes_only_session_id(mocker: MockerFixture) -> None:
    """``LearnCommand`` calls ``knowledge.learn(session_id)`` with one positional arg."""
    knowledge = mocker.MagicMock()
    knowledge.learn.return_value = 3

    app_state = AppState(
        version=__version__,
        knowledge=knowledge,  # type: ignore[arg-type]
        session_id="only-session",
        history=[UserMessage(content="x")],
    )

    ctx = CommandContext(repl=_StubRepl(), app_state=app_state)
    LearnCommand().execute(ctx)

    knowledge.learn.assert_called_once_with("only-session")
