"""Tests pinning the composition root's wiring of ``Settings`` and ``LLMClient``.

Pinned by ``agent-development/02-llm-client-adapter/tests.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from simple_cli_coder_with_rag.domain.llm_client import LLMClient
from simple_cli_coder_with_rag.presentation.commands import AppState

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_app_state_has_llm_field() -> None:
    """``AppState`` must expose an ``llm`` field that defaults to ``None``."""
    state = AppState(version="0.1.0")
    assert hasattr(state, "llm")
    assert state.llm is None


def test_app_state_accepts_an_llm_client() -> None:
    fake_client = MagicMock(spec=LLMClient)
    state = AppState(version="0.1.0", llm=fake_client)
    assert state.llm is fake_client


def test_composition_root_wires_settings_and_client(
    monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    """``main([])`` instantiates Settings, builds the active adapter, and stashes it.

    With ``Repl.run`` patched out and a non-empty API key for the default
    provider, ``app_state.llm`` must end up populated with a non-``None``
    ``LLMClient`` instance.
    """
    from prompt_toolkit import PromptSession

    # Skip the REPL loop immediately.
    def raise_eof(self: object, *args: object, **kwargs: object) -> str:
        raise EOFError

    monkeypatch.setattr(PromptSession, "prompt", raise_eof)

    # Make sure the active provider's key is non-empty and the Anthropic SDK
    # class is patched (so no network call).
    monkeypatch.setenv("DEFAULT_PROVIDER", "minimax")
    monkeypatch.setenv("MINIMAX_API_KEY", "mx-test")

    mocker.patch(
        "anthropic.Anthropic",
        return_value=MagicMock(),
    )

    # Patch out Repl.run so the test exits immediately after main() wires state.
    repl_run_calls = {"n": 0}

    def fake_run(self: object) -> None:
        repl_run_calls["n"] += 1

    from simple_cli_coder_with_rag.presentation import repl as repl_module

    monkeypatch.setattr(repl_module.Repl, "run", fake_run)

    # Capture the AppState instance via a sentinel on the Repl.
    captured: dict[str, AppState] = {}

    original_init = repl_module.Repl.__init__

    def spy_init(self: object, *args: object, **kwargs: object) -> None:
        original_init(self, *args, **kwargs)  # type: ignore[arg-type]
        captured["state"] = self._app_state  # type: ignore[attr-defined]

    monkeypatch.setattr(repl_module.Repl, "__init__", spy_init)

    from simple_cli_coder_with_rag import cli

    exit_code = cli.main([])
    assert exit_code == 0
    assert repl_run_calls["n"] == 1
    assert "state" in captured, "Repl was never instantiated"

    state = captured["state"]
    assert state.llm is not None
    # ``LLMClient`` is a ``typing.Protocol`` without ``@runtime_checkable``,
    # so ``isinstance`` raises. Use duck-typing instead.
    assert hasattr(state.llm, "complete")
    assert hasattr(state.llm, "complete_with_tools")
    assert callable(state.llm.complete)
    assert callable(state.llm.complete_with_tools)
