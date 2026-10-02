"""Mocked-SDK tests for ``OpenAILLMClient`` (official ``openai`` SDK)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from simple_cli_coder_with_rag.domain.llm_client import LLMError
from simple_cli_coder_with_rag.domain.messages import UserMessage
from simple_cli_coder_with_rag.infrastructure.llm.openai_client import OpenAILLMClient

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _message_mock(content: str = "hi", tool_calls: object = None) -> MagicMock:
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls
    return message


def _response(message: MagicMock) -> MagicMock:
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def test_complete_returns_text(mocker: MockerFixture) -> None:
    fake = mocker.patch("openai.OpenAI")
    client = fake.return_value
    client.chat.completions.create.return_value = _response(_message_mock("hi"))

    adapter = OpenAILLMClient(api_key="k", base_url="https://x", default_model="m")
    assert adapter.complete([UserMessage(content="yo")], model="m") == "hi"


def test_complete_passes_messages_and_model(mocker: MockerFixture) -> None:
    fake = mocker.patch("openai.OpenAI")
    client = fake.return_value
    client.chat.completions.create.return_value = _response(_message_mock("ok"))

    adapter = OpenAILLMClient(api_key="k", base_url="https://x", default_model="m")
    adapter.complete([UserMessage(content="yo")], model="m")

    call = client.chat.completions.create.call_args
    assert call.kwargs["model"] == "m"
    assert call.kwargs["messages"] == [{"role": "user", "content": "yo"}]


def test_complete_passes_base_url(mocker: MockerFixture) -> None:
    fake = mocker.patch("openai.OpenAI")
    OpenAILLMClient(api_key="k", base_url="https://x", default_model="m")
    assert fake.call_args.kwargs["base_url"] == "https://x"


def test_complete_wraps_vendor_error(mocker: MockerFixture) -> None:
    import openai

    fake = mocker.patch("openai.OpenAI")
    client = fake.return_value
    client.chat.completions.create.side_effect = openai.OpenAIError("boom")

    adapter = OpenAILLMClient(api_key="k", base_url="https://x", default_model="m")
    with pytest.raises(LLMError, match="OpenAI error: boom"):
        adapter.complete([UserMessage(content="yo")], model="m")


def test_complete_with_tools_returns_assistant_turn(mocker: MockerFixture) -> None:
    fake = mocker.patch("openai.OpenAI")
    client = fake.return_value
    tool_call = MagicMock()
    tool_call.id = "1"
    tool_call.function.name = "read"
    tool_call.function.arguments = '{"path":"x"}'
    client.chat.completions.create.return_value = _response(
        _message_mock("ok", tool_calls=[tool_call])
    )

    adapter = OpenAILLMClient(api_key="k", base_url="https://x", default_model="m")
    turn = adapter.complete_with_tools([UserMessage(content="yo")], model="m", tools=[])

    assert turn.content == "ok"
    assert len(turn.tool_calls) == 1
    assert turn.tool_calls[0].id == "1"
    assert turn.tool_calls[0].name == "read"
    assert turn.tool_calls[0].arguments == {"path": "x"}


def test_complete_with_tools_parses_arguments_json_string(mocker: MockerFixture) -> None:
    fake = mocker.patch("openai.OpenAI")
    client = fake.return_value
    tool_call = MagicMock()
    tool_call.id = "1"
    tool_call.function.name = "read"
    tool_call.function.arguments = '{"a":1}'
    client.chat.completions.create.return_value = _response(
        _message_mock("", tool_calls=[tool_call])
    )

    adapter = OpenAILLMClient(api_key="k", base_url="https://x", default_model="m")
    turn = adapter.complete_with_tools([UserMessage(content="yo")], model="m", tools=[])
    assert turn.tool_calls[0].arguments == {"a": 1}


def test_complete_with_tools_keeps_arguments_when_dict(mocker: MockerFixture) -> None:
    fake = mocker.patch("openai.OpenAI")
    client = fake.return_value
    tool_call = MagicMock()
    tool_call.id = "1"
    tool_call.function.name = "read"
    tool_call.function.arguments = {"key": "value"}
    client.chat.completions.create.return_value = _response(
        _message_mock("", tool_calls=[tool_call])
    )

    adapter = OpenAILLMClient(api_key="k", base_url="https://x", default_model="m")
    turn = adapter.complete_with_tools([UserMessage(content="yo")], model="m", tools=[])
    assert turn.tool_calls[0].arguments == {"key": "value"}


def test_complete_with_tools_handles_empty_arguments(mocker: MockerFixture) -> None:
    fake = mocker.patch("openai.OpenAI")
    client = fake.return_value
    tool_call = MagicMock()
    tool_call.id = "1"
    tool_call.function.name = "read"
    tool_call.function.arguments = ""
    client.chat.completions.create.return_value = _response(
        _message_mock("", tool_calls=[tool_call])
    )

    adapter = OpenAILLMClient(api_key="k", base_url="https://x", default_model="m")
    turn = adapter.complete_with_tools([UserMessage(content="yo")], model="m", tools=[])
    assert turn.tool_calls[0].arguments == {}


def test_complete_with_tools_empty_tool_calls(mocker: MockerFixture) -> None:
    fake = mocker.patch("openai.OpenAI")
    client = fake.return_value
    client.chat.completions.create.return_value = _response(_message_mock("ok", tool_calls=None))

    adapter = OpenAILLMClient(api_key="k", base_url="https://x", default_model="m")
    turn = adapter.complete_with_tools([UserMessage(content="yo")], model="m", tools=[])
    assert turn.content == "ok"
    assert turn.tool_calls == []


def test_adapter_holds_one_client_instance(mocker: MockerFixture) -> None:
    fake = mocker.patch("openai.OpenAI")
    OpenAILLMClient(api_key="k", base_url="https://x", default_model="m")
    assert fake.call_count == 1
