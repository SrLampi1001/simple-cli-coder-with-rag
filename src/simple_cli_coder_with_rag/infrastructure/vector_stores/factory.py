"""``VectorStoreFactory`` — the Strategy seam for swappable vector stores (DO-13).

This module is the **single composition point** for picking which
:class:`~simple_cli_coder_with_rag.domain.vector_store.VectorStore`
backend the application uses. The user-facing knobs are:

* :class:`Settings.vector_store_strategy` (``"sqlite"`` for v1, the
  literal is forward-compatible with ``"supabase"`` for a follow-up
  DO that wires the Supabase adapter).
* :class:`Settings.vector_store` — the *sub-pick* inside the
  ``"sqlite"`` family: ``"sqlite_vec"`` (default, persistent) or
  ``"brute_force"`` (in-memory fallback).
* The ``/vector-store`` command — runtime swap that calls
  :func:`build_vector_store` again with the new strategy and reaches
  into :meth:`KnowledgeService.set_vector_store` to rewire the
  retriever chain.

Adding a new backend (e.g. an in-memory HNSW index, a Chroma
adapter, or — in a follow-up DO — Supabase + pgvector) is a matter
of:

1. Writing a new class implementing :class:`VectorStore` in this
   package.
2. Adding a branch in :func:`build_vector_store` that returns an
   instance when its name is selected.

The presentation layer (``/vector-store`` command) and the
application layer (``KnowledgeService.set_vector_store``) never
need to change.

The "unsupported" branch is **explicit** — a future ``"supabase"``
selection returns a :class:`VectorStoreBackendUnavailable` with a
helpful message so the user gets a clean failure path rather than
an opaque ``KeyError`` from a switch that has not been wired yet.
This is the architecture-vs-implementation split the user asked
for: the seam is in place, the Supabase adapter is the follow-up.

Architectural note: this module imports from :mod:`domain` and
sibling :mod:`infrastructure.vector_stores` modules only. It does
not import vendor SDKs. The follow-up Supabase adapter would live
under :mod:`infrastructure.vector_stores` (mirroring
``sqlite_vec_store.py``) and be imported lazily inside the
``"supabase"`` branch — never at module scope, so the default
``sqlite`` install does not need the Supabase dependency.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from loguru import logger

from simple_cli_coder_with_rag.domain.vector_store import (
    VectorStore,
    VectorStoreBackendUnavailable,
)
from simple_cli_coder_with_rag.infrastructure.settings import Settings, resolve_db_path
from simple_cli_coder_with_rag.infrastructure.vector_stores.numpy_brute_force_store import (
    NumpyBruteForceStore,
)
from simple_cli_coder_with_rag.infrastructure.vector_stores.sqlite_vec_store import (
    SqliteVecStore,
)

# Forward-compatible literal mirroring ``Settings.vector_store_strategy``.
# Kept as a private alias here so the call site does not need to
# import the Settings module directly.
Strategy = Literal["sqlite", "supabase"]

# Friendly "not yet implemented" message for the ``"supabase"``
# branch. The architecture seam is in place; the adapter is the
# follow-up DO. Surfaced as ``VectorStoreBackendUnavailable`` so the
# composition root's existing fallback chain (and the ``/vector-store``
# command's friendly-error path) can treat it uniformly.
_SUPABASE_NOT_WIRED_MSG = (
    "Supabase vector store is not wired in this build. "
    "The DO-13 follow-up will add the adapter. "
    "Use 'sqlite_vec' or 'brute_force' for now."
)


def build_vector_store(
    settings: Settings,
    *,
    db_path: Path | None = None,
) -> VectorStore:
    """Build the configured :class:`VectorStore`, with graceful fallback.

    Selection logic (mirrors the ``Settings`` shape):

    1. ``settings.vector_store_strategy == "sqlite"`` → pick
       ``"sqlite_vec"`` (default) or ``"brute_force"`` based on
       ``settings.vector_store``. ``SqliteVecStore`` failure
       (``VectorStoreBackendUnavailable``) falls back to
       :class:`NumpyBruteForceStore` and logs at INFO.
    2. ``settings.vector_store_strategy == "supabase"`` → raise
       :class:`VectorStoreBackendUnavailable` with the
       forthcoming message. (Follow-up DO.)

    The fallback decision is logged through :mod:`loguru` to the
    file sink (not stderr) — :mod:`prompt_toolkit` owns stderr
    during normal runs.
    """
    strategy: Strategy = settings.vector_store_strategy  # type: ignore[assignment]

    if strategy == "sqlite":
        return _build_sqlite(settings, db_path=db_path)

    if strategy == "supabase":
        # Architecture seam in place; adapter is the follow-up DO.
        logger.info(
            "supabase vector store requested but not yet wired: {}",
            _SUPABASE_NOT_WIRED_MSG,
        )
        raise VectorStoreBackendUnavailable(_SUPABASE_NOT_WIRED_MSG)

    # ``Settings.vector_store_strategy`` is a ``Literal``; an
    # unknown value is a programming bug, not a user error.
    raise VectorStoreBackendUnavailable(f"unknown vector store strategy: {strategy!r}")


def _build_sqlite(settings: Settings, *, db_path: Path | None) -> VectorStore:
    """Build the ``sqlite`` family of vector stores with graceful fallback.

    Two sub-picks:

    * ``"sqlite_vec"`` (default) → :class:`SqliteVecStore`. On
      :class:`VectorStoreBackendUnavailable` (e.g. host Python
      cannot load extensions), fall back to
      :class:`NumpyBruteForceStore` and log at INFO.
    * ``"brute_force"`` → :class:`NumpyBruteForceStore` directly.

    The fallback decision is logged through :mod:`loguru` to the
    file sink — :mod:`prompt_toolkit` owns stderr during normal
    runs and would corrupt the prompt.
    """
    sub = settings.vector_store

    if sub == "brute_force":
        return NumpyBruteForceStore()

    # ``sqlite_vec`` is the default sub-pick.
    resolved = db_path if db_path is not None else resolve_db_path(settings)
    try:
        return SqliteVecStore(db_path=resolved)
    except VectorStoreBackendUnavailable as exc:
        logger.info("sqlite-vec unavailable, falling back to numpy: {}", exc)
        return NumpyBruteForceStore()


__all__ = ["Strategy", "build_vector_store"]
