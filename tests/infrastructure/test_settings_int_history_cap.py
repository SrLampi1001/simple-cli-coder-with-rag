"""Tests for ``Settings.int_history_cap``.

Pinned by ``agent-development/12-session-memory-and-saved-chats/tests.md``.

The cap ``int_history_cap`` controls the size of the rolling
conversation window in *turns*; one turn = one user + one
assistant message = 2 messages. The default is ``10`` (= 20
messages), matching the TL literal acceptance criterion
"10 most recent user/assistant messages".

The validator (``ge=1, le=100``) is the only guard rail: a value
of ``0`` would create a window that can never hold any message;
a value of ``200`` would defeat the cap's purpose.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from simple_cli_coder_with_rag.infrastructure.settings import Settings


def _settings(**overrides: object) -> Settings:
    """Return a ``Settings`` instance."""
    return Settings(**overrides)  # type: ignore[arg-type]


def test_int_history_cap_default_is_ten() -> None:
    """The default cap is ``10`` turns (= 20 messages)."""
    settings = _settings()

    assert settings.int_history_cap == 10


def test_int_history_cap_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """``INT_HISTORY_CAP=7`` in the env is honoured by ``Settings()``."""
    monkeypatch.setenv("INT_HISTORY_CAP", "7")

    settings = Settings()

    assert settings.int_history_cap == 7


def test_int_history_cap_accepts_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """``INT_HISTORY_CAP=1`` is the smallest valid cap (= 1 turn)."""
    monkeypatch.setenv("INT_HISTORY_CAP", "1")

    settings = Settings()

    assert settings.int_history_cap == 1


def test_int_history_cap_accepts_one_hundred(monkeypatch: pytest.MonkeyPatch) -> None:
    """``INT_HISTORY_CAP=100`` is the largest valid cap."""
    monkeypatch.setenv("INT_HISTORY_CAP", "100")

    settings = Settings()

    assert settings.int_history_cap == 100


def test_int_history_cap_rejects_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """``INT_HISTORY_CAP=0`` raises ``ValidationError`` (no messages can fit)."""
    monkeypatch.setenv("INT_HISTORY_CAP", "0")

    with pytest.raises(ValidationError):
        Settings()


def test_int_history_cap_rejects_too_large(monkeypatch: pytest.MonkeyPatch) -> None:
    """``INT_HISTORY_CAP=101`` raises ``ValidationError`` (above the upper bound)."""
    monkeypatch.setenv("INT_HISTORY_CAP", "101")

    with pytest.raises(ValidationError):
        Settings()


def test_int_history_cap_rejects_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    """``INT_HISTORY_CAP=-1`` raises ``ValidationError`` (below the lower bound)."""
    monkeypatch.setenv("INT_HISTORY_CAP", "-1")

    with pytest.raises(ValidationError):
        Settings()


def test_int_history_cap_accepts_explicit_constructor_value() -> None:
    """``Settings(int_history_cap=4)`` overrides the default."""
    settings = _settings(int_history_cap=4)

    assert settings.int_history_cap == 4
