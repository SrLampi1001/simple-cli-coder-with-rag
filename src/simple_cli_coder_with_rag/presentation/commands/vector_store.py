"""``/vector-store`` command — switch the active vector store backend (DO-13).

This command is the user-facing seam on top of the swappable vector
store Strategy. With no arguments it prints the active backend; with
an argument it rebuilds the vector store, the
:class:`BaseRetriever` wrapped in :class:`TimeoutRetriever`, and
re-wires them through :meth:`KnowledgeService.set_vector_store` so
the next chat turn uses the new backend.

DO-13 wires the two currently-available sqlite-family backends:

* ``sqlite_vec`` (default) — persistent, requires a Python build with
  ``sqlite3`` extension loading. Falls back to ``brute_force`` on
  :class:`VectorStoreBackendUnavailable`.
* ``brute_force`` — in-memory, no persistence. Useful for one-shot
  experiments where the user does not want to dirty the on-disk DB.

The Supabase adapter (``supabase`` value) is the follow-up DO. The
command recognises the token and prints a friendly forthcoming
message — adding the actual adapter is a separate work item.
"""

from __future__ import annotations

from loguru import logger

from simple_cli_coder_with_rag.application.retrievers.base_retriever import (
    BaseRetriever,
)
from simple_cli_coder_with_rag.domain.embedder import Embedder
from simple_cli_coder_with_rag.domain.retriever import Retriever
from simple_cli_coder_with_rag.domain.vector_store import (
    VectorStore,
    VectorStoreBackendUnavailable,
)
from simple_cli_coder_with_rag.infrastructure.retrievers.executor import (
    RetrievalExecutor,
)
from simple_cli_coder_with_rag.infrastructure.retrievers.timeout_retriever import (
    TimeoutRetriever,
)
from simple_cli_coder_with_rag.infrastructure.vector_stores import build_vector_store
from simple_cli_coder_with_rag.presentation.commands import (
    CommandContext,
    CommandResult,
)

# Friendly "not yet implemented" message for the ``supabase`` token.
# The architecture seam is in place (the factory's ``"supabase"``
# branch returns ``VectorStoreBackendUnavailable``); the actual
# adapter is the follow-up DO.
_SUPABASE_FORTHCOMING = (
    "Supabase vector store is not wired in this build. "
    "The DO-13 follow-up will add the adapter; use 'sqlite_vec' or "
    "'brute_force' for now."
)

# Available backends — the set the user can pick. Supabase is listed
# in the help text so the user knows it is planned, but the actual
# token is rejected at runtime (see above).
_AVAILABLE_BACKENDS: tuple[str, ...] = ("sqlite_vec", "brute_force")


class VectorStoreCommand:
    """``/vector-store``: print or swap the active vector store backend."""

    name = "vector-store"
    summary = "Switch the active vector store backend (sqlite_vec | brute_force)."

    def execute(self, context: CommandContext) -> CommandResult:
        args = context.args.strip().lower()
        if not args:
            active = context.app_state.active_vector_store
            available = ", ".join(_AVAILABLE_BACKENDS)
            return CommandResult(
                action="continue",
                message=f"active vector store: {active}\navailable: {available}",
            )

        if args == "supabase":
            # Architecture seam in place; the adapter is the follow-up.
            return CommandResult(action="continue", message=_SUPABASE_FORTHCOMING)

        if args not in _AVAILABLE_BACKENDS:
            available = ", ".join(_AVAILABLE_BACKENDS)
            return CommandResult(
                action="continue",
                message=f"unknown vector store '{args}'. Available: {available}",
            )

        # The active backend is valid — rebuild the chain and rewire
        # ``KnowledgeService``. Build the new store with a temporary
        # ``Settings`` override so we honour the user's pick without
        # mutating the live settings object.
        knowledge = context.app_state.knowledge
        if knowledge is None:
            return CommandResult(
                action="continue", message="vector-store: knowledge not configured"
            )
        embedder = context.app_state.embedder
        if embedder is None:
            return CommandResult(action="continue", message="vector-store: embedder not configured")

        new_store, error = self._build_store(args, context)
        if error is not None:
            return CommandResult(action="continue", message=error)
        assert new_store is not None  # narrowed by the error branch

        new_retriever = self._build_retriever(
            embedder=embedder,
            store=new_store,
            executor=self._resolve_executor(context),
            timeout_seconds=self._resolve_timeout(context),
        )

        knowledge.set_vector_store(new_store, new_retriever)
        context.app_state.vector_store = new_store
        context.app_state.active_vector_store = args
        logger.info("vector-store: switched to {}", args)
        return CommandResult(action="continue", message=f"active vector store: {args}")

    @staticmethod
    def _build_store(
        backend: str,
        context: CommandContext,
    ) -> tuple[VectorStore | None, str | None]:
        """Build the named store. Returns ``(store, None)`` or ``(None, error_message)``."""
        settings = context.app_state.settings
        if settings is None:
            return None, "vector-store: settings not configured"

        # Build a one-off settings object with the requested sub-pick
        # so ``build_vector_store`` honours it without mutating the
        # live settings.
        candidate = settings.model_copy(update={"vector_store": backend})  # type: ignore[arg-type]
        try:
            return build_vector_store(candidate), None
        except VectorStoreBackendUnavailable as exc:
            logger.info("vector-store: backend unavailable: {}", exc)
            return None, f"vector-store: {exc}"

    @staticmethod
    def _build_retriever(
        *,
        embedder: Embedder,
        store: VectorStore,
        executor: RetrievalExecutor,
        timeout_seconds: float,
    ) -> Retriever:
        """Build the ``BaseRetriever`` + ``TimeoutRetriever`` chain for ``store``."""
        base = BaseRetriever(embedder=embedder, vector_store=store)
        return TimeoutRetriever(
            inner=base,
            timeout_seconds=timeout_seconds,
            executor=executor,
        )

    @staticmethod
    def _resolve_executor(context: CommandContext) -> RetrievalExecutor:
        """Return the shared ``RetrievalExecutor``.

        The composition root owns a single executor and registers its
        ``shutdown`` on REPL exit. The command reaches for the live
        executor through ``KnowledgeService._coordinator``'s retriever
        — the only one wired at this point. If the chain is
        uninitialised, the command falls back to a brand-new executor.
        The fallback is defensive; the REPL never invokes the command
        without a coordinator.
        """
        knowledge = context.app_state.knowledge
        if knowledge is not None and knowledge._coordinator is not None:
            retriever = knowledge._coordinator._retriever
            executor = getattr(retriever, "_executor", None)
            if isinstance(executor, RetrievalExecutor):
                return executor
        return RetrievalExecutor()

    @staticmethod
    def _resolve_timeout(context: CommandContext) -> float:
        """Return the active retrieval timeout, defaulting to 1.5s."""
        settings = context.app_state.settings
        if settings is None:
            return 1.5
        return settings.retrieval_timeout_seconds


__all__ = ["VectorStoreCommand"]
