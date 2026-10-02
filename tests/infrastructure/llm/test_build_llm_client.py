"""Tests for ``build_llm_client`` adapter dispatch."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from simple_cli_coder_with_rag.infrastructure.llm import (
    AnthropicLLMClient,
    OpenAILLMClient,
    build_llm_client,
)
from simple_cli_coder_with_rag.infrastructure.providers import ProviderConfig


def test_build_llm_client_returns_openai_for_openai_adapter() -> None:
    config = ProviderConfig(
        adapter="openai", base_url="https://x", default_model="m", api_key=SecretStr("k")
    )
    assert isinstance(build_llm_client(config), OpenAILLMClient)


def test_build_llm_client_returns_anthropic_for_anthropic_adapter() -> None:
    config = ProviderConfig(
        adapter="anthropic", base_url="https://x", default_model="m", api_key=SecretStr("k")
    )
    assert isinstance(build_llm_client(config), AnthropicLLMClient)


def test_build_llm_client_unknown_adapter_raises() -> None:
    config = ProviderConfig(
        adapter="openai", base_url="https://x", default_model="m", api_key=SecretStr("k")
    )
    bogus = config.model_copy(update={"adapter": "bogus"})
    with pytest.raises(ValueError, match="unknown adapter kind"):
        build_llm_client(bogus)
