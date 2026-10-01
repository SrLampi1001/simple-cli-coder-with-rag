"""Tests for ``CommandRegistry``."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from simple_cli_coder_with_rag.presentation.commands import CommandContext, CommandResult
from simple_cli_coder_with_rag.presentation.registry import CommandRegistry


@dataclass(frozen=True)
class _StubCommand:
    name: str
    summary: str

    def execute(self, context: CommandContext) -> CommandResult:
        return CommandResult(action="continue", message=f"ran {self.name}")


def test_registry_register_and_get(fresh_registry: CommandRegistry) -> None:
    cmd = _StubCommand(name="alpha", summary="first")
    fresh_registry.register(cmd)

    assert fresh_registry.get("alpha") is cmd


def test_registry_register_rejects_duplicate(fresh_registry: CommandRegistry) -> None:
    fresh_registry.register(_StubCommand(name="alpha", summary="first"))

    with pytest.raises(ValueError, match="alpha"):
        fresh_registry.register(_StubCommand(name="alpha", summary="dup"))


def test_registry_get_unknown_returns_none(fresh_registry: CommandRegistry) -> None:
    assert fresh_registry.get("nope") is None


def test_registry_unregister(fresh_registry: CommandRegistry) -> None:
    fresh_registry.register(_StubCommand(name="alpha", summary="first"))
    fresh_registry.unregister("alpha")

    assert fresh_registry.get("alpha") is None


def test_registry_names_sorted(fresh_registry: CommandRegistry) -> None:
    for name in ("gamma", "alpha", "beta"):
        fresh_registry.register(_StubCommand(name=name, summary=name))

    assert fresh_registry.names() == ["alpha", "beta", "gamma"]


def test_registry_all_returns_commands(fresh_registry: CommandRegistry) -> None:
    for name in ("gamma", "alpha", "beta"):
        fresh_registry.register(_StubCommand(name=name, summary=name))

    by_name = {cmd.name for cmd in fresh_registry.all()}
    assert by_name == {"alpha", "beta", "gamma"}
    assert len(fresh_registry.all()) == len(fresh_registry.names())
