"""``Settings`` after DO-11: provider fields live in the JSON registry."""

from __future__ import annotations

import pytest

from simple_cli_coder_with_rag.infrastructure.settings import Settings


def test_settings_no_longer_carries_provider_fields() -> None:
    settings = Settings()
    for removed in (
        "nvidia_api_key",
        "mistral_api_key",
        "minimax_api_key",
        "default_provider",
        "nvidia_model",
        "mistral_model",
        "minimax_model",
        "nvidia_base_url",
        "mistral_base_url",
        "minimax_base_url",
        "chat_model",
        "compactor_model",
    ):
        assert not hasattr(settings, removed)


def test_settings_still_reads_non_provider_knobs() -> None:
    settings = Settings(chunker_strategy="semantic", vector_store="brute_force")
    assert settings.chunker_strategy == "semantic"
    assert settings.vector_store == "brute_force"


def test_settings_ignores_legacy_provider_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stale ``DEFAULT_PROVIDER`` / ``NVIDIA_API_KEY`` env does not crash construction."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nv")
    monkeypatch.setenv("DEFAULT_PROVIDER", "nvidia")
    Settings()


def test_settings_extra_env_vars_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOTALLY_UNKNOWN_VAR", "ignored")
    Settings()
