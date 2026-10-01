"""Tests for the ``LLMClient`` Protocol and ``LLMError`` exception.

Pinned by ``agent-development/02-llm-client-adapter/tests.md``.
"""

from __future__ import annotations

import pytest

from simple_cli_coder_with_rag.domain.llm_client import LLMClient, LLMError


def test_protocol_has_complete_method() -> None:
    """``LLMClient`` declares ``complete`` with the expected signature."""
    assert hasattr(LLMClient, "complete")


def test_protocol_has_complete_with_tools() -> None:
    """``LLMClient`` declares ``complete_with_tools`` for DO-10."""
    assert hasattr(LLMClient, "complete_with_tools")


def test_llm_error_exists() -> None:
    """``LLMError`` is a project-owned Exception subclass."""
    assert issubclass(LLMError, Exception)
    err = LLMError("boom")
    assert str(err) == "boom"


def test_llm_error_is_raising_exception() -> None:
    """``LLMError`` can be raised and caught as a normal ``Exception``."""
    with pytest.raises(LLMError, match="wrapped"):
        raise LLMError("wrapped")
