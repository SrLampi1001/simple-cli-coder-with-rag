"""``LLMClient`` factory: picks the adapter for a :class:`ProviderConfig`.

The composition root (``simple_cli_coder_with_rag.cli``) calls
:func:`build_llm_client` and stores the result on ``AppState``. The
application and presentation layers only see the resulting ``LLMClient`` —
vendor types never leak above this module.
"""

from __future__ import annotations

from simple_cli_coder_with_rag.domain.llm_client import LLMClient
from simple_cli_coder_with_rag.infrastructure.llm.anthropic_client import (
    AnthropicLLMClient,
)
from simple_cli_coder_with_rag.infrastructure.llm.openai_client import (
    OpenAILLMClient,
)
from simple_cli_coder_with_rag.infrastructure.providers.models import ProviderConfig


def build_llm_client(config: ProviderConfig) -> LLMClient:
    """Return an ``LLMClient`` for ``config``'s adapter kind."""
    if config.adapter == "openai":
        return OpenAILLMClient(
            api_key=config.api_key.get_secret_value(),
            base_url=config.base_url,
            default_model=config.default_model,
        )
    if config.adapter == "anthropic":
        return AnthropicLLMClient(
            api_key=config.api_key.get_secret_value(),
            base_url=config.base_url,
            default_model=config.default_model,
        )
    raise ValueError(f"unknown adapter kind: {config.adapter!r}")


__all__ = ["AnthropicLLMClient", "OpenAILLMClient", "build_llm_client"]
