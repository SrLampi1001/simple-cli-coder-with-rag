"""``coder`` entry point.

Responsibilities:

* parse ``--version`` / ``--help`` / ``--reset`` via :mod:`argparse`;
* on ``--reset``, wipe the local data directory **before** any logger or
  REPL state is touched (so a destructive run never races a live SQLite
  handle);
* otherwise, configure loguru to write to ``platformdirs.user_log_dir``,
  load :class:`Settings`, build the ``LLMClient`` for the active
  provider, build the session store + compactor + ``KnowledgeService``
  facade, build the vector store (with ``SqliteVecStore`` falling back
  to ``NumpyBruteForceStore`` when ``sqlite-vec`` cannot load — DO-07),
  build the retriever chain (``BaseRetriever`` wrapped in
  ``TimeoutRetriever`` sharing one ``RetrievalExecutor`` — DO-08),
  generate a fresh UUIDv4 session id, and start the
  :class:`~simple_cli_coder_with_rag.presentation.repl.Repl`.

The composition root is also responsible for **registering
``RetrievalExecutor.shutdown`` on REPL exit** (passed as the ``Repl``'s
``on_exit`` callback) so Ctrl-D does not hang waiting for in-flight
retrieval threads (``docs/development-tools.md`` §9).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import platformdirs
from loguru import logger

from simple_cli_coder_with_rag import __version__
from simple_cli_coder_with_rag.application.compactor import Compactor
from simple_cli_coder_with_rag.application.knowledge_service import (
    KnowledgeService,
    build_chunker,
)
from simple_cli_coder_with_rag.application.recall_coordinator import (
    RecallCoordinator,
)
from simple_cli_coder_with_rag.application.retrievers.base_retriever import (
    BaseRetriever,
)
from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.application.trivial_gate import TrivialGate
from simple_cli_coder_with_rag.domain.vector_store import (
    VectorStore,
    VectorStoreBackendUnavailable,
)
from simple_cli_coder_with_rag.infrastructure.embedders import FastembedEmbedder
from simple_cli_coder_with_rag.infrastructure.llm import build_llm_client
from simple_cli_coder_with_rag.infrastructure.local_paths import LocalPaths
from simple_cli_coder_with_rag.infrastructure.logging import configure_logging
from simple_cli_coder_with_rag.infrastructure.retrievers.executor import (
    RetrievalExecutor,
)
from simple_cli_coder_with_rag.infrastructure.retrievers.timeout_retriever import (
    TimeoutRetriever,
)
from simple_cli_coder_with_rag.infrastructure.settings import (
    Settings,
    resolve_db_path,
)
from simple_cli_coder_with_rag.infrastructure.vector_stores import (
    NumpyBruteForceStore,
    SqliteVecStore,
)
from simple_cli_coder_with_rag.presentation.commands import AppState
from simple_cli_coder_with_rag.presentation.commands.clear import ClearCommand
from simple_cli_coder_with_rag.presentation.commands.exit import ExitCommand
from simple_cli_coder_with_rag.presentation.commands.help import HelpCommand
from simple_cli_coder_with_rag.presentation.commands.learn import LearnCommand
from simple_cli_coder_with_rag.presentation.commands.version import VersionCommand
from simple_cli_coder_with_rag.presentation.registry import CommandRegistry
from simple_cli_coder_with_rag.presentation.repl import Repl


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="coder",
        description="Interactive coding assistant with optional RAG context.",
    )
    parser.add_argument("--version", action="store_true", help="print the package version and exit")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="wipe the local data directory after a y/N prompt",
    )
    return parser


def _build_registry() -> CommandRegistry:
    registry = CommandRegistry()
    registry.register(HelpCommand(registry))
    registry.register(ExitCommand())
    registry.register(ClearCommand())
    registry.register(VersionCommand())
    registry.register(LearnCommand())
    return registry


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a shell exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.reset:
        # Short-circuit: destructive path must not touch the logger or the
        # REPL, so it cannot race with a live SQLite connection.
        return _reset_local_data()

    if args.version:
        print(__version__)
        return 0

    configure_logging()

    _settings, app_state, retrieval_executor = _bootstrap_app_state()
    if app_state is None or retrieval_executor is None:
        # Settings validation failed; the helper already wrote the message
        # to stderr. We deliberately do **not** start the REPL here — the
        # prompt would corrupt the message.
        return 2

    # Flip the embedder module's ``_REPL_ACTIVE`` flag **before**
    # ``repl.run()``. From this point on, the embedder's background
    # thread routes the cold-cache download notice through the log file
    # instead of stderr — ``prompt_toolkit`` owns the screen during
    # ``repl.run()`` and would corrupt the prompt otherwise. The flag
    # lives in ``infrastructure.embedders.fastembed_embedder``; this is
    # the only place the presentation layer touches it.
    from simple_cli_coder_with_rag.infrastructure.embedders import fastembed_embedder

    fastembed_embedder._REPL_ACTIVE = True

    registry = _build_registry()
    # ``RetrievalExecutor.shutdown`` is registered as the REPL's exit hook so
    # Ctrl-D does not hang waiting for in-flight retrieval threads
    # (``docs/development-tools.md`` §9). The executor is shared by the
    # ``TimeoutRetriever`` built inside ``_bootstrap_app_state`` — there is
    # exactly one executor per process.
    repl = Repl(
        registry=registry,
        app_state=app_state,
        on_exit=retrieval_executor.shutdown,
    )
    repl.run()
    return 0


def _bootstrap_app_state() -> tuple[Settings | None, AppState | None, RetrievalExecutor | None]:
    """Instantiate Settings, build the active LLM client, and bundle into AppState.

    Returns ``(None, None, None)`` if the active provider's API key is missing —
    in that case the helper prints a friendly message to stderr (the only
    place we write to stderr before ``prompt_toolkit`` takes over) and the
    caller exits with code 2. On success, returns the wired ``RetrievalExecutor``
    alongside ``settings`` and ``app_state`` so the caller can register
    ``executor.shutdown`` as the REPL's ``on_exit`` callback (DO-08).
    """
    try:
        settings = Settings()
    except RuntimeError as exc:
        # Active provider's key is missing. This is the only stderr write
        # before the REPL takes over.
        print(f"coder: {exc}", file=sys.stderr)
        return None, None, None

    llm_client = build_llm_client(settings)
    chat_model = _resolve_chat_model(settings)
    compactor_model = _resolve_compactor_model(settings)

    # Session store and compactor are wired *before* the KnowledgeService so
    # the service receives both in its constructor. The session id is
    # generated by the store (UUIDv4 hex) so the REPL has a stable,
    # filesystem-friendly identifier to pass to ``/learn`` and to use as a
    # filename prefix on disk.
    session_store = SessionStore(root=LocalPaths.data_dir() / "sessions")
    session_id = session_store.current_id()
    compactor = Compactor(llm=llm_client, compactor_model=compactor_model)
    chunker = build_chunker(settings.chunker_strategy)

    # Embedder (DO-06). Built on a daemon thread so the REPL can open
    # before the ~130 MB BGE-small download finishes. The cache dir sits
    # under ``platformdirs.user_cache_dir`` so the model survives reboots
    # and reinstalls (per ``docs/development-tools.md`` §5). We do not
    # call ``warmup()`` here; the background thread drives the load and
    # downstream callers gate on ``is_ready()``.
    embedder_cache_dir = Path(platformdirs.user_cache_dir("simple-cli-coder-with-rag")) / "models"
    embedder = FastembedEmbedder(
        model_name=settings.embedding_model,
        cache_dir=embedder_cache_dir,
        local_files_only=settings.embedding_local_files_only,
    )

    # Vector store (DO-07). ``SqliteVecStore`` is the default; the
    # ``Settings.vector_store=="brute_force"`` setting short-circuits the
    # sqlite-vec attempt, and an ``init`` failure (``VectorStoreBackendUnavailable``)
    # also falls back to ``NumpyBruteForceStore``. The fallback is logged
    # at INFO so the user can see it in ``tail -f`` of the log file.
    vector_store = _build_vector_store(settings)

    # Retriever chain (DO-08). One ``RetrievalExecutor`` is built and shared
    # by the timeout-wrapped retriever; the executor is returned to the caller
    # so its ``shutdown`` is wired to REPL exit. ``BaseRetriever`` is the
    # default Strategy; ``TimeoutRetriever`` Decorator wraps it so the REPL
    # never blocks past ``settings.retrieval_timeout_seconds``.
    retrieval_executor = RetrievalExecutor()
    retriever = TimeoutRetriever(
        BaseRetriever(embedder=embedder, vector_store=vector_store),
        timeout_seconds=settings.retrieval_timeout_seconds,
        executor=retrieval_executor,
    )

    # Recall coordinator (DO-09). The coordinator takes the **already-wrapped**
    # retriever above — it does not own an executor and does not wrap again.
    # ``TrivialGate`` short-circuits trivial prompts inside the coordinator,
    # and the similarity threshold drops weakly-related hits before they
    # reach the LLM context.
    trivial_gate = TrivialGate(
        max_chars=settings.trivial_gate_max_chars,
        max_words=settings.trivial_gate_max_words,
    )
    recall_coordinator = RecallCoordinator(
        retriever=retriever,
        gate=trivial_gate,
        top_k=settings.recall_top_k,
        similarity_threshold=settings.recall_similarity_threshold,
    )

    knowledge = KnowledgeService(
        llm=llm_client,
        chat_model=chat_model,
        session_store=session_store,
        compactor=compactor,
        chunker=chunker,
        embedder=embedder,
        vector_store=vector_store,
        coordinator=recall_coordinator,
    )
    app_state = AppState(
        version=__version__,
        llm=llm_client,
        knowledge=knowledge,
        session_id=session_id,
        session_store=session_store,
        chunker=chunker,
        embedder=embedder,
    )
    return settings, app_state, retrieval_executor


def _build_vector_store(settings: Settings) -> VectorStore:
    """Build the configured vector store, with graceful fallback.

    Order of attempts:

    1. ``settings.vector_store == "brute_force"`` → use
       :class:`NumpyBruteForceStore` directly (no sqlite-vec attempt).
    2. ``settings.vector_store == "sqlite_vec"`` (default) → try
       :class:`SqliteVecStore`. If its constructor raises
       :class:`VectorStoreBackendUnavailable`, fall back to
       :class:`NumpyBruteForceStore` and log a single INFO line so the
       user can grep for it.

    The fallback decision is logged through ``loguru`` to the file sink
    (not stderr) — ``prompt_toolkit`` will own stderr during normal runs.
    """
    if settings.vector_store == "brute_force":
        return NumpyBruteForceStore()

    db_path = resolve_db_path(settings)
    try:
        return SqliteVecStore(db_path=db_path)
    except VectorStoreBackendUnavailable as exc:
        logger.info("sqlite-vec unavailable, falling back to numpy: {}", exc)
        return NumpyBruteForceStore()


def _resolve_chat_model(settings: Settings) -> str:
    """Return the model name to pass to ``LLMClient.complete`` for chat turns.

    ``settings.chat_model`` is the explicit override (set via the
    ``CHAT_MODEL`` env var). An empty string means "no override"; in that
    case we fall back to the active provider's per-provider default so the
    REPL still has a usable model out of the box.
    """
    if settings.chat_model:
        return settings.chat_model
    return getattr(settings, f"{settings.default_provider}_model")


def _resolve_compactor_model(settings: Settings) -> str:
    """Return the model name to pass to ``LLMClient.complete`` from the compactor.

    Mirrors :func:`_resolve_chat_model` but reads
    :attr:`Settings.compactor_model` instead — empty string falls back to
    the active provider's per-provider default so a user who never sets
    ``COMPACTOR_MODEL`` still gets a working compaction pipeline.
    """
    if settings.compactor_model:
        return settings.compactor_model
    return getattr(settings, f"{settings.default_provider}_model")


def _reset_local_data() -> int:
    """Wipe local data files after an interactive y/N prompt.

    Returns 0 whether the user confirms or aborts, and on an empty data
    directory. The REPL and the loguru file sink are intentionally not
    created here.
    """
    targets = LocalPaths.reset_targets()
    data_dir = LocalPaths.data_dir()
    print(f"This will delete {len(targets)} file(s) under {data_dir}:")
    for path in targets:
        print(f"  {path}")
    print("Continue? [y/N] ", end="", flush=True)
    answer = sys.stdin.readline().strip()
    if answer != "y":
        print("Aborted.")
        return 0
    for path in targets:
        path.unlink(missing_ok=True)
    print("Reset complete.")
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry only
    raise SystemExit(main())
