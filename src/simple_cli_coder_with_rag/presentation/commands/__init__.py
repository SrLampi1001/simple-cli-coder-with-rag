"""Command-pattern contracts for the REPL.

Built-in commands live in submodules of this package. The REPL
(:mod:`simple_cli_coder_with_rag.presentation.repl`) composes them via
:class:`CommandRegistry`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from simple_cli_coder_with_rag.application.knowledge_service import (
        KnowledgeService,
    )
    from simple_cli_coder_with_rag.application.session_store import SessionStore
    from simple_cli_coder_with_rag.domain.chunker import Chunker
    from simple_cli_coder_with_rag.domain.embedder import Embedder
    from simple_cli_coder_with_rag.domain.file_editor import FileEditor
    from simple_cli_coder_with_rag.domain.llm_client import LLMClient
    from simple_cli_coder_with_rag.domain.messages import Message
    from simple_cli_coder_with_rag.domain.vector_store import VectorStore
    from simple_cli_coder_with_rag.infrastructure.providers.registry import (
        ProviderRegistry,
    )
    from simple_cli_coder_with_rag.infrastructure.settings import Settings
    from simple_cli_coder_with_rag.presentation.repl import Repl


@dataclass
class AppState:
    """Mutable application state passed to commands and the REPL.

    ``Settings`` is built once in the composition root. The cap on the
    active conversation window (``Settings.int_history_cap``) is read
    by the REPL through ``app_state.settings`` (DO-12); the legacy
    ``history_cap`` field that backed the in-REPL trim in DO-03 is
    removed. ``None`` is permitted for pre-DO-12 unit tests — the REPL
    falls back to the documented default ``10``.

    ``history`` is a list that is **mutated in place** by the REPL
    (``history.append(...)``, ``history[:] = history[-cap:]``) and by
    the ``ResumeCommand`` (``history[:] = ...`` on a /resume).
    ``llm`` and ``knowledge`` are reassigned in place by
    provider-switch commands.

    ``knowledge`` is wired by the composition root in ``cli.py`` once
    the active provider's adapter is built. It defaults to ``None`` so
    unit tests that don't need an LLM can construct a bare ``AppState``.

    ``session_id`` is a UUIDv4 hex string generated at startup by the
    composition root (via ``SessionStore.current_id``). It is the
    identifier the REPL passes to ``KnowledgeService.learn`` when the
    user runs ``/learn``, the filename prefix used by the session
    store (``<root>/<session_id>.jsonl``), and the value
    ``/resume <id>`` swaps in. ``ResumeCommand`` may assign a new
    value mid-run.

    ``session_store`` is the on-disk store for transcripts and
    compacted JSON. The composition root wires the real
    :class:`~simple_cli_coder_with_rag.application.session_store.SessionStore`;
    ``None`` is permitted only for tests that do not exercise the
    session-store path.

    ``embedder`` is the ``Embedder`` Protocol implementation built by
    the composition root (DO-06 — ``FastembedEmbedder``). The embedder
    loads on a daemon thread, so ``is_ready()`` may return ``False``
    when the REPL first opens; ``KnowledgeService.recall`` (DO-09)
    short-circuits to "no memories" in that case. ``None`` is permitted
    only for tests that do not exercise the embedder surface.

    ``vector_store`` (DO-13) is the live :class:`VectorStore` instance
    currently driving retrieval. The composition root wires the first
    instance; ``/vector-store`` swaps it in place. ``None`` is permitted
    only for tests that do not exercise the store surface.

    ``active_vector_store`` (DO-13) is a short, human-readable name for
    the active backend (``"sqlite_vec"`` / ``"brute_force"`` / —
    in a follow-up DO — ``"supabase"``). The REPL prints it on
    ``/vector-store``; the tests assert against it. Default
    ``"sqlite_vec"`` matches the historical default.

    ``persisted_through`` (DO-12) is the count of leading messages in
    ``history`` that have already been appended to the
    ``<session_id>.jsonl`` transcript. The REPL updates it after every
    persisted turn; ``ResumeCommand`` sets it to ``len(history)`` after
    loading a transcript so the loaded messages are never
    re-appended. The default ``0`` keeps every existing test passing
    — a fresh ``AppState`` has no history and therefore nothing to
    persist.
    """

    version: str
    llm: LLMClient | None = None
    knowledge: KnowledgeService | None = None
    history: list[Message] = field(default_factory=list)
    session_id: str = ""
    session_store: SessionStore | None = None
    chunker: Chunker | None = None
    embedder: Embedder | None = None
    editor: FileEditor | None = None
    provider_registry: ProviderRegistry | None = None
    settings: Settings | None = None
    persisted_through: int = 0
    vector_store: VectorStore | None = None
    active_vector_store: str = "sqlite_vec"


@dataclass(frozen=True)
class CommandContext:
    """Per-invocation context handed to a :class:`Command`."""

    repl: Repl
    app_state: AppState
    # Raw remainder of the input line after the command token ("" by default
    # so existing zero-arg commands are unaffected).
    args: str = ""


@dataclass(frozen=True)
class CommandResult:
    """Outcome of executing a :class:`Command`."""

    action: Literal["continue", "exit"] = "continue"
    message: str | None = field(default=None)


class Command(Protocol):
    """Minimal contract every REPL command implements."""

    name: str
    summary: str

    def execute(self, context: CommandContext) -> CommandResult: ...


__all__ = ["AppState", "Command", "CommandContext", "CommandResult"]
