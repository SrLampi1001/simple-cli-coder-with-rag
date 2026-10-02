"""Tests for the ``/vector-store`` command (DO-13).

Pinned by ``agent-development/13-rag-over-documents-supabase/tests.md``.

The command prints the active backend with no args, swaps the
backend with a valid arg, and returns a friendly forthcoming
message for ``supabase`` (the DO-13 follow-up). The unknown-name
path is also friendly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from simple_cli_coder_with_rag import __version__
from simple_cli_coder_with_rag.domain.vector_store import (
    VectorStore,
)
from simple_cli_coder_with_rag.infrastructure.settings import Settings
from simple_cli_coder_with_rag.infrastructure.vector_stores import (
    NumpyBruteForceStore,
    SqliteVecStore,
)
from simple_cli_coder_with_rag.presentation.commands import (
    AppState,
    CommandContext,
)
from simple_cli_coder_with_rag.presentation.commands.vector_store import (
    VectorStoreCommand,
)
from simple_cli_coder_with_rag.presentation.repl import Repl

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from simple_cli_coder_with_rag.presentation.registry import CommandRegistry


def _app_state(
    *,
    knowledge: object | None = None,
    embedder: object | None = None,
    settings: Settings | None = None,
    active_vector_store: str = "sqlite_vec",
    vector_store: VectorStore | None = None,
) -> AppState:
    """Build an ``AppState`` carrying the configured pieces."""
    return AppState(
        version=__version__,
        knowledge=knowledge,
        history=[],
        embedder=embedder,  # type: ignore[arg-type]
        settings=settings,
        active_vector_store=active_vector_store,
        vector_store=vector_store,
    )


def _make_knowledge(
    coordinator: object | None = None,
) -> object:
    """Build a MagicMock ``KnowledgeService`` with a coordinator."""
    knowledge = MagicMock()
    knowledge._coordinator = coordinator
    return knowledge


def test_vector_store_no_args_prints_table(
    fresh_registry: CommandRegistry,
) -> None:
    """``/vector-store`` (no args) prints the active backend + available list."""
    state = _app_state(active_vector_store="sqlite_vec")
    fresh_registry.register(VectorStoreCommand())

    result = VectorStoreCommand().execute(
        CommandContext(
            repl=Repl(registry=fresh_registry, app_state=state),
            app_state=state,
            args="",
        )
    )

    assert result.message is not None
    assert "active vector store: sqlite_vec" in result.message
    assert "sqlite_vec" in result.message
    assert "brute_force" in result.message


def test_vector_store_supabase_returns_forthcoming(
    fresh_registry: CommandRegistry,
) -> None:
    """``/vector-store supabase`` returns the forthcoming-supabase message (no crash)."""
    state = _app_state()
    fresh_registry.register(VectorStoreCommand())

    result = VectorStoreCommand().execute(
        CommandContext(
            repl=Repl(registry=fresh_registry, app_state=state),
            app_state=state,
            args="supabase",
        )
    )

    assert result.message is not None
    assert "Supabase" in result.message
    assert "not" in result.message.lower()


def test_vector_store_unknown_returns_friendly(
    fresh_registry: CommandRegistry,
) -> None:
    """An unrecognised backend returns a friendly message; no exception."""
    state = _app_state()
    fresh_registry.register(VectorStoreCommand())

    result = VectorStoreCommand().execute(
        CommandContext(
            repl=Repl(registry=fresh_registry, app_state=state),
            app_state=state,
            args="bogus",
        )
    )

    assert result.message is not None
    assert "unknown vector store 'bogus'" in result.message
    assert "Available:" in result.message


def test_vector_store_sqlite_rebuilds_chain(
    fresh_registry: CommandRegistry,
    mocker: MockerFixture,
    tmp_path: __import__("pathlib").Path,
) -> None:
    """``/vector-store sqlite_vec`` rebuilds the chain and updates the active field."""
    from simple_cli_coder_with_rag.application.recall_coordinator import (
        RecallCoordinator,
    )
    from simple_cli_coder_with_rag.application.retrievers.base_retriever import (
        BaseRetriever,
    )
    from simple_cli_coder_with_rag.application.trivial_gate import TrivialGate
    from simple_cli_coder_with_rag.domain.embedder import Embedder
    from simple_cli_coder_with_rag.domain.retriever import Retriever
    from simple_cli_coder_with_rag.infrastructure.retrievers.executor import (
        RetrievalExecutor,
    )
    from simple_cli_coder_with_rag.infrastructure.retrievers.timeout_retriever import (
        TimeoutRetriever,
    )

    embedder = MagicMock(spec=Embedder)
    embedder.is_ready.return_value = True
    coordinator = RecallCoordinator(
        retriever=BaseRetriever(embedder=embedder, vector_store=MagicMock(spec=VectorStore)),
        gate=TrivialGate(),
        top_k=3,
        similarity_threshold=0.5,
    )
    knowledge = _make_knowledge(coordinator)
    settings = Settings(
        vector_store="brute_force",
        db_path=tmp_path / "db.sqlite",
    )
    state = _app_state(
        knowledge=knowledge,
        embedder=embedder,
        settings=settings,
        active_vector_store="brute_force",
    )
    fresh_registry.register(VectorStoreCommand())

    # Stub the executor's setup so the test does not start a real thread pool.
    mocker.patch.object(RetrievalExecutor, "submit", return_value=MagicMock())

    result = VectorStoreCommand().execute(
        CommandContext(
            repl=Repl(registry=fresh_registry, app_state=state),
            app_state=state,
            args="sqlite_vec",
        )
    )

    assert result.message is not None
    assert "active vector store: sqlite_vec" in result.message
    # The active field was updated on the AppState.
    assert state.active_vector_store == "sqlite_vec"
    # ``set_vector_store`` was called on the knowledge service.
    knowledge.set_vector_store.assert_called_once()
    new_store, new_retriever = knowledge.set_vector_store.call_args.args
    # The host Python may not have sqlite-vec extension loading —
    # accept either backend.
    assert isinstance(new_store, (SqliteVecStore, NumpyBruteForceStore))
    assert isinstance(new_retriever, (BaseRetriever, TimeoutRetriever, Retriever))
