"""Pydantic models for the JSON provider registry.

The on-disk file (``providers.json`` under ``LocalPaths.data_dir()``) is a
:class:`ProvidersFile`; each entry is a :class:`ProviderConfig`. ``SecretStr``
masking keeps raw API keys out of ``repr`` / ``str`` / ``model_dump_json``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_serializer, field_validator

AdapterKind = Literal["openai", "anthropic"]


class ProviderConfig(BaseModel):
    """Connection details for one provider entry."""

    model_config = ConfigDict(extra="forbid")

    adapter: AdapterKind
    base_url: str = Field(min_length=1)
    default_model: str = Field(min_length=1)
    # The model's *input-token* budget; consumed by DO-12's SessionManager
    # for auto-compaction. Default keeps ad-hoc (custom) entries valid.
    context_window: int = Field(default=128_000, ge=1024)
    api_key: SecretStr = SecretStr("")

    @field_validator("base_url")
    @classmethod
    def _base_url_must_be_https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("base_url must start with 'https://'")
        return value

    @field_serializer("api_key")
    def _dump_api_key(self, value: SecretStr) -> str:
        """Persist the real secret to ``providers.json`` so it survives restart.

        ``SecretStr``'s default ``model_dump_json`` masks the value to
        ``"**********"``, which round-trips back as the literal string
        ``"**********"`` on disk — every subsequent LLM call then sends
        ``Bearer **********`` and gets ``401 Unauthorized``. We override
        here so the JSON registry actually stores the key. ``repr`` and
        ``str`` still mask via ``SecretStr``'s default behaviour, so logs
        and debug printing remain safe.
        """
        return value.get_secret_value()


class ProvidersFile(BaseModel):
    """Root document of ``providers.json``."""

    model_config = ConfigDict(extra="forbid")

    active_provider_id: str = ""
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)


__all__ = ["AdapterKind", "ProviderConfig", "ProvidersFile"]
