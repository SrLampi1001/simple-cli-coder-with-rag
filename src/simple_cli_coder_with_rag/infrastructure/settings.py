"""Pydantic-settings configuration for the three LLM providers.

Three secrets (``NVIDIA_API_KEY``, ``MISTRAL_API_KEY``, ``MINIMAX_API_KEY``)
are loaded from the environment (or the ``.env`` file). Each provider also
has a default ``*_model`` (overridable via env) and an optional ``*_base_url``
(``None`` means "use the adapter's built-in default", so users only set it
when self-hosting).

Validation contract (DO-02):

* The API key for ``default_provider`` **must** be non-empty at construction
  time — a hard ``RuntimeError`` if it isn't. The other two keys are allowed
  to be empty so a single-provider install does not require dummy values for
  the others.
* ``__repr__`` / ``__str__`` mask every key. The literal string of a key must
  never appear in either output.
"""

from __future__ import annotations

from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["nvidia", "mistral", "minimax"]


class Settings(BaseSettings):
    """Per-provider configuration loaded from environment / ``.env``."""

    # Secrets. Defaults to empty so construction without env vars works for
    # the *inactive* providers; the active provider's key is checked below.
    nvidia_api_key: SecretStr = SecretStr("")
    mistral_api_key: SecretStr = SecretStr("")
    minimax_api_key: SecretStr = SecretStr("")

    default_provider: Provider = "nvidia"

    # Per-provider model defaults. Override via NVIDIA_MODEL, MISTRAL_MODEL,
    # MINIMAX_MODEL in .env. Defaults chosen during the DO-03 real-API
    # smoke test: the previous defaults (``meta/llama-3.1-70b-instruct`` /
    # ``mistral-large-latest``) return HTTP 410 Gone / HTTP 403 (tier not
    # allowed) from the providers on the test account. The current defaults
    # were verified to respond correctly to a chat completion call.
    nvidia_model: str = "meta/llama-3.2-11b-vision-instruct"
    mistral_model: str = "mistral-code-latest"
    minimax_model: str = "MiniMax-M3"

    # Optional per-provider base URL. ``None`` means "use the adapter's
    # built-in default", which is the provider's own first-party endpoint.
    nvidia_base_url: str | None = None
    mistral_base_url: str | None = None
    minimax_base_url: str | None = None

    # The model used by the REPL chat path. Empty string (default) means
    # "fall back to the active provider's per-provider default", so a user
    # who never overrides ``CHAT_MODEL`` still gets a sensible model. The
    # composition root resolves the empty-string case against
    # ``getattr(settings, f"{default_provider}_model")``.
    chat_model: str = ""

    # The model used by the ``/learn`` compaction pipeline. Empty string
    # (default) means "fall back to the active provider's per-provider
    # default", same pattern as ``chat_model`` above. Override via the
    # ``COMPACTOR_MODEL`` env var.
    compactor_model: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def model_post_init(self, __context: object) -> None:
        """Fail-fast on an empty API key for the *active* provider only."""
        active = self._active_key()
        if active is None or not active.get_secret_value():
            raise RuntimeError(
                f"{self.default_provider} API key is required (set "
                f"{self._active_env_var()} in the environment or .env)."
            )

    def _active_key(self) -> SecretStr | None:
        return {
            "nvidia": self.nvidia_api_key,
            "mistral": self.mistral_api_key,
            "minimax": self.minimax_api_key,
        }.get(self.default_provider)

    def _active_env_var(self) -> str:
        return {
            "nvidia": "NVIDIA_API_KEY",
            "mistral": "MISTRAL_API_KEY",
            "minimax": "MINIMAX_API_KEY",
        }[self.default_provider]

    def __repr__(self) -> str:
        """Mask every API key in the ``repr`` output."""
        return (
            f"Settings(default_provider={self.default_provider!r}, "
            "nvidia_api_key=***, mistral_api_key=***, minimax_api_key=***)"
        )

    def __str__(self) -> str:
        """``str(settings)`` mirrors ``repr`` so accidental string formatting
        never leaks a key either."""
        return self.__repr__()


__all__ = ["Provider", "Settings"]
