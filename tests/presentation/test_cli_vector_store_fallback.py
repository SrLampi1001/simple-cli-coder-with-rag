"""Tests for the composition-root's vector-store wiring and fallback.

Pinned by ``agent-development/07-vector-store-strategy/contracts.md``
behavioral contract:

* ``SqliteVecStore(...)`` raises ``VectorStoreBackendUnavailable`` on a
  Python build that cannot load extensions. The composition root must
  catch it and use ``NumpyBruteForceStore`` instead.
* The fallback writes a single INFO log line so the user can see why
  persistence is off (grep the log file).
* ``Settings.vector_store == "brute_force"`` short-circuits the
  sqlite-vec attempt entirely.

These tests exercise ``_build_vector_store`` directly so the prompt /
REPL / API-key bootstrapping does not have to be in the picture.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from simple_cli_coder_with_rag.cli import _build_vector_store
from simple_cli_coder_with_rag.domain.vector_store import (
    VectorStoreBackendUnavailable,
)
from simple_cli_coder_with_rag.infrastructure.settings import Settings
from simple_cli_coder_with_rag.infrastructure.vector_stores import (
    NumpyBruteForceStore,
    SqliteVecStore,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _settings(**overrides: object) -> Settings:
    """Return a ``Settings`` instance with a non-empty active key."""
    base: dict[str, object] = {"vector_store": "sqlite_vec"}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_brute_force_setting_skips_sqlite_vec(mocker: MockerFixture, tmp_path: Path) -> None:
    """``brute_force`` returns ``NumpyBruteForceStore`` without touching sqlite-vec."""
    sqlite_vec_ctor = mocker.patch(
        "simple_cli_coder_with_rag.cli.SqliteVecStore",
        side_effect=AssertionError("SqliteVecStore must not be instantiated in brute_force mode"),
    )

    settings = _settings(vector_store="brute_force")
    store = _build_vector_store(settings)

    assert isinstance(store, NumpyBruteForceStore)
    sqlite_vec_ctor.assert_not_called()


def test_sqlite_vec_setting_returns_sqlite_vec_store(mocker: MockerFixture, tmp_path: Path) -> None:
    """When ``SqliteVecStore(db_path)`` succeeds, it is the active store."""
    fake_instance = mocker.MagicMock(spec=SqliteVecStore)
    mocker.patch(
        "simple_cli_coder_with_rag.cli.SqliteVecStore",
        return_value=fake_instance,
    )

    settings = _settings(db_path=tmp_path / "db.sqlite")
    store = _build_vector_store(settings)

    assert store is fake_instance


def test_sqlite_vec_unavailable_falls_back_to_numpy(mocker: MockerFixture, tmp_path: Path) -> None:
    """``SqliteVecStore`` raising ``VectorStoreBackendUnavailable`` triggers the fallback."""
    mocker.patch(
        "simple_cli_coder_with_rag.cli.SqliteVecStore",
        side_effect=VectorStoreBackendUnavailable(
            "This Python build does not support sqlite3 extension loading. "
            "Set VECTOR_STORE=brute_force to use the numpy fallback."
        ),
    )
    # Capture loguru INFO lines so we can assert the user-visible signal.
    sink_id = mocker.patch.object(logger, "info")

    settings = _settings(db_path=tmp_path / "db.sqlite")
    store = _build_vector_store(settings)

    assert isinstance(store, NumpyBruteForceStore)
    sink_id.assert_called_once()
    # The message must mention the fallback so the user can grep for it.
    fmt, *_ = sink_id.call_args.args
    rendered = fmt.format(*sink_id.call_args.args[1:]) if sink_id.call_args.args[1:] else fmt
    assert "sqlite-vec unavailable" in rendered.lower() or "fallback" in rendered.lower()


def test_fallback_logs_once_per_startup(mocker: MockerFixture, tmp_path: Path) -> None:
    """Multiple failed builds still log one INFO line per call.

    The composition root is called once at startup, so this is more of
    a regression guard: a future change that wraps the exception in a
    retry loop should not double-log.
    """
    mocker.patch(
        "simple_cli_coder_with_rag.cli.SqliteVecStore",
        side_effect=VectorStoreBackendUnavailable("disabled"),
    )
    mocker.patch.object(logger, "info")

    settings = _settings(db_path=tmp_path / "db.sqlite")

    _build_vector_store(settings)

    assert logger.info.call_count == 1


def test_build_vector_store_returns_protocol_compatible_object(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """The returned object satisfies the ``VectorStore`` duck-typed Protocol."""
    # Both branches — sqlite_vec (successful) and brute_force — must
    # satisfy the protocol. Verify duck-typing (``VectorStore`` is a
    # ``typing.Protocol`` without ``@runtime_checkable`` so ``isinstance``
    # raises).
    mocker.patch(
        "simple_cli_coder_with_rag.cli.SqliteVecStore",
        return_value=mocker.MagicMock(spec=SqliteVecStore),
    )

    settings_ok = _settings(db_path=tmp_path / "ok.sqlite")
    store_ok = _build_vector_store(settings_ok)
    assert hasattr(store_ok, "upsert")
    assert hasattr(store_ok, "query")
    assert callable(store_ok.upsert)
    assert callable(store_ok.query)

    settings_bf = _settings(vector_store="brute_force")
    store_bf = _build_vector_store(settings_bf)
    assert hasattr(store_bf, "upsert")
    assert hasattr(store_bf, "query")
    assert callable(store_bf.upsert)
    assert callable(store_bf.query)
