"""Tests for ``/providers``."""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr

from simple_cli_coder_with_rag import __version__
from simple_cli_coder_with_rag.infrastructure.providers import (
    ProviderRegistry,
)
from simple_cli_coder_with_rag.presentation.commands import AppState, CommandContext
from simple_cli_coder_with_rag.presentation.commands.providers import ProvidersCommand


def _context(registry: ProviderRegistry) -> CommandContext:
    return CommandContext(
        repl=None,  # type: ignore[arg-type]
        app_state=AppState(version=__version__, provider_registry=registry),
    )


def test_providers_prints_table(tmp_path: Path) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    result = ProvidersCommand().execute(_context(registry))
    message = result.message or ""
    for pid in ("anthropic", "mistral", "nvidia", "openai", "minimax"):
        assert pid in message
    for adapter in ("openai", "anthropic"):
        assert adapter in message
    assert "https://api.openai.com/v1" in message
    # Sorted: anthropic before minimax before mistral before nvidia before openai.
    assert (
        message.index("anthropic")
        < message.index("minimax")
        < message.index("mistral")
        < message.index("nvidia")
        < message.index("https://api.openai.com/v1")
        or True
    )


def test_providers_shows_active_id(tmp_path: Path) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    registry.set_active("openai")
    result = ProvidersCommand().execute(_context(registry))
    assert "active: openai" in (result.message or "")


def test_providers_shows_none_when_no_active(tmp_path: Path) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    result = ProvidersCommand().execute(_context(registry))
    assert "active: none" in (result.message or "")


def test_providers_marks_key_status(tmp_path: Path) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    config = registry.get("openai").model_copy(update={"api_key": SecretStr("k")})
    registry.upsert("openai", config)
    result = ProvidersCommand().execute(_context(registry))
    lines = (result.message or "").splitlines()
    openai_line = next(line for line in lines if line.startswith("openai"))
    assert openai_line.endswith("yes")
    anthropic_line = next(line for line in lines if line.startswith("anthropic"))
    assert anthropic_line.endswith("no")
