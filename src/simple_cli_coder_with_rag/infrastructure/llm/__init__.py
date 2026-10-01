"""``LLMClient`` factory: builds the adapter for ``Settings.default_provider``.

The composition root (``simple_cli_coder_with_rag.cli``) calls
:func:`build_llm_client` once at startup and stores the result on
``AppState``. The application and presentation layers only see the resulting
``LLMClient`` — vendor types never leak above this module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from simple_cli_coder_with_rag.domain.llm_client import LLMClient
from simple_cli_coder_with_rag.infrastructure.llm.anthropic_compat import (
    AnthropicCompatLLMClient,
)
from simple_cli_coder_with_rag.infrastructure.llm.openai_compat import (
    OpenAICompatLLMClient,
)

if TYPE_CHECKING:
    from simple_cli_coder_with_rag.infrastructure.settings import Settings


# Default endpoints discovered during DO-02's web-search step.
# Per-provider ``base_url`` in Settings (if set) overrides these.
_DEFAULT_BASE_URLS: dict[str, str] = {
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "mistral": "https://api.mistral.ai/v1",
    "minimax": "https://api.minimax.io/anthropic",
}

# Which adapter class to use per provider.
# ``"anthropic"`` -> Anthropic SDK; ``"openai_compat"`` -> urllib /v1/chat/completions.
_ADAPTERS: dict[str, str] = {
    "nvidia": "openai_compat",
    "mistral": "openai_compat",
    "minimax": "anthropic",
}


def build_llm_client(settings: Settings) -> LLMClient:
    """Return an ``LLMClient`` for ``settings.default_provider``.

    One adapter instance per provider — the composition root can call this
    three times if it wants all three built, but only the result for the
    active provider is wired into ``AppState``.
    """
    provider = settings.default_provider
    base_url = _resolve_base_url(settings, provider)
    api_key = _resolve_api_key(settings, provider)
    default_model = _resolve_model(settings, provider)
    adapter_kind = _ADAPTERS[provider]

    if adapter_kind == "anthropic":
        return AnthropicCompatLLMClient(
            api_key=api_key, base_url=base_url, default_model=default_model
        )
    if adapter_kind == "openai_compat":
        return OpenAICompatLLMClient(
            api_key=api_key, base_url=base_url, default_model=default_model
        )
    raise ValueError(f"unknown adapter kind for provider {provider!r}: {adapter_kind}")


def _resolve_base_url(settings: Settings, provider: str) -> str:
    raw = getattr(settings, f"{provider}_base_url")
    if raw:
        return raw
    return _DEFAULT_BASE_URLS[provider]


def _resolve_api_key(settings: Settings, provider: str) -> str:
    secret = getattr(settings, f"{provider}_api_key")
    return secret.get_secret_value()


def _resolve_model(settings: Settings, provider: str) -> str:
    return getattr(settings, f"{provider}_model")


__all__ = ["build_llm_client"]
