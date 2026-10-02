"""Pre-populated providers written on first run.

Default models/endpoints were verified during DO-02's smoke test and the
DO-11 web-search step (see the DO-11 commit body's ``provider-research:``
block). API keys start empty — the user adds them with ``/connect <id>``.
"""

from __future__ import annotations

from simple_cli_coder_with_rag.infrastructure.providers.models import ProviderConfig

DEFAULT_PROVIDERS: dict[str, ProviderConfig] = {
    "nvidia": ProviderConfig(
        adapter="openai",
        base_url="https://integrate.api.nvidia.com/v1",
        default_model="openai/gpt-oss-20b",
        context_window=128_000,
    ),
    "mistral": ProviderConfig(
        adapter="openai",
        base_url="https://api.mistral.ai/v1",
        default_model="mistral-code-latest",
        context_window=128_000,
    ),
    "minimax": ProviderConfig(
        adapter="anthropic",
        base_url="https://api.minimax.io/anthropic",
        default_model="MiniMax-M3",
        context_window=128_000,
    ),
    "anthropic": ProviderConfig(
        adapter="anthropic",
        base_url="https://api.anthropic.com",
        default_model="claude-3-5-sonnet-latest",
        context_window=200_000,
    ),
    "openai": ProviderConfig(
        adapter="openai",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        context_window=128_000,
    ),
}

__all__ = ["DEFAULT_PROVIDERS"]
