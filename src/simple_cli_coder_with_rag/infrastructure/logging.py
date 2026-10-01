"""Loguru configuration — file sink only.

The default ``loguru`` sink writes to stderr; anything on stderr while
``prompt_toolkit`` owns the screen corrupts the prompt, so the default
sink is removed and replaced with a rotating file under
``platformdirs.user_log_dir``.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import platformdirs
from loguru import logger as _logger

_APP_NAME = "simple-cli-coder-with-rag"
_LOG_FILENAME = "app.log"


def _log_dir() -> Path:
    return Path(platformdirs.user_log_dir(_APP_NAME))


def configure_logging(*, log_dir: Path | None = None) -> Path:
    """Install the file sink. Returns the resolved log directory.

    Idempotent: the default stderr sink (always at index ``0`` on a
    fresh loguru logger) is removed if it is still present, and the
    file sink is then added. Subsequent calls in the same process
    succeed because the ``remove(0)`` is suppressed.

    Tests can still monkeypatch ``logger.add`` and ``logger.remove`` to
    observe calls without touching the filesystem.
    """
    target_dir = log_dir if log_dir is not None else _log_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    log_path = target_dir / _LOG_FILENAME
    # Remove the default stderr sink if it still exists. ``logger.remove(0)``
    # raises ``ValueError`` if index 0 is already gone.
    with contextlib.suppress(ValueError):
        _logger.remove(0)
    _logger.add(
        str(log_path),
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
    )
    return target_dir


__all__ = ["configure_logging"]
