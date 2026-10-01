"""Shared fixtures for presentation-layer tests.

The `fresh_registry` fixture gives each test an isolated ``CommandRegistry``
so registered commands do not leak between tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from simple_cli_coder_with_rag.presentation.registry import CommandRegistry


@pytest.fixture
def fresh_registry() -> CommandRegistry:
    """Return a brand-new ``CommandRegistry`` for the test."""
    from simple_cli_coder_with_rag.presentation.registry import CommandRegistry

    return CommandRegistry()
