"""Command-pattern contracts for the REPL.

Built-in commands live in submodules of this package. The REPL
(:mod:`simple_cli_coder_with_rag.presentation.repl`) composes them via
:class:`CommandRegistry`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from simple_cli_coder_with_rag.application.knowledge_service import (
        KnowledgeService,
    )
    from simple_cli_coder_with_rag.domain.llm_client import LLMClient
    from simple_cli_coder_with_rag.domain.messages import Message
    from simple_cli_coder_with_rag.presentation.repl import Repl


@dataclass(frozen=True)
class AppState:
    """Mutable application state passed to commands and the REPL.

    ``Settings`` is **not** stored here: it is built once in the
    composition root and consumed by concrete adapters directly. The
    resulting ``LLMClient`` *is* stashed here so commands can reach it
    (DO-03 wires the chat loop; DO-04 wires the compactor).

    ``history`` is a list that is **mutated in place** by the REPL
    (``history.append(...)``, ``history[:] = history[-cap:]``). Despite
    the ``frozen=True`` dataclass, the list itself is mutable — the
    dataclass just refuses to reassign the field to a different list.

    ``knowledge`` is wired by the composition root in ``cli.py`` once
    the active provider's adapter is built. It defaults to ``None`` so
    unit tests that don't need an LLM can construct a bare ``AppState``.
    """

    version: str
    llm: LLMClient | None = None
    knowledge: KnowledgeService | None = None
    history: list[Message] = field(default_factory=list)
    history_cap: int = 20


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
