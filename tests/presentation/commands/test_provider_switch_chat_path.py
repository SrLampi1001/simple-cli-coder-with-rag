"""REPL-level tests for provider switching and the no-provider path."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from simple_cli_coder_with_rag import __version__
from simple_cli_coder_with_rag.application.chunkers import FixedSizeChunker
from simple_cli_coder_with_rag.application.compactor import Compactor
from simple_cli_coder_with_rag.application.knowledge_service import KnowledgeService
from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.domain.messages import AssistantTurn
from simple_cli_coder_with_rag.infrastructure.providers import ProviderRegistry
from simple_cli_coder_with_rag.presentation.commands import AppState
from simple_cli_coder_with_rag.presentation.commands.exit import ExitCommand
from simple_cli_coder_with_rag.presentation.commands.provider import ProviderCommand
from simple_cli_coder_with_rag.presentation.registry import CommandRegistry
from simple_cli_coder_with_rag.presentation.repl import Repl

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _patch_prompt(monkeypatch: pytest.MonkeyPatch, inputs: list[str]) -> None:
    from prompt_toolkit import PromptSession

    iterator = iter(inputs)

    def fake_prompt(self: object, *args: object, **kwargs: object) -> str:
        try:
            return next(iterator)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr(PromptSession, "prompt", fake_prompt)


def test_repl_chat_after_provider_switch_uses_new_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    registry.set_active("anthropic")

    anthropic_llm = mocker.MagicMock()
    anthropic_llm.complete_with_tools.return_value = AssistantTurn(content="a", tool_calls=[])
    openai_llm = mocker.MagicMock()
    openai_llm.complete_with_tools.return_value = AssistantTurn(content="o", tool_calls=[])
    mocker.patch(
        "simple_cli_coder_with_rag.presentation.commands.provider.build_llm_client",
        return_value=openai_llm,
    )

    knowledge = KnowledgeService(
        llm=anthropic_llm,
        chat_model="m",
        session_store=SessionStore(root=tmp_path / "sessions"),
        compactor=Compactor(llm=anthropic_llm, compactor_model="m"),
        chunker=FixedSizeChunker(),
    )
    app_state = AppState(
        version=__version__,
        llm=anthropic_llm,
        knowledge=knowledge,
        provider_registry=registry,
    )
    command_registry = CommandRegistry()
    command_registry.register(ExitCommand())
    command_registry.register(ProviderCommand())

    _patch_prompt(monkeypatch, ["/provider openai", "hello", "/exit"])
    Repl(registry=command_registry, app_state=app_state).run()

    openai_llm.complete_with_tools.assert_called()
    anthropic_llm.complete_with_tools.assert_not_called()


def test_repl_chat_without_active_provider_returns_friendly_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mocker: MockerFixture,
) -> None:
    from simple_cli_coder_with_rag.cli import _NoProviderLLMClient

    registry = ProviderRegistry(tmp_path / "providers.json")
    llm = _NoProviderLLMClient()
    knowledge = KnowledgeService(
        llm=llm,
        chat_model="",
        session_store=SessionStore(root=tmp_path / "sessions"),
        compactor=Compactor(llm=llm, compactor_model=""),
        chunker=FixedSizeChunker(),
    )
    app_state = AppState(
        version=__version__, llm=llm, knowledge=knowledge, provider_registry=registry
    )
    command_registry = CommandRegistry()
    command_registry.register(ExitCommand())

    _patch_prompt(monkeypatch, ["hello", "/exit"])
    Repl(registry=command_registry, app_state=app_state).run()

    captured = capsys.readouterr().out
    assert "No active provider" in captured


def _stub_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from simple_cli_coder_with_rag.infrastructure import local_paths

    monkeypatch.setattr(local_paths.LocalPaths, "data_dir", classmethod(lambda cls: tmp_path))


def test_composition_root_prints_seed_message_on_first_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_data_dir(monkeypatch, tmp_path)

    from prompt_toolkit import PromptSession

    def raise_eof(self: object, *args: object, **kwargs: object) -> str:
        raise EOFError

    monkeypatch.setattr(PromptSession, "prompt", raise_eof)

    from simple_cli_coder_with_rag import cli

    exit_code = cli.main([])

    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "wrote " in captured
    assert "/providers.json" in captured
    assert "5 pre-populated providers" in captured
    assert "/connect <id> to add one" in captured
    assert str(tmp_path.joinpath("providers.json")) in captured


def test_composition_root_does_not_print_seed_message_on_second_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_data_dir(monkeypatch, tmp_path)

    from prompt_toolkit import PromptSession

    def raise_eof(self: object, *args: object, **kwargs: object) -> str:
        raise EOFError

    monkeypatch.setattr(PromptSession, "prompt", raise_eof)

    from simple_cli_coder_with_rag import cli

    cli.main([])
    capsys.readouterr()
    exit_code = cli.main([])

    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "5 pre-populated providers" not in captured


def test_composition_root_seed_message_is_exactly_one_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_data_dir(monkeypatch, tmp_path)

    from prompt_toolkit import PromptSession

    def raise_eof(self: object, *args: object, **kwargs: object) -> str:
        raise EOFError

    monkeypatch.setattr(PromptSession, "prompt", raise_eof)

    from simple_cli_coder_with_rag import cli

    cli.main([])

    captured = capsys.readouterr().out
    seed_lines = [line for line in captured.splitlines() if "wrote " in line]
    assert len(seed_lines) == 1
    assert "pre-populated providers" in seed_lines[0]
