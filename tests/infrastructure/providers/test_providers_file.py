"""Round-trip and secrets-handling tests for ``ProvidersFile``."""

from __future__ import annotations

import json

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


def test_providers_file_persists_real_api_key_on_disk() -> None:
    """The JSON dump stores the real key so it survives restart.

    Pydantic's ``SecretStr`` defaults to masking values to ``"**********"``
    in ``model_dump_json`` — that round-trips back as the literal string
    ``"**********"`` on reload and every subsequent LLM call would send
    ``Bearer **********`` (401 Unauthorized). The registry overrides the
    serializer to dump the real key while keeping ``repr`` / ``str``
    masked via the underlying ``SecretStr``.
    """
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
    raw = json.loads(doc.model_dump_json())
    assert raw["providers"]["p"]["api_key"] == "sk-supersecret"

    reloaded = ProvidersFile.model_validate_json(doc.model_dump_json())
    assert reloaded.providers["p"].api_key.get_secret_value() == "sk-supersecret"


def test_providers_file_empty_api_key_round_trips_empty() -> None:
    doc = ProvidersFile(
        providers={"p": ProviderConfig(adapter="openai", base_url="https://x", default_model="m")}
    )
    raw = json.loads(doc.model_dump_json())
    assert raw["providers"]["p"]["api_key"] == ""
    reloaded = ProvidersFile.model_validate_json(doc.model_dump_json())
    assert reloaded.providers["p"].api_key.get_secret_value() == ""


def test_providers_file_forbids_extra_keys() -> None:
    with pytest.raises(ValidationError):
        ProvidersFile(unknown_field="x")  # type: ignore[call-arg]
