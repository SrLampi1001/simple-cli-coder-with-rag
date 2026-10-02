"""Tests for the ``Settings`` embedder-related fields.

Pinned by ``agent-development/06-embedder-strategy/tests.md``.

The embedder wiring in the composition root needs two values from
``Settings``:

* ``embedding_model`` — the HuggingFace repo id for the local model.
  Defaults to ``"BAAI/bge-small-en-v1.5"`` (384-dim, BGE family).
* ``embedding_local_files_only`` — whether to skip the HuggingFace
  network check at startup. Defaults to ``True`` per dev-tools.md §5
  ("make subsequent runs truly offline").

Both must be overridable via env vars
(``EMBEDDING_MODEL``, ``EMBEDDING_LOCAL_FILES_ONLY``).
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from simple_cli_coder_with_rag.infrastructure.settings import Settings


def _settings(**overrides: object) -> Settings:
    """Return a ``Settings`` instance with a non-empty active provider key."""
    base: dict[str, object] = {
        "default_provider": "nvidia",
        "nvidia_api_key": SecretStr("nv"),
        "mistral_api_key": SecretStr(""),
        "minimax_api_key": SecretStr(""),
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_settings_default_embedding_model() -> None:
    """Default ``embedding_model`` is the BGE-small-en-v1.5 repo id."""
    settings = _settings()

    assert settings.embedding_model == "BAAI/bge-small-en-v1.5"


def test_settings_default_embedding_local_files_only() -> None:
    """Default ``embedding_local_files_only`` is ``True`` (offline-friendly)."""
    settings = _settings()

    assert settings.embedding_local_files_only is True


def test_settings_embedding_model_overridable() -> None:
    """``embedding_model`` can be set explicitly in the constructor."""
    settings = _settings(embedding_model="custom/model")

    assert settings.embedding_model == "custom/model"


def test_settings_embedding_local_files_only_overridable() -> None:
    """``embedding_local_files_only=False`` is accepted (developer opt-in to refresh)."""
    settings = _settings(embedding_local_files_only=False)

    assert settings.embedding_local_files_only is False


def test_settings_embedding_model_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """``EMBEDDING_MODEL`` in the env is honoured by ``Settings()``."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nv")
    monkeypatch.setenv("EMBEDDING_MODEL", "custom/from-env")

    settings = Settings()

    assert settings.embedding_model == "custom/from-env"


def test_settings_embedding_local_files_only_reads_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``EMBEDDING_LOCAL_FILES_ONLY=0`` in the env flips the flag off."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nv")
    monkeypatch.setenv("EMBEDDING_LOCAL_FILES_ONLY", "0")

    settings = Settings()

    assert settings.embedding_local_files_only is False
