"""Provider registry subpackage: JSON config + Pydantic models."""

from __future__ import annotations

from simple_cli_coder_with_rag.infrastructure.providers.errors import (
    NoActiveProviderError,
    UnknownProviderError,
)
from simple_cli_coder_with_rag.infrastructure.providers.models import (
    AdapterKind,
    ProviderConfig,
    ProvidersFile,
)
from simple_cli_coder_with_rag.infrastructure.providers.registry import ProviderRegistry

__all__ = [
    "AdapterKind",
    "NoActiveProviderError",
    "ProviderConfig",
    "ProviderRegistry",
    "ProvidersFile",
    "UnknownProviderError",
]
