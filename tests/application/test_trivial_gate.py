"""Tests for ``TrivialGate`` (DO-09).

Pinned by ``agent-development/09-recall-integration/tests.md``. The gate
is the latency tip from ``OBJECTIVES.md``: trivial prompts (short and
few-worded) must skip the vector store round-trip entirely.

The boundary tests (``test_boundary_chars``, ``test_boundary_words``)
pin the inclusive ``<=`` semantics — easy to off-by-one if the
implementation flips a ``>``.
"""

from __future__ import annotations

from simple_cli_coder_with_rag.application.trivial_gate import TrivialGate


def test_short_string_is_trivial() -> None:
    """``"hi"`` (2 chars, 1 word) is trivial."""
    gate = TrivialGate()
    assert gate.is_trivial("hi") is True


def test_short_word_count_is_trivial() -> None:
    """``"how are you"`` (12 chars, 3 words) is trivial — under both bounds."""
    gate = TrivialGate()
    assert gate.is_trivial("how are you") is True


def test_long_prompt_is_not_trivial() -> None:
    """``"why does ModuleNotFoundError happen for foo"`` is not trivial — long and > 4 words."""
    gate = TrivialGate()
    assert gate.is_trivial("why does ModuleNotFoundError happen for foo") is False


def test_long_string_is_not_trivial() -> None:
    """A single 25-character word fails the char bound — NOT trivial despite 1 word.

    This is the regression guard for using ``and`` instead of ``or``:
    a single long word would be classified trivial under ``or`` (1 word <= 4)
    but must not be.
    """
    gate = TrivialGate()
    assert gate.is_trivial("a" * 25) is False


def test_boundary_chars() -> None:
    """``"a" * 20`` (exactly 20 chars, 1 word) is trivial — boundary inclusive."""
    gate = TrivialGate()
    assert gate.is_trivial("a" * 20) is True


def test_boundary_words() -> None:
    """``"one two three four"`` (exactly 4 words) is trivial — boundary inclusive."""
    gate = TrivialGate()
    assert gate.is_trivial("one two three four") is True


def test_empty_string_is_trivial() -> None:
    """Empty string: 0 chars <= 20 and 0 words <= 4 — trivial."""
    gate = TrivialGate()
    assert gate.is_trivial("") is True


def test_default_bounds_match_objective() -> None:
    """The default constructor pins the OBJECTIVES latency tip: 20 chars / 4 words."""
    gate = TrivialGate()
    # A 21-char prompt is no longer trivial under the default char bound.
    assert gate.is_trivial("a" * 21) is False
    # A 5-word prompt of any length is no longer trivial under the default word bound.
    assert gate.is_trivial("one two three four five") is False


def test_custom_bounds_are_honoured() -> None:
    """``max_chars`` / ``max_words`` are configurable — useful for tests, not used in prod."""
    gate = TrivialGate(max_chars=5, max_words=1)
    assert gate.is_trivial("hello world") is False  # 2 words > 1
    assert gate.is_trivial("hello") is True  # 5 chars, 1 word — both bounds hold
    assert gate.is_trivial("hi!") is True  # 3 chars, 1 word — both bounds hold


def test_long_string_with_short_word_count_is_not_trivial() -> None:
    """Regression guard: ``and`` semantics. A 30-char, 1-word prompt is NOT trivial."""
    gate = TrivialGate()
    # 30 chars > 20, but only 1 word <= 4. ``and`` makes this NOT trivial.
    assert gate.is_trivial("a" * 30) is False
