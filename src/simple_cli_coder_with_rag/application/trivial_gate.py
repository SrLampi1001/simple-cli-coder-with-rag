"""Trivial-request gate that short-circuits recall for short prompts.

The gate is the **first latency tip** from ``OBJECTIVES.md`` ("Skip
retrieval when the request is trivial — a cheap length/keyword gate").
Sitting in the application layer in front of
:class:`~simple_cli_coder_with_rag.application.recall_coordinator.RecallCoordinator`,
it keeps the cheapest of all recall paths — a vector-store round-trip —
from ever firing on a one-word user prompt.

Design notes:

* **Both bounds use ``and``, not ``or``.** A single 25-character word
  (e.g. an API key pasted by mistake) has ``len(words) == 1 <= 4`` and
  would wrongly count as trivial under ``or``. The ``and`` semantics
  pin the OFFICIAL definition of "trivial" from the OBJECTIVES — short
  enough **and** with few enough tokens.
* **Inclusive boundaries.** ``<=`` on both bounds so a 20-character or
  4-word prompt is trivial. The contract is the budget, not the floor.
* **Empty string is trivial** (``0`` chars, ``0`` words). The REPL
  already strips empty input before reaching the chat path, but the
  defensive default is correct in isolation.
* **No state.** The gate is a pure function of the prompt and the two
  constructor bounds. Tests can construct it freely; production wires
  one instance at startup via :class:`pydantic_settings.BaseSettings`.

Architectural note: this module imports from :mod:`domain` only (it
imports nothing). It is part of the application layer and may be
extended at the composition root in ``cli.py`` without violating the
``layered-architecture`` ``import-linter`` contract.
"""

from __future__ import annotations


class TrivialGate:
    """Return ``True`` when a prompt is short enough to skip retrieval.

    Parameters
    ----------
    max_chars:
        Inclusive upper bound on ``len(prompt)``. Defaults to ``20`` —
        the OBJECTIVES latency tip's "short prompt" budget.
    max_words:
        Inclusive upper bound on ``len(prompt.split())``. Defaults to
        ``4`` — matches the OBJECTIVES tip.

    Both bounds must hold for the prompt to be classified trivial.
    """

    def __init__(self, *, max_chars: int = 20, max_words: int = 4) -> None:
        if max_chars <= 0:
            raise ValueError(f"max_chars must be > 0, got {max_chars}")
        if max_words <= 0:
            raise ValueError(f"max_words must be > 0, got {max_words}")
        self._max_chars = max_chars
        self._max_words = max_words

    def is_trivial(self, prompt: str) -> bool:
        """Return ``True`` iff the prompt is short enough **and** has few enough words.

        ``and`` (not ``or``): a single 25-character word has 1 word <= 4
        but 25 chars > 20 and is therefore **not** trivial. The DO-09
        contract ``test_long_string_is_not_trivial`` pins this.
        """
        return len(prompt) <= self._max_chars and len(prompt.split()) <= self._max_words


__all__ = ["TrivialGate"]
