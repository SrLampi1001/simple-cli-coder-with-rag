"""Round-trip and secrets-masking tests for ``ProvidersFile``."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from simple_cli_coder_with_rag.infrastructure.providers import (
    ProviderConfig,
    ProvidersFile,
)


def test_providers_file_empty() -> None:
    doc = ProvidersFile()
    assert doc.active_provider_id == ""
    assert doc.providers == {}
    assert ProvidersFile.model_validate(doc.model_dump()) == doc


def test_providers_file_dump_masks_api_keys() -> None:
    doc = ProvidersFile(
        providers={
            "p": ProviderConfig(
                adapter="openai",
                base_url="https://x",
                default_model="m",
                api_key=SecretStr("sk-supersecret"),
            )
        }
    )
    dumped = doc.model_dump_json()
    assert "sk-supersecret" not in dumped


def test_providers_file_forbids_extra_keys() -> None:
    with pytest.raises(ValidationError):
        ProvidersFile(unknown_field="x")  # type: ignore[call-arg]
