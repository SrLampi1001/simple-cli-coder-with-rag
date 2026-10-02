"""Pydantic-settings configuration for non-provider knobs.

Provider credentials and models live in the JSON registry
(``infrastructure/providers/``), configured via ``/connect`` / ``/provider``.
This class keeps everything else: chunker, embedder, vector store,
retrieval, recall, and editor-sandbox tuning — still loaded from ``.env``.

Vector store configuration (DO-07):

* ``vector_store`` — pick between ``"sqlite_vec"`` (default,
  ``SqliteVecStore``) and ``"brute_force"`` (``NumpyBruteForceStore``).
  The composition root also falls back to ``brute_force`` automatically
  when the host Python's SQLite cannot load extensions.
* ``db_path`` — on-disk location of the ``sqlite-vec`` database. Defaults
  to ``None`` so :func:`resolve_db_path` fills in the platform-default
  path (``~/.local/share/simple-cli-coder-with-rag/db.sqlite``) at the
  composition root. Override via the ``DB_PATH`` env var when the user
  has a non-default data dir (CI, containerised installs, tests).

Retrieval timeout (DO-08):

* ``retrieval_timeout_seconds`` — upper bound on a single retrieval
  call, in seconds. The
  :class:`~simple_cli_coder_with_rag.infrastructure.retrievers.timeout_retriever.TimeoutRetriever`
  Decorator wraps the base retriever and submits each ``retrieve`` call
  to the retrieval :class:`~concurrent.futures.ThreadPoolExecutor`,
  waiting at most this many seconds via
  ``future.result(timeout=...)``. On timeout it returns ``[]`` and logs
  at DEBUG — the user never blocks past the deadline. Default ``1.5``
  is the value ``OBJECTIVES.md`` pins for v1 (the underlying query is a
  tiny cosine lookup on a few-hundred-row table; 1.5 s is plenty even
  on a slow CI runner). Override via the ``RETRIEVAL_TIMEOUT_SECONDS``
  env var for tighter SLAs (e.g. ``0.5`` for a latency-sensitive
  integration).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

VectorStoreChoice = Literal["sqlite_vec", "brute_force"]


class Settings(BaseSettings):
    """Non-provider configuration loaded from environment / ``.env``."""

    # Chunking strategy picked by the composition root for ``/learn``.
    # ``"fixed"`` — ``FixedSizeChunker`` (default, sliding window).
    # ``"semantic"`` — ``SemanticChunker`` (one chunk per record).
    # Override via the ``CHUNKER_STRATEGY`` env var; any other value is
    # rejected at validation time so the user gets a clean
    # ``ValidationError`` instead of a deferred ``KeyError`` in the REPL.
    chunker_strategy: Literal["fixed", "semantic"] = "fixed"

    # HuggingFace repo id for the local embedding model (DO-06). The
    # default ``BAAI/bge-small-en-v1.5`` is the 384-dim BGE model
    # ``docs/development-tools.md`` §5 pins — ONNX runtime via
    # ``fastembed``, English-only (an accepted v1 limitation). Override
    # via the ``EMBEDDING_MODEL`` env var to swap behind the same
    # ``Embedder`` Protocol when a multilingual model is needed.
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # Whether the embedder should skip the HuggingFace network check
    # when the model is already cached locally. ``True`` (default)
    # makes subsequent runs truly offline — ``fastembed`` calls the HF
    # API on every ``TextEmbedding()`` constructor invocation to verify
    # the cache, even with ``cache_dir`` set. Override via
    # ``EMBEDDING_LOCAL_FILES_ONLY`` env var (``0`` / ``1``).
    embedding_local_files_only: bool = True

    # Vector store Strategy (DO-07). ``"sqlite_vec"`` is the default;
    # the composition root falls back to ``"brute_force"`` automatically
    # when ``SqliteVecStore.__init__`` raises
    # :class:`VectorStoreBackendUnavailable` (host Python's SQLite build
    # cannot load extensions). Override via the ``VECTOR_STORE`` env
    # var to skip the sqlite-vec attempt altogether.
    vector_store: VectorStoreChoice = "sqlite_vec"

    # On-disk path for the ``sqlite-vec`` database. ``None`` (default)
    # means "use the platform-default data dir + ``db.sqlite``"; the
    # composition root resolves this via :func:`resolve_db_path`.
    # Override via the ``DB_PATH`` env var to relocate the DB (CI,
    # containerised installs, tests with ``tmp_path``).
    db_path: Path | None = None

    # Upper bound on a single retrieval call (DO-08). Used by the
    # ``TimeoutRetriever`` Decorator wrapping the base retriever at the
    # composition root. Plain ``float`` — pydantic-settings reads it
    # from the ``RETRIEVAL_TIMEOUT_SECONDS`` env var. The default ``1.5``
    # is the value ``OBJECTIVES.md`` pins for v1.
    retrieval_timeout_seconds: float = 1.5

    # Recall pipeline tuning (DO-09). ``recall_top_k`` caps how many
    # chunks the retriever returns for a single user prompt — small
    # enough to keep the LLM context window manageable, large enough
    # that "obvious" hits land inside the slice. Default ``3`` matches
    # the OBJECTIVES latency tip ("top-k 3 or so"). Override via the
    # ``RECALL_TOP_K`` env var.
    recall_top_k: int = 3

    # Minimum cosine similarity for a recalled chunk to be injected into
    # the chat prompt (DO-09). Chunks below the threshold are dropped
    # from the coordinator's output — keeps weakly-related noise out of
    # the LLM context. Default ``0.5`` is a conservative floor for
    # ``bge-small-en-v1.5`` cosine scores; tune up for stricter
    # precision, down for higher recall. Override via
    # ``RECALL_SIMILARITY_THRESHOLD``.
    recall_similarity_threshold: float = 0.5

    # Trivial-gate bounds (DO-09). A prompt is "trivial" when it
    # satisfies BOTH bounds (inclusive ``<=``), and the
    # :class:`~simple_cli_coder_with_rag.application.trivial_gate.TrivialGate`
    # short-circuits the recall path entirely. Defaults ``20`` chars and
    # ``4`` words match the OBJECTIVES latency tip. Override via
    # ``TRIVIAL_GATE_MAX_CHARS`` / ``TRIVIAL_GATE_MAX_WORDS``.
    trivial_gate_max_chars: int = 20
    trivial_gate_max_words: int = 4

    # Editor sandbox root (DO-10). The ``SandboxedFileEditor`` confines all
    # read/write/edit operations to this directory; any path that escapes
    # (via ``..`` traversal, an absolute path, or a symlink) raises
    # :class:`~simple_cli_coder_with_rag.domain.file_editor.PathNotAllowed`.
    # Default is :meth:`Path.cwd` so ``coder`` opens in the user's working
    # directory. Override via the ``EDITOR_ROOT`` env var to scope the
    # sandbox to a sub-project.
    editor_root: Path = Path.cwd()

    # Upper bound on tool-use rounds per chat turn (DO-10). One round is
    # one ``complete_with_tools`` call followed by zero-or-more tool
    # executions. Default ``1`` keeps the chat loop bounded — a runaway
    # agent cannot loop indefinitely calling tools. Override via the
    # ``EDITOR_MAX_TOOL_ROUNDS`` env var when more rounds are needed
    # (e.g. an editor that mutates files and re-reads them).
    editor_max_tool_rounds: int = 1

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Empty values in ``.env`` (e.g. ``RETRIEVAL_TIMEOUT_SECONDS=``)
        # are treated as "use the field default" instead of being parsed
        # as empty strings and failing numeric validation. This makes
        # ``.env.example`` round-trippable: a user who copies it to ``.env``
        # and fills in only the non-secret knobs gets the documented defaults.
        env_ignore_empty=True,
    )

    def __repr__(self) -> str:
        """Compact, key-free representation."""
        return (
            f"Settings(chunker_strategy={self.chunker_strategy!r}, "
            f"vector_store={self.vector_store!r}, "
            f"embedding_model={self.embedding_model!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


def resolve_db_path(settings: Settings) -> Path:
    """Return the on-disk DB path, falling back to the data dir default.

    ``Settings.db_path`` is the explicit override (set via ``DB_PATH``).
    ``None`` means "no override"; we then build the path from the
    single source of truth in
    :mod:`simple_cli_coder_with_rag.infrastructure.local_paths` so
    ``--reset``, the DB default, and ``VECTOR_STORE=brute_force`` opt-in
    all agree on where files live.
    """
    if settings.db_path is not None:
        return settings.db_path
    # Local import to dodge the circular dependency: ``settings`` is read
    # before ``LocalPaths`` is needed elsewhere, and ``LocalPaths`` does
    # not import ``Settings``.
    from simple_cli_coder_with_rag.infrastructure.local_paths import LocalPaths

    return LocalPaths.data_dir() / "db.sqlite"


__all__ = ["Settings", "VectorStoreChoice", "resolve_db_path"]
