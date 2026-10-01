"""Single source of truth for local data file paths.

The CLI's ``--reset`` flag and (later) the database default in
``infrastructure/settings`` both ask this module which files belong to a
local install. Keeping the enumeration here avoids path drift between
the two consumers and lets both layers import a downward-free dependency.
"""

from __future__ import annotations

from pathlib import Path

import platformdirs

_APP_NAME = "simple-cli-coder-with-rag"


class LocalPaths:
    """Resolve on-disk locations used by the CLI."""

    @staticmethod
    def data_dir() -> Path:
        """Return the per-user data directory as an absolute :class:`Path`."""
        return Path(platformdirs.user_data_dir(_APP_NAME)).resolve()

    @classmethod
    def reset_targets(cls) -> list[Path]:
        """Return every file the ``--reset`` flag would attempt to delete.

        Non-existing entries are filtered out so a fresh install does not
        raise. The list is sorted so output is deterministic.
        """
        data_dir = cls.data_dir()
        candidates: list[Path] = [
            data_dir / "db.sqlite",
            data_dir / "db.sqlite-shm",
            data_dir / "db.sqlite-wal",
            *sorted(data_dir.glob("sessions/*")),
        ]
        return [path for path in candidates if path.exists()]


__all__ = ["LocalPaths"]
