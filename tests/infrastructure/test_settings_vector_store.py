"""Tests for ``Settings.vector_store`` and ``Settings.db_path`` + ``resolve_db_path``.

Pinned by ``agent-development/07-vector-store-strategy/contracts.md``.

The vector-store configuration is small but tightly coupled to the
composition root:

* ``vector_store`` — ``"sqlite_vec"`` (default, ``SqliteVecStore``)
  or ``"brute_force"`` (``NumpyBruteForceStore`` opt-in / fallback).
  Pydantic validation rejects unknown values at construction so the
  error surfaces at startup, not later in the REPL.
* ``db_path`` — on-disk path for the sqlite-vec database. ``None``
  (default) means "use the platform-default data dir + ``db.sqlite``".
  The :func:`resolve_db_path` helper is the single source of truth
  (matches :func:`LocalPaths.data_dir() / "db.sqlite"`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from simple_cli_coder_with_rag.infrastructure.settings import (
    Settings,
    resolve_db_path,
)


def _settings(**overrides: object) -> Settings:
    """Return a ``Settings`` instance."""
    base: dict[str, object] = {}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_settings_default_vector_store() -> None:
    """Default ``vector_store`` is ``"sqlite_vec"`` (the persistent Strategy)."""
    settings = _settings()

    assert settings.vector_store == "sqlite_vec"


def test_settings_accepts_brute_force() -> None:
    """``vector_store="brute_force"`` is a valid value (the in-memory fallback)."""
    settings = _settings(vector_store="brute_force")

    assert settings.vector_store == "brute_force"


def test_settings_accepts_sqlite_vec_explicit() -> None:
    """``vector_store="sqlite_vec"`` is accepted (same as the default)."""
    settings = _settings(vector_store="sqlite_vec")

    assert settings.vector_store == "sqlite_vec"


def test_settings_rejects_unknown_vector_store() -> None:
    """Unknown values raise ``ValidationError`` at construction."""
    with pytest.raises(ValidationError):
        _settings(vector_store="faiss")


def test_settings_vector_store_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """``VECTOR_STORE=brute_force`` in the env is honoured by ``Settings()``."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nv")
    monkeypatch.setenv("VECTOR_STORE", "brute_force")

    settings = Settings()

    assert settings.vector_store == "brute_force"


def test_settings_default_db_path_is_none() -> None:
    """``db_path`` defaults to ``None`` so :func:`resolve_db_path` fills in the platform default."""
    settings = _settings()

    assert settings.db_path is None


def test_settings_db_path_is_overridable(tmp_path: Path) -> None:
    """``db_path`` can be set to an explicit ``Path`` via kwarg."""
    settings = _settings(db_path=tmp_path / "custom.sqlite")

    assert settings.db_path == tmp_path / "custom.sqlite"


def test_settings_db_path_reads_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``DB_PATH=/some/path`` in the env is honoured by ``Settings()``."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nv")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "from-env.sqlite"))

    settings = Settings()

    assert settings.db_path == tmp_path / "from-env.sqlite"


def test_resolve_db_path_returns_explicit_override(tmp_path: Path) -> None:
    """``resolve_db_path`` returns the explicit override verbatim."""
    explicit = tmp_path / "explicit.sqlite"
    settings = _settings(db_path=explicit)

    assert resolve_db_path(settings) == explicit


def test_resolve_db_path_falls_back_to_local_paths_data_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``resolve_db_path`` falls back to the platform-default data dir when ``db_path is None``."""
    # Point ``LocalPaths.data_dir`` at a known temp dir so the assertion
    # is hermetic (independent of the user's real ``platformdirs``
    # data dir). Patch the source — the ``settings`` module imports
    # ``LocalPaths`` inside the helper, so patching the local_paths
    # module's attribute is the only path that affects the call.
    from simple_cli_coder_with_rag.infrastructure import local_paths

    monkeypatch.setattr(local_paths.LocalPaths, "data_dir", classmethod(lambda cls: tmp_path))

    settings = _settings()

    assert resolve_db_path(settings) == tmp_path / "db.sqlite"
    assert isinstance(resolve_db_path(settings), Path)
