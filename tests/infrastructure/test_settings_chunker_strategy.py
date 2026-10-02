"""Tests for ``Settings.chunker_strategy``.

Pinned by ``agent-development/05-chunker-strategy/tests.md``.

The ``chunker_strategy`` setting picks which ``Chunker`` Strategy
implementation the composition root instantiates:

* ``"fixed"`` — ``FixedSizeChunker`` (default).
* ``"semantic"`` — ``SemanticChunker``.

Any other string is rejected at validation time so the user gets a clean
``ValidationError`` instead of a deferred ``KeyError`` in the REPL.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from simple_cli_coder_with_rag.infrastructure.settings import Settings


def _settings(**overrides: object) -> Settings:
    """Return a ``Settings`` instance with a non-empty active key."""
    base: dict[str, object] = {
        "default_provider": "nvidia",
        "nvidia_api_key": SecretStr("nv"),
        "mistral_api_key": SecretStr(""),
        "minimax_api_key": SecretStr(""),
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_settings_default_chunker_strategy() -> None:
    """The default strategy is ``"fixed"``."""
    settings = _settings()

    assert settings.chunker_strategy == "fixed"


def test_settings_accepts_semantic() -> None:
    """``chunker_strategy="semantic"`` is a valid value."""
    settings = _settings(chunker_strategy="semantic")

    assert settings.chunker_strategy == "semantic"


def test_settings_accepts_fixed_explicit() -> None:
    """``chunker_strategy="fixed"`` is accepted (same as the default)."""
    settings = _settings(chunker_strategy="fixed")

    assert settings.chunker_strategy == "fixed"


def test_settings_rejects_unknown_strategy() -> None:
    """Unknown values raise ``ValidationError`` at construction."""
    with pytest.raises(ValidationError):
        _settings(chunker_strategy="foo")


def test_settings_chunker_strategy_reads_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``CHUNKER_STRATEGY=semantic`` in the env is honoured by ``Settings()``."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nv")
    monkeypatch.setenv("CHUNKER_STRATEGY", "semantic")

    settings = Settings()

    assert settings.chunker_strategy == "semantic"
