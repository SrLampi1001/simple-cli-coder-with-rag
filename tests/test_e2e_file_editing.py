"""Smoke tests for the ``scripts/`` real-API test runners.

Thin wrappers so the standard test suite can collect them without
hitting the network. Running the actual end-to-end tests requires the
user's ``.env`` to be configured with a valid API key; do that manually
with::

    uv run python scripts/e2e_file_editing.py --provider mistral
    uv run python scripts/e2e_semantic_retrieval.py --provider mistral
"""

from __future__ import annotations

import importlib


def test_e2e_file_editing_script_imports() -> None:
    """The file-editing E2E script imports cleanly and exposes ``main``."""
    module = importlib.import_module("scripts.e2e_file_editing")
    assert callable(getattr(module, "main", None))


def test_e2e_file_editing_script_has_docstring() -> None:
    """The file-editing E2E script's module docstring describes the run instructions."""
    module = importlib.import_module("scripts.e2e_file_editing")
    assert module.__doc__
    assert "uv run python scripts/e2e_file_editing.py" in module.__doc__


def test_e2e_semantic_retrieval_script_imports() -> None:
    """The semantic-retrieval E2E script imports cleanly and exposes ``main``."""
    module = importlib.import_module("scripts.e2e_semantic_retrieval")
    assert callable(getattr(module, "main", None))


def test_e2e_semantic_retrieval_script_has_docstring() -> None:
    """The semantic-retrieval E2E script's module docstring describes the run instructions."""
    module = importlib.import_module("scripts.e2e_semantic_retrieval")
    assert module.__doc__
    assert "uv run python scripts/e2e_semantic_retrieval.py" in module.__doc__
