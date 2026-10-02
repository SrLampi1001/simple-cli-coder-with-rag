"""Tests for ``KnowledgeService.chat`` with the tool-use loop (DO-10).

Pinned by ``agent-development/10-file-editing/tests.md``.

The ``LLMClient`` is replaced with a fake that returns ``AssistantTurn`` with
tool calls on the first call and a plain string on the second. A real
``SandboxedFileEditor`` is wired so the assertions cover the end-to-end
tool-loop behaviour (tool execution, message-shape contract, error
handling).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from simple_cli_coder_with_rag.application.chunkers.fixed_size import FixedSizeChunker
from simple_cli_coder_with_rag.application.compactor import Compactor
from simple_cli_coder_with_rag.application.file_editor.sandboxed_editor import (
    SandboxedFileEditor,
)
from simple_cli_coder_with_rag.application.knowledge_service import KnowledgeService
from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.domain.file_editor import PathNotAllowed
from simple_cli_coder_with_rag.domain.llm_client import LLMClient
from simple_cli_coder_with_rag.domain.messages import (
    AssistantMessage,
    AssistantTurn,
    Message,
    ToolCall,
    ToolResultMessage,
    ToolSpec,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


_READ_TOOL = ToolSpec(
    name="read",
    description="Read a file from the editor sandbox.",
    input_schema={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
)


class _FakeLLM:
    """Programmable ``LLMClient`` that returns a sequence of ``AssistantTurn`` values."""

    def __init__(self, turns: list[AssistantTurn]) -> None:
        self._turns = list(turns)
        self.calls: list[tuple[list[Message], list[ToolSpec]]] = []

    def complete(self, messages: list[Message], *, model: str) -> str:
        return self._turns[0].content if self._turns else ""

    def complete_with_tools(
        self,
        messages: list[Message],
        *,
        model: str,
        tools: list[ToolSpec],
    ) -> AssistantTurn:
        self.calls.append((list(messages), list(tools)))
        if not self._turns:
            return AssistantTurn(content="", tool_calls=[])
        return self._turns.pop(0)


def _build_service(
    tmp_path: Path,
    fake_llm: LLMClient,
    *,
    editor: SandboxedFileEditor | None = None,
    max_tool_rounds: int = 1,
) -> KnowledgeService:
    store = SessionStore(tmp_path)
    compactor = Compactor(llm=fake_llm, compactor_model="m")
    return KnowledgeService(
        llm=fake_llm,
        chat_model="m",
        session_store=store,
        compactor=compactor,
        chunker=FixedSizeChunker(),
        editor=editor,
        editor_max_tool_rounds=max_tool_rounds,
    )


# ---------------------------------------------------------------------------
# Tool-call happy path
# ---------------------------------------------------------------------------


def test_chat_executes_tool_call_and_returns_followup(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """``chat`` calls ``editor.read(path)``, feeds the result back into a second
    ``complete_with_tools`` call, and returns the follow-up text."""
    (tmp_path / "foo.txt").write_text("hello world", encoding="utf-8")
    editor = SandboxedFileEditor(root=tmp_path)

    fake_llm = _FakeLLM(
        turns=[
            AssistantTurn(
                content="",
                tool_calls=[
                    ToolCall(id="c1", name="read", arguments={"path": "foo.txt"}),
                ],
            ),
            AssistantTurn(content="I read the file: hello world", tool_calls=[]),
        ]
    )

    service = _build_service(tmp_path, fake_llm, editor=editor)
    result = service.chat("read foo.txt", history=[])

    assert result == "I read the file: hello world"
    assert len(fake_llm.calls) == 2


def test_chat_appends_assistant_turn_then_tool_result(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """The second ``complete_with_tools`` call receives the assistant's tool_use
    turn immediately followed by a ``ToolResultMessage`` carrying the read result.

    This pins the Anthropic-required ordering: ``tool_use`` -> ``tool_result``.
    """
    (tmp_path / "foo.txt").write_text("hi", encoding="utf-8")
    editor = SandboxedFileEditor(root=tmp_path)

    fake_llm = _FakeLLM(
        turns=[
            AssistantTurn(
                content="",
                tool_calls=[ToolCall(id="call-1", name="read", arguments={"path": "foo.txt"})],
            ),
            AssistantTurn(content="done", tool_calls=[]),
        ]
    )
    service = _build_service(tmp_path, fake_llm, editor=editor)
    service.chat("read foo.txt", history=[])

    # The second call's message list must end with the assistant tool_use turn
    # followed by a ToolResultMessage.
    second_messages = fake_llm.calls[1][0]
    assert second_messages[-2] == AssistantMessage(
        content="",
        tool_calls=[ToolCall(id="call-1", name="read", arguments={"path": "foo.txt"})],
    )
    assert second_messages[-1] == ToolResultMessage(tool_call_id="call-1", content="hi")


def test_chat_with_no_tool_calls_returns_first_response(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """When the first ``complete_with_tools`` returns ``tool_calls=[]``, ``chat``
    returns ``content`` directly without making a second call."""
    editor = SandboxedFileEditor(root=tmp_path)
    fake_llm = _FakeLLM(turns=[AssistantTurn(content="plain answer", tool_calls=[])])
    service = _build_service(tmp_path, fake_llm, editor=editor)

    result = service.chat("hi", history=[])

    assert result == "plain answer"
    assert len(fake_llm.calls) == 1


# ---------------------------------------------------------------------------
# Bounded tool loop
# ---------------------------------------------------------------------------


def test_chat_respects_max_tool_rounds(tmp_path: Path, mocker: MockerFixture) -> None:
    """``chat`` stops after ``editor_max_tool_rounds`` (1 by default), even if the
    follow-up response contains more tool calls.

    The follow-up tool call must NOT be executed.
    """
    (tmp_path / "foo.txt").write_text("a", encoding="utf-8")
    editor = SandboxedFileEditor(root=tmp_path)

    fake_llm = _FakeLLM(
        turns=[
            AssistantTurn(
                content="",
                tool_calls=[ToolCall(id="c1", name="read", arguments={"path": "foo.txt"})],
            ),
            # Worst case: the follow-up also wants to call a tool.
            AssistantTurn(
                content="partial answer",
                tool_calls=[ToolCall(id="c2", name="read", arguments={"path": "foo.txt"})],
            ),
        ]
    )
    service = _build_service(tmp_path, fake_llm, editor=editor, max_tool_rounds=1)
    result = service.chat("read foo.txt", history=[])

    # The service stops after one round and returns whatever it has.
    assert result == "partial answer"
    # Only the first follow-up response was consumed; the second tool call is ignored.
    assert len(fake_llm.calls) == 2
    assert fake_llm._turns == []  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Error handling: editor exceptions and malformed arguments are NOT re-raised
# ---------------------------------------------------------------------------


def test_chat_propagates_editor_errors(tmp_path: Path, mocker: MockerFixture) -> None:
    """When ``editor.read`` raises ``PathNotAllowed``, the service catches it and
    returns a readable error string as the assistant's text — the LLM sees the
    rejection and can explain it to the user."""
    editor = SandboxedFileEditor(root=tmp_path)

    fake_llm = _FakeLLM(
        turns=[
            AssistantTurn(
                content="",
                tool_calls=[ToolCall(id="c1", name="read", arguments={"path": "../foo"})],
            ),
            AssistantTurn(
                content="I tried to read ../foo but it is outside the sandbox.", tool_calls=[]
            ),
        ]
    )
    service = _build_service(tmp_path, fake_llm, editor=editor)
    result = service.chat("read ../foo", history=[])

    assert (
        "outside" in result.lower()
        or "not allowed" in result.lower()
        or "sandbox" in result.lower()
    )
    # The error string must be carried in the tool result, not raised.
    second_messages = fake_llm.calls[1][0]
    tool_result = second_messages[-1]
    assert isinstance(tool_result, ToolResultMessage)
    assert tool_result.tool_call_id == "c1"
    assert "not allowed" in tool_result.content.lower() or "outside" in tool_result.content.lower()


def test_chat_handles_malformed_tool_arguments(tmp_path: Path, mocker: MockerFixture) -> None:
    """A ``ToolCall.arguments`` missing required keys must NOT raise ``KeyError``;
    a readable error string is fed back into the LLM instead."""
    editor = SandboxedFileEditor(root=tmp_path)

    fake_llm = _FakeLLM(
        turns=[
            AssistantTurn(
                content="",
                tool_calls=[ToolCall(id="bad", name="read", arguments={})],  # no "path"
            ),
            AssistantTurn(content="ok", tool_calls=[]),
        ]
    )
    service = _build_service(tmp_path, fake_llm, editor=editor)
    result = service.chat("read", history=[])

    # No KeyError raised; the service returned something.
    assert isinstance(result, str)
    second_messages = fake_llm.calls[1][0]
    tool_result = second_messages[-1]
    assert isinstance(tool_result, ToolResultMessage)
    # The error string is informative enough to be useful to the LLM.
    assert tool_result.tool_call_id == "bad"
    assert tool_result.content  # non-empty error string


def test_chat_without_editor_returns_initial_response(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """When ``editor`` is ``None`` (legacy / test wiring) and the LLM returns a tool call,
    the service still returns a usable result — the tool call is reported as an
    error rather than crashing the REPL."""
    fake_llm = _FakeLLM(
        turns=[
            AssistantTurn(
                content="",
                tool_calls=[ToolCall(id="c1", name="read", arguments={"path": "foo.txt"})],
            ),
            AssistantTurn(content="final", tool_calls=[]),
        ]
    )
    service = _build_service(tmp_path, fake_llm, editor=None)
    result = service.chat("read foo.txt", history=[])

    assert isinstance(result, str)
    second_messages = fake_llm.calls[1][0]
    tool_result = second_messages[-1]
    assert isinstance(tool_result, ToolResultMessage)
    # A useful error string is propagated to the LLM (no editor wired).
    assert (
        "editor" in tool_result.content.lower() or "not configured" in tool_result.content.lower()
    )


def test_path_not_allowed_exception_propagated_through_tool_call(tmp_path: Path) -> None:
    """Sanity check on the editor itself: ``read("../foo")`` raises ``PathNotAllowed``."""
    editor = SandboxedFileEditor(root=tmp_path)
    with pytest.raises(PathNotAllowed):
        editor.read("../foo")
