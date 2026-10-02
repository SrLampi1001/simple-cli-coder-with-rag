"""Pydantic model tests for ``ProviderConfig``."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from simple_cli_coder_with_rag.infrastructure.providers import (
    ProviderConfig,
    ProviderRegistry,
)


def test_provider_config_openai() -> None:
    config = ProviderConfig(
        adapter="openai",
        base_url="https://x",
        default_model="m",
        context_window=128000,
        api_key=SecretStr("k"),
    )
    assert ProviderConfig.model_validate(config.model_dump()) == config


def test_provider_config_anthropic() -> None:
    config = ProviderConfig(
        adapter="anthropic",
        base_url="https://x",
        default_model="m",
        context_window=200000,
        api_key=SecretStr("k"),
    )
    assert ProviderConfig.model_validate(config.model_dump()) == config


def test_provider_config_rejects_unknown_adapter() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            adapter="cohere", base_url="https://x", default_model="m", context_window=128000
        )  # type: ignore[arg-type]


def test_provider_config_rejects_non_https_base_url() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            adapter="openai", base_url="http://x", default_model="m", context_window=128000
        )


def test_provider_config_rejects_empty_model() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            adapter="openai", base_url="https://x", default_model="", context_window=128000
        )


def test_provider_config_rejects_context_window_below_minimum() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            adapter="openai", base_url="https://x", default_model="m", context_window=512
        )


def test_provider_config_default_context_window_is_anthropic_two_hundred(tmp_path) -> None:
    ProviderRegistry(tmp_path / "providers.json")
    manifest = (tmp_path / "providers.json").read_text()
    import json

    data = json.loads(manifest)
    assert data["providers"]["anthropic"]["context_window"] == 200_000


def test_provider_config_repr_masks_api_key() -> None:
    config = ProviderConfig(
        adapter="openai", base_url="https://x", default_model="m", api_key=SecretStr("sk-literal")
    )
    assert "sk-literal" not in repr(config)
    assert "sk-literal" not in str(config)


def test_provider_config_forbids_extra_keys() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(
            adapter="openai",
            base_url="https://x",
            default_model="m",
            context_window=128000,
            typo="x",
        )  # type: ignore[call-arg]


def test_provider_config_default_api_key_is_empty_secret() -> None:
    config = ProviderConfig(adapter="openai", base_url="https://x", default_model="m")
    assert config.api_key == SecretStr("")
    assert config.api_key.get_secret_value() == ""
