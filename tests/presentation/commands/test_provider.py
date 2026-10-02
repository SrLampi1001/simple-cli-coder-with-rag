"""Tests for ``/provider <id>``."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import SecretStr

from simple_cli_coder_with_rag import __version__
from simple_cli_coder_with_rag.domain.messages import AssistantTurn
from simple_cli_coder_with_rag.infrastructure.llm import OpenAILLMClient
from simple_cli_coder_with_rag.infrastructure.providers import ProviderRegistry
from simple_cli_coder_with_rag.presentation.commands import AppState, CommandContext
from simple_cli_coder_with_rag.presentation.commands.provider import ProviderCommand

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _context(args: str, registry: ProviderRegistry, app_state: AppState) -> CommandContext:
    return CommandContext(repl=None, app_state=app_state, args=args)  # type: ignore[arg-type]


def test_provider_switch_updates_registry_and_app_state(tmp_path: Path) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    config = registry.get("openai").model_copy(update={"api_key": SecretStr("k")})
    registry.upsert("openai", config)
    app_state = AppState(version=__version__, provider_registry=registry)

    ProviderCommand().execute(_context("openai", registry, app_state))

    assert registry.active_provider_id == "openai"
    assert isinstance(app_state.llm, OpenAILLMClient)


def test_provider_switch_unknown_id_returns_friendly_message(tmp_path: Path) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    app_state = AppState(version=__version__, provider_registry=registry)

    result = ProviderCommand().execute(_context("nope", registry, app_state))

    assert "unknown provider" in (result.message or "")


def test_provider_switch_with_unconfigured_key_warns_and_activates(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    app_state = AppState(version=__version__, provider_registry=registry)
    mocker.patch(
        "simple_cli_coder_with_rag.presentation.commands.provider.build_llm_client",
        return_value=mocker.MagicMock(),
    )
    # Give myproxy a valid https URL and model so build_llm_client can run.
    from simple_cli_coder_with_rag.infrastructure.providers import ProviderConfig

    registry.upsert(
        "myproxy",
        ProviderConfig(adapter="openai", base_url="https://x.example/v1", default_model="m"),
    )

    result = ProviderCommand().execute(_context("myproxy", registry, app_state))

    message = result.message or ""
    assert "warning" in message
    assert "myproxy" in message
    assert registry.active_provider_id == "myproxy"
    assert app_state.llm is not None


def test_provider_switch_rebuilds_knowledge_service_llm(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    from simple_cli_coder_with_rag.application.chunkers import FixedSizeChunker
    from simple_cli_coder_with_rag.application.compactor import Compactor
    from simple_cli_coder_with_rag.application.knowledge_service import KnowledgeService
    from simple_cli_coder_with_rag.application.session_store import SessionStore

    registry = ProviderRegistry(tmp_path / "providers.json")
    old_llm = mocker.MagicMock()
    old_llm.complete_with_tools.return_value = AssistantTurn(content="old", tool_calls=[])
    new_llm = mocker.MagicMock()
    new_llm.complete_with_tools.return_value = AssistantTurn(content="new", tool_calls=[])
    mocker.patch(
        "simple_cli_coder_with_rag.presentation.commands.provider.build_llm_client",
        return_value=new_llm,
    )

    knowledge = KnowledgeService(
        llm=old_llm,
        chat_model="m",
        session_store=SessionStore(root=tmp_path / "sessions"),
        compactor=Compactor(llm=old_llm, compactor_model="m"),
        chunker=FixedSizeChunker(),
    )
    app_state = AppState(
        version=__version__, provider_registry=registry, knowledge=knowledge, llm=old_llm
    )

    ProviderCommand().execute(_context("openai", registry, app_state))
    knowledge.chat("hi", history=[], recalled=[])

    new_llm.complete_with_tools.assert_called()
    old_llm.complete_with_tools.assert_not_called()
    # The switch also retargets the chat model to the new provider's default.
    assert knowledge._chat_model == "gpt-4o-mini"
