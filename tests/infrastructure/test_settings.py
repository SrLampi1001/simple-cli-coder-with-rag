"""Tests for the ``Settings`` (pydantic-settings) class.

Pinned by ``agent-development/02-llm-client-adapter/tests.md``.

The settings layer reads three provider API keys and per-provider
``model`` / ``base_url`` values. The API key for ``default_provider``
must be non-empty at construction time; the other two keys are allowed
to be empty (``SecretStr("")``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from simple_cli_coder_with_rag.infrastructure.settings import Settings


def _settings_with(
    *,
    default_provider: str = "nvidia",
    nvidia: str = "nv-key",
    mistral: str = "ms-key",
    minimax: str = "mx-key",
) -> Settings:
    return Settings(
        default_provider=default_provider,  # type: ignore[arg-type]
        nvidia_api_key=SecretStr(nvidia),
        mistral_api_key=SecretStr(mistral),
        minimax_api_key=SecretStr(minimax),
    )


def test_settings_loads_nvidia_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "nv-env")
    monkeypatch.setenv("MISTRAL_API_KEY", "ms-env")
    monkeypatch.setenv("MINIMAX_API_KEY", "mx-env")
    settings = Settings()
    assert settings.nvidia_api_key.get_secret_value() == "nv-env"


def test_settings_loads_mistral_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "nv-env")
    monkeypatch.setenv("MISTRAL_API_KEY", "ms-env")
    monkeypatch.setenv("MINIMAX_API_KEY", "mx-env")
    settings = Settings()
    assert settings.mistral_api_key.get_secret_value() == "ms-env"


def test_settings_loads_minimax_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "nv-env")
    monkeypatch.setenv("MISTRAL_API_KEY", "ms-env")
    monkeypatch.setenv("MINIMAX_API_KEY", "mx-env")
    settings = Settings()
    assert settings.minimax_api_key.get_secret_value() == "mx-env"


def test_settings_loads_from_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "NVIDIA_API_KEY=nv-dotenv\nMISTRAL_API_KEY=ms-dotenv\nMINIMAX_API_KEY=mx-dotenv\n"
    )
    # Tell pydantic-settings to read this file via its _env_file argument
    # while keeping env vars out of the way.
    for var in ("NVIDIA_API_KEY", "MISTRAL_API_KEY", "MINIMAX_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    settings = Settings(_env_file=str(dotenv))
    assert settings.nvidia_api_key.get_secret_value() == "nv-dotenv"


def test_settings_rejects_empty_default_provider_key_nvidia() -> None:
    with pytest.raises(RuntimeError, match="nvidia"):
        _settings_with(default_provider="nvidia", nvidia="")


def test_settings_rejects_empty_default_provider_key_mistral() -> None:
    with pytest.raises(RuntimeError, match="mistral"):
        _settings_with(default_provider="mistral", mistral="")


def test_settings_rejects_empty_default_provider_key_minimax() -> None:
    with pytest.raises(RuntimeError, match="minimax"):
        _settings_with(default_provider="minimax", minimax="")


def test_settings_allows_empty_keys_for_inactive_providers() -> None:
    """Only the active provider's key must be present."""
    settings = Settings(
        default_provider="nvidia",  # type: ignore[arg-type]
        nvidia_api_key=SecretStr("nv"),
        mistral_api_key=SecretStr(""),
        minimax_api_key=SecretStr(""),
    )
    assert settings.mistral_api_key.get_secret_value() == ""
    assert settings.minimax_api_key.get_secret_value() == ""


def test_settings_default_provider() -> None:
    """``default_provider`` defaults to ``"nvidia"``."""
    settings = _settings_with()
    assert settings.default_provider == "nvidia"


def test_settings_repr_masks_keys() -> None:
    settings = _settings_with(nvidia="nv-secret", mistral="ms-secret", minimax="mx-secret")
    text = repr(settings)
    assert "nv-secret" not in text
    assert "ms-secret" not in text
    assert "mx-secret" not in text


def test_settings_str_masks_keys() -> None:
    settings = _settings_with(nvidia="nv-secret", mistral="ms-secret", minimax="mx-secret")
    text = str(settings)
    assert "nv-secret" not in text
    assert "ms-secret" not in text
    assert "mx-secret" not in text


def test_settings_uses_dotenv_when_present(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Confirm ``model_config.env_file = ".env"`` is honored by pydantic-settings."""
    # Move into an isolated working dir that has its own .env so we don't read
    # the project's real one.
    dotenv = tmp_path / ".env"
    dotenv.write_text("NVIDIA_API_KEY=nv-isolated\n")
    for var in ("NVIDIA_API_KEY", "MISTRAL_API_KEY", "MINIMAX_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    class _Src(BaseSettings):
        model_config = SettingsConfigDict(env_file=str(dotenv), extra="ignore")
        nvidia_api_key: str = ""

    src = _Src()
    assert src.nvidia_api_key == "nv-isolated"


def test_settings_extra_env_vars_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``extra="ignore"`` must not raise on unknown env vars."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nv")
    monkeypatch.setenv("TOTALLY_UNKNOWN_VAR", "ignored")
    settings = Settings()
    assert settings.nvidia_api_key.get_secret_value() == "nv"
