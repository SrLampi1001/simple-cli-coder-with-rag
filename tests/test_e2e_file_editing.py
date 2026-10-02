"""Smoke test for the ``scripts/e2e_file_editing.py`` real-API test runner.

This is a thin wrapper that the standard test suite can collect without
hitting the network: it imports the module and asserts the main entry
point exists. Running the actual end-to-end test requires the user's
``.env`` to be configured with a valid API key; do that manually with::

    uv run python scripts/e2e_file_editing.py
"""

from __future__ import annotations

import importlib


def test_e2e_script_imports() -> None:
    """The E2E script imports cleanly and exposes ``main``."""
    module = importlib.import_module("scripts.e2e_file_editing")
    assert callable(getattr(module, "main", None))


def test_e2e_script_has_docstring() -> None:
    """The E2E script's module docstring describes the run instructions."""
    module = importlib.import_module("scripts.e2e_file_editing")
    assert module.__doc__
    assert "uv run python scripts/e2e_file_editing.py" in module.__doc__
