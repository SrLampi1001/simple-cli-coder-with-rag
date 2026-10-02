"""Tests for ``/connect``."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from simple_cli_coder_with_rag import __version__
from simple_cli_coder_with_rag.domain.llm_client import LLMError
from simple_cli_coder_with_rag.infrastructure.providers import ProviderRegistry
from simple_cli_coder_with_rag.presentation.commands import AppState, CommandContext
from simple_cli_coder_with_rag.presentation.commands.connect import ConnectCommand

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _context(args: str, registry: ProviderRegistry) -> CommandContext:
    return CommandContext(
        repl=None,  # type: ignore[arg-type]
        app_state=AppState(version=__version__, provider_registry=registry),
        args=args,
    )


def _stub_client(mocker: MockerFixture, reply: str = "pong") -> object:
    client = mocker.MagicMock()
    client.complete.return_value = reply
    mocker.patch(
        "simple_cli_coder_with_rag.presentation.commands.connect.build_llm_client",
        return_value=client,
    )
    return client


def test_connect_existing_provider_writes_back_after_validating_key(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    _stub_client(mocker)
    mocker.patch("getpass.getpass", return_value="sk-test")

    result = ConnectCommand().execute(_context("openai", registry))

    assert registry.get("openai").api_key.get_secret_value() == "sk-test"
    assert "connected openai (adapter=openai, model=gpt-4o-mini)" in (result.message or "")
    assert "no validation" not in (result.message or "")


def test_connect_existing_provider_does_not_write_back_on_validation_failure(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    client = mocker.MagicMock()
    client.complete.side_effect = LLMError("nope")
    mocker.patch(
        "simple_cli_coder_with_rag.presentation.commands.connect.build_llm_client",
        return_value=client,
    )
    mocker.patch("getpass.getpass", return_value="sk-test")

    result = ConnectCommand().execute(_context("openai", registry))

    assert registry.get("openai").api_key.get_secret_value() == ""
    assert "validation failed" in (result.message or "")


def test_connect_existing_provider_no_validate_skips_round_trip(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    client = mocker.MagicMock()
    client.complete.side_effect = AssertionError("must not be called")
    mocker.patch(
        "simple_cli_coder_with_rag.presentation.commands.connect.build_llm_client",
        return_value=client,
    )
    mocker.patch("getpass.getpass", return_value="sk-test")

    result = ConnectCommand().execute(_context("openai --no-validate", registry))

    assert registry.get("openai").api_key.get_secret_value() == "sk-test"
    assert client.complete.call_count == 0
    assert "no validation" in (result.message or "")


def test_connect_existing_provider_no_validate_writes_bad_key(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    client = mocker.MagicMock()
    client.complete.side_effect = LLMError("bad key")
    mocker.patch(
        "simple_cli_coder_with_rag.presentation.commands.connect.build_llm_client",
        return_value=client,
    )
    mocker.patch("getpass.getpass", return_value="bogus-key")

    ConnectCommand().execute(_context("openai --no-validate", registry))

    assert registry.get("openai").api_key.get_secret_value() == "bogus-key"
    assert client.complete.call_count == 0


def test_connect_new_provider_creates_entry(tmp_path: Path, mocker: MockerFixture) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    _stub_client(mocker)
    mocker.patch("getpass.getpass", return_value="sk-test")

    ConnectCommand().execute(
        _context(
            "--new myproxy --adapter openai --base-url https://x.example/v1 --model my-model",
            registry,
        )
    )

    assert registry.get("myproxy").default_model == "my-model"


def test_connect_new_provider_rejects_http_base_url(tmp_path: Path, mocker: MockerFixture) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    mocker.patch("getpass.getpass", return_value="sk-test")

    result = ConnectCommand().execute(
        _context(
            "--new myproxy --adapter openai --base-url http://x.example/v1 --model m", registry
        )
    )

    assert "https://" in (result.message or "")
    from simple_cli_coder_with_rag.infrastructure.providers import UnknownProviderError

    with pytest.raises(UnknownProviderError):
        registry.get("myproxy")


def test_connect_new_provider_rejects_unknown_adapter(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    mocker.patch("getpass.getpass", return_value="sk-test")

    result = ConnectCommand().execute(
        _context(
            "--new myproxy --adapter cohere --base-url https://x.example/v1 --model m", registry
        )
    )

    assert "unknown adapter" in (result.message or "")


def test_connect_unknown_id_returns_friendly_message(tmp_path: Path, mocker: MockerFixture) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")

    result = ConnectCommand().execute(_context("nope", registry))

    assert result.message == "unknown provider 'nope'. Run /providers to see what's available."
    assert result.action == "continue"


def test_connect_does_not_echo_key(tmp_path: Path, mocker: MockerFixture) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    _stub_client(mocker)
    mocker.patch("getpass.getpass", return_value="sk-test")

    result = ConnectCommand().execute(_context("openai", registry))

    assert "sk-test" not in (result.message or "")


def test_connect_on_active_provider_rebuilds_live_client(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """After /connect on the active provider, the running adapter must hold the NEW key."""
    registry = ProviderRegistry(tmp_path / "providers.json")
    registry.set_active("openai")
    fresh_client = mocker.MagicMock()
    fresh_client.complete.return_value = "pong"
    mocker.patch(
        "simple_cli_coder_with_rag.presentation.commands.connect.build_llm_client",
        return_value=fresh_client,
    )
    mocker.patch("getpass.getpass", return_value="sk-new")

    app_state = AppState(version=__version__, provider_registry=registry, llm=mocker.MagicMock())
    context = CommandContext(repl=None, app_state=app_state, args="openai")  # type: ignore[arg-type]

    ConnectCommand().execute(context)

    assert app_state.llm is fresh_client
