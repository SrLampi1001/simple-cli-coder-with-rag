"""Tests for the swappable vector store factory (DO-13).

The factory is the single composition point that picks a
:class:`VectorStore` backend from :class:`Settings`. The
``Settings.vector_store_strategy`` is the family pick
(``"sqlite"`` for v1, ``"supabase"`` is the follow-up DO) and
``Settings.vector_store`` is the sub-pick inside the family
(``"sqlite_vec"`` / ``"brute_force"``).

The Supabase branch raises :class:`VectorStoreBackendUnavailable`
with a friendly message so the user gets a clean failure path
rather than an opaque ``KeyError`` from a switch that has not
been wired yet. The architecture seam is in place; the adapter is
the follow-up.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from simple_cli_coder_with_rag.domain.vector_store import VectorStoreBackendUnavailable
from simple_cli_coder_with_rag.infrastructure.settings import Settings
from simple_cli_coder_with_rag.infrastructure.vector_stores import (
    NumpyBruteForceStore,
    SqliteVecStore,
    build_vector_store,
)


def _settings(**overrides: object) -> Settings:
    """Build a ``Settings`` with a non-empty active vector store config."""
    base: dict[str, object] = {
        "vector_store_strategy": "sqlite",
        "vector_store": "sqlite_vec",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_build_vector_store_sqlite_vec_strategy(tmp_path: Path) -> None:
    """``strategy='sqlite'`` + ``vector_store='sqlite_vec'`` returns a usable VectorStore.

    The factory returns :class:`SqliteVecStore` when the host
    Python's SQLite build can load extensions, or falls back to
    :class:`NumpyBruteForceStore` when it cannot. We accept either
    backend; the important invariant is that the factory returns
    a usable :class:`VectorStore`.
    """
    settings = _settings(db_path=tmp_path / "db.sqlite")
    store = build_vector_store(settings)

    assert isinstance(store, (SqliteVecStore, NumpyBruteForceStore))


def test_build_vector_store_sqlite_brute_force(tmp_path: Path) -> None:
    """``strategy='sqlite'`` + ``vector_store='brute_force'`` returns ``NumpyBruteForceStore``."""
    settings = _settings(vector_store="brute_force")
    store = build_vector_store(settings)

    assert isinstance(store, NumpyBruteForceStore)


def test_build_vector_store_supabase_not_wired() -> None:
    """``strategy='supabase'`` raises ``VectorStoreBackendUnavailable`` (DO-13 follow-up)."""
    settings = _settings(vector_store_strategy="supabase")
    with pytest.raises(VectorStoreBackendUnavailable) as exc:
        build_vector_store(settings)

    msg = str(exc.value).lower()
    assert "supabase" in msg
    assert "not" in msg  # "is not wired"


def test_build_vector_store_unknown_strategy() -> None:
    """An unrecognised strategy raises (the ``Literal`` validator rejects it)."""
    with pytest.raises(ValidationError):
        # ``Settings`` is a Pydantic model — an unknown strategy is
        # rejected at construction time, not at the factory call.
        Settings(  # type: ignore[call-arg]
            vector_store_strategy="chroma",  # type: ignore[arg-type]
        )


def test_build_vector_store_returns_protocol_compatible(tmp_path: Path) -> None:
    """The returned object satisfies the ``VectorStore`` duck-typed Protocol.

    ``VectorStore`` is a ``typing.Protocol`` without
    ``@runtime_checkable`` so ``isinstance(...)`` is not
    available. We duck-type-check the two required methods
    (``upsert`` and ``query``) instead.
    """
    settings = _settings(db_path=tmp_path / "ok.sqlite")
    store = build_vector_store(settings)

    assert hasattr(store, "upsert")
    assert hasattr(store, "query")
    assert callable(store.upsert)
    assert callable(store.query)


def test_build_vector_store_falls_back_on_unavailable(
    mocker: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``SqliteVecStore`` raising ``VectorStoreBackendUnavailable`` triggers the numpy fallback."""
    from simple_cli_coder_with_rag.infrastructure.vector_stores import factory as _factory

    mocker.patch.object(
        _factory,
        "SqliteVecStore",
        side_effect=VectorStoreBackendUnavailable("disabled"),
    )

    settings = _settings(db_path=tmp_path / "db.sqlite")
    store = build_vector_store(settings)

    assert isinstance(store, NumpyBruteForceStore)
