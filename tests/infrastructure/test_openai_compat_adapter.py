"""Tests for the urllib-based OpenAI-compat ``LLMClient`` adapter.

Used for NVIDIA NIM (cloud) and Mistral — both expose
``POST /v1/chat/completions`` with ``Authorization: Bearer <key>``.
No new runtime dependency: stdlib ``urllib.request`` only.

Pinned by ``agent-development/02-llm-client-adapter/tests.md``.
"""

from __future__ import annotations

import json
import urllib.error
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from simple_cli_coder_with_rag.domain.llm_client import LLMError
from simple_cli_coder_with_rag.domain.messages import (
    AssistantTurn,
    SystemMessage,
    ToolSpec,
    UserMessage,
)
from simple_cli_coder_with_rag.infrastructure.llm.openai_compat import (
    OpenAICompatLLMClient,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _fake_urlopen_response(payload: dict[str, object]) -> MagicMock:
    """Return a mock that quacks like the return value of ``urllib.request.urlopen``."""
    body = json.dumps(payload).encode("utf-8")
    response = MagicMock()
    response.read.return_value = body
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def _ok_response(text: str) -> MagicMock:
    return _fake_urlopen_response(
        {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
    )


def _patch_urlopen(mocker: MockerFixture, response: MagicMock) -> MagicMock:
    return mocker.patch(
        "simple_cli_coder_with_rag.infrastructure.llm.openai_compat.urllib.request.urlopen",
        return_value=response,
    )


def test_complete_returns_text(mocker: MockerFixture) -> None:
    _patch_urlopen(mocker, _ok_response("hi from mock"))

    adapter = OpenAICompatLLMClient(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="nv-key",
        default_model="meta/llama-3.1-70b-instruct",
    )

    result = adapter.complete([UserMessage(content="hi")], model="meta/llama-3.1-70b-instruct")

    assert result == "hi from mock"


def test_complete_passes_messages_and_model(mocker: MockerFixture) -> None:
    mock_urlopen = _patch_urlopen(mocker, _ok_response("ok"))

    adapter = OpenAICompatLLMClient(
        base_url="https://api.mistral.ai/v1",
        api_key="ms-key",
        default_model="mistral-large-latest",
    )
    adapter.complete(
        [
            SystemMessage(content="sys-prompt"),
            UserMessage(content="hi"),
        ],
        model="mistral-large-latest",
    )

    mock_urlopen.assert_called_once()
    request_obj = mock_urlopen.call_args.args[0]
    body = json.loads(request_obj.data.decode("utf-8"))

    # The model is in the JSON body, not in the URL.
    assert body["model"] == "mistral-large-latest"
    # System messages stay in the messages array (OpenAI-style), in order.
    assert body["messages"] == [
        {"role": "system", "content": "sys-prompt"},
        {"role": "user", "content": "hi"},
    ]
    # The URL targets /v1/chat/completions under the configured base URL.
    assert request_obj.full_url == "https://api.mistral.ai/v1/chat/completions"
    # The Authorization header uses Bearer (OpenAI-compatible auth).
    assert request_obj.get_header("Authorization") == "Bearer ms-key"


def test_complete_wraps_vendor_error(mocker: MockerFixture) -> None:
    # Simulate the urllib layer raising on the HTTP call.
    mocker.patch(
        "simple_cli_coder_with_rag.infrastructure.llm.openai_compat.urllib.request.urlopen",
        side_effect=urllib.error.URLError("network down"),
    )

    adapter = OpenAICompatLLMClient(
        base_url="https://api.mistral.ai/v1",
        api_key="ms-key",
        default_model="mistral-large-latest",
    )

    with pytest.raises(LLMError):
        adapter.complete([UserMessage(content="hi")], model="mistral-large-latest")


def test_complete_wraps_http_error(mocker: MockerFixture) -> None:
    # HTTPError is a special URLError subclass that carries an HTTPResponse.
    err = urllib.error.HTTPError(
        url="https://api.mistral.ai/v1/chat/completions",
        code=500,
        msg="server error",
        hdrs=None,  # type: ignore[arg-type]
        fp=None,
    )
    mocker.patch(
        "simple_cli_coder_with_rag.infrastructure.llm.openai_compat.urllib.request.urlopen",
        side_effect=err,
    )

    adapter = OpenAICompatLLMClient(
        base_url="https://api.mistral.ai/v1",
        api_key="ms-key",
        default_model="mistral-large-latest",
    )

    with pytest.raises(LLMError):
        adapter.complete([UserMessage(content="hi")], model="mistral-large-latest")


def test_complete_with_tools_stub_returns_assistant_turn(mocker: MockerFixture) -> None:
    _patch_urlopen(mocker, _ok_response("tool-aware reply"))

    adapter = OpenAICompatLLMClient(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="nv-key",
        default_model="meta/llama-3.1-70b-instruct",
    )
    turn = adapter.complete_with_tools(
        [UserMessage(content="hi")],
        model="meta/llama-3.1-70b-instruct",
        tools=[ToolSpec(name="read_file", description="d", input_schema={"type": "object"})],
    )

    assert isinstance(turn, AssistantTurn)
    assert turn.content == "tool-aware reply"
    assert turn.tool_calls == []


def test_adapter_holds_one_client_instance(mocker: MockerFixture) -> None:
    """The adapter must construct its HTTP client (or equivalent state) exactly once.

    Since this adapter is stateless urllib, we verify the no-construction-side-
    effects property: instantiating the adapter does not call urlopen or open
    any persistent connection.
    """
    mock_urlopen = mocker.patch(
        "simple_cli_coder_with_rag.infrastructure.llm.openai_compat.urllib.request.urlopen",
        return_value=_ok_response("ok"),
    )

    adapter = OpenAICompatLLMClient(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="nv-key",
        default_model="meta/llama-3.1-70b-instruct",
    )
    # Construction must not have hit the network.
    assert mock_urlopen.call_count == 0

    # The first complete call should produce exactly one URL open.
    adapter.complete([UserMessage(content="hi")], model="meta/llama-3.1-70b-instruct")
    assert mock_urlopen.call_count == 1


def test_adapter_uses_provider_base_url(mocker: MockerFixture) -> None:
    mock_urlopen = _patch_urlopen(mocker, _ok_response("ok"))

    adapter = OpenAICompatLLMClient(
        base_url="https://api.mistral.ai/v1",
        api_key="ms-key",
        default_model="mistral-large-latest",
    )
    adapter.complete([UserMessage(content="hi")], model="mistral-large-latest")

    request_obj = mock_urlopen.call_args.args[0]
    assert request_obj.full_url.startswith("https://api.mistral.ai/v1/")


def test_complete_parses_first_choice_content(mocker: MockerFixture) -> None:
    """When the response carries multiple choices, take ``choices[0]``."""
    payload = {
        "choices": [
            {"message": {"role": "assistant", "content": "first"}},
            {"message": {"role": "assistant", "content": "second"}},
        ]
    }
    _patch_urlopen(mocker, _fake_urlopen_response(payload))

    adapter = OpenAICompatLLMClient(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key="nv-key",
        default_model="meta/llama-3.1-70b-instruct",
    )
    assert (
        adapter.complete([UserMessage(content="hi")], model="meta/llama-3.1-70b-instruct")
        == "first"
    )
