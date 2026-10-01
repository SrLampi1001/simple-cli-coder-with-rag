"""Command-pattern contracts for the REPL.

Built-in commands live in submodules of this package. The REPL
(:mod:`simple_cli_coder_with_rag.presentation.repl`) composes them via
:class:`CommandRegistry`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from simple_cli_coder_with_rag.domain.llm_client import LLMClient
    from simple_cli_coder_with_rag.presentation.repl import Repl


@dataclass(frozen=True)
class AppState:
    """Mutable application state passed to commands.

    ``Settings`` is **not** stored here: it is built once in the
    composition root and consumed by concrete adapters directly. The
    resulting ``LLMClient`` *is* stashed here so commands can reach it
    (DO-03 wires the chat loop; DO-04 wires the compactor).
    """

    version: str
    llm: LLMClient | None = None


@dataclass(frozen=True)
class CommandContext:
    """Per-invocation context handed to a :class:`Command`."""

    repl: Repl
    app_state: AppState


@dataclass(frozen=True)
class CommandResult:
    """Outcome of executing a :class:`Command`."""

    action: Literal["continue", "exit"] = "continue"
    message: str | None = field(default=None)


class Command(Protocol):
    """Minimal contract every REPL command implements."""

    name: str
    summary: str

    def execute(self, context: CommandContext) -> CommandResult: ...


__all__ = ["AppState", "Command", "CommandContext", "CommandResult"]
