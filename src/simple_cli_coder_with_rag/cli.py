"""``coder`` entry point.

Responsibilities:

* parse ``--version`` / ``--help`` / ``--reset`` via :mod:`argparse`;
* on ``--reset``, wipe the local data directory **before** any logger or
  REPL state is touched (so a destructive run never races a live SQLite
  handle);
* otherwise, configure loguru to write to ``platformdirs.user_log_dir``
  and start the :class:`~simple_cli_coder_with_rag.presentation.repl.Repl`.
"""

from __future__ import annotations

import argparse
import sys

from simple_cli_coder_with_rag import __version__
from simple_cli_coder_with_rag.infrastructure.local_paths import LocalPaths
from simple_cli_coder_with_rag.infrastructure.logging import configure_logging
from simple_cli_coder_with_rag.presentation.commands import AppState
from simple_cli_coder_with_rag.presentation.commands.clear import ClearCommand
from simple_cli_coder_with_rag.presentation.commands.exit import ExitCommand
from simple_cli_coder_with_rag.presentation.commands.help import HelpCommand
from simple_cli_coder_with_rag.presentation.commands.version import VersionCommand
from simple_cli_coder_with_rag.presentation.registry import CommandRegistry
from simple_cli_coder_with_rag.presentation.repl import Repl


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="coder",
        description="Interactive coding assistant with optional RAG context.",
    )
    parser.add_argument("--version", action="store_true", help="print the package version and exit")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="wipe the local data directory after a y/N prompt",
    )
    return parser


def _build_registry() -> CommandRegistry:
    registry = CommandRegistry()
    registry.register(HelpCommand(registry))
    registry.register(ExitCommand())
    registry.register(ClearCommand())
    registry.register(VersionCommand())
    return registry


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a shell exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.reset:
        # Short-circuit: destructive path must not touch the logger or the
        # REPL, so it cannot race with a live SQLite connection.
        return _reset_local_data()

    if args.version:
        print(__version__)
        return 0

    configure_logging()

    app_state = AppState(version=__version__)
    registry = _build_registry()
    repl = Repl(registry=registry, app_state=app_state)
    repl.run()
    return 0


def _reset_local_data() -> int:
    """Wipe local data files after an interactive y/N prompt.

    Returns 0 whether the user confirms or aborts, and on an empty data
    directory. The REPL and the loguru file sink are intentionally not
    created here.
    """
    targets = LocalPaths.reset_targets()
    data_dir = LocalPaths.data_dir()
    print(f"This will delete {len(targets)} file(s) under {data_dir}:")
    for path in targets:
        print(f"  {path}")
    print("Continue? [y/N] ", end="", flush=True)
    answer = sys.stdin.readline().strip()
    if answer != "y":
        print("Aborted.")
        return 0
    for path in targets:
        path.unlink(missing_ok=True)
    print("Reset complete.")
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry only
    raise SystemExit(main())
