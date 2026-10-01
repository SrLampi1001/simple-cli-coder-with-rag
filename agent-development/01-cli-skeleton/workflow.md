# DO-01 workflow

## Subagent delegation

**One subagent.** The REPL, the registry, the command classes, and the entry point are tightly coupled — splitting risks interface drift between the command types, the registry, and the REPL.

### Context passed to the subagent

- `agent-development/README.md` (master).
- The four files in this folder.
- `docs/development-tools.md` §3 (architectural layers), §7 (CLI surface), §8 (logging doesn't go to the terminal).
- Nothing else.

## Web-search verification

Not required. `prompt_toolkit` is mature and the API used here (`PromptSession.prompt`, `prompt_toolkit.shortcuts.clear`) is stable across major versions. The version in `pyproject.toml` from DO-00 is sufficient.

## Steps

1. **Pre-flight.** `git status` is clean. The only untracked item is the `agent-development/` folder itself, which is committed at the end of the whole plan, not here.

2. **Read** `docs/development-tools.md` §3, §7, §8 only.

3. **Write the test files** from `tests.md` first. Confirm they fail (`uv run pytest -q` shows collection errors or failures for the new test modules).

4. **Add `__version__`** to `src/simple_cli_coder_with_rag/__init__.py`:
   ```python
   __version__: str = "0.1.0"
   __all__ = ["__version__"]
   ```

5. **Write `src/simple_cli_coder_with_rag/infrastructure/local_paths.py`** with `LocalPaths` (`data_dir()` + `reset_targets()`). This is the single source of truth for local data file paths. `--reset` (presentation) and DO-07's `Settings.db_path` default (infrastructure/settings) both consume it; do **not** hard-code `~/.local/share/...` elsewhere. Putting it in `infrastructure/` (rather than `presentation/`) lets DO-07 reuse it without a downward import.

6. **Write `src/simple_cli_coder_with_rag/presentation/commands/__init__.py`** with `Command`, `CommandContext`, `CommandResult`, and `AppState`. Use `typing.Protocol` for `Command`. Use `dataclasses.dataclass` (frozen) for `CommandContext`, `CommandResult`, `AppState`.

7. **Write `src/simple_cli_coder_with_rag/presentation/registry.py`** with `CommandRegistry`. The constructor takes no args; backing storage is a `dict[str, Command]`. `register` raises `ValueError` on duplicate.

8. **Write the four command modules** under `src/simple_cli_coder_with_rag/presentation/commands/`:
   - `help.py`: iterates `registry.all()`, formats `f"{c.name:<12} {c.summary}"` into a `message`.
   - `exit.py`: calls `context.repl.request_exit()`; returns `CommandResult(action="exit")`.
   - `clear.py`: calls `prompt_toolkit.shortcuts.clear(leave_current_page=True)`; returns `CommandResult(action="continue")`.
   - `version.py`: returns `CommandResult(action="continue", message=__version__)`.

9. **Write `src/simple_cli_coder_with_rag/presentation/repl.py`** with `Repl`. Use `prompt_toolkit.PromptSession`. Parse input: if it starts with `/`, look up `name = line[1:].split()[0]` in the registry; if found, call `command.execute(context)`, handle the returned `CommandResult` (break on `action == "exit"`); if not found, print `Unknown command: /foo`. If the input does not start with `/`, print `Type /help for available commands.`. The session prompt string is `">>> "`.

10. **Write `src/simple_cli_coder_with_rag/cli.py`**:
    ```python
    import argparse
    import sys
    from simple_cli_coder_with_rag import __version__
    from simple_cli_coder_with_rag.infrastructure.local_paths import LocalPaths
    from simple_cli_coder_with_rag.presentation.repl import Repl
    from simple_cli_coder_with_rag.presentation.registry import CommandRegistry
    from simple_cli_coder_with_rag.presentation.commands import (
        AppState, CommandContext,
    )
    from simple_cli_coder_with_rag.presentation.commands.help import HelpCommand
    # ... etc

    def main(argv: list[str] | None = None) -> int:
        parser = argparse.ArgumentParser(prog="coder")
        parser.add_argument("--version", action="store_true")
        parser.add_argument("--reset", action="store_true")
        args = parser.parse_args(argv)

        if args.reset:
            return _reset_local_data()

        if args.version:
            print(__version__)
            return 0

        registry = CommandRegistry()
        registry.register(HelpCommand(registry))
        registry.register(ExitCommand())
        registry.register(ClearCommand())
        registry.register(VersionCommand())

        app_state = AppState(version=__version__)
        repl = Repl(registry=registry, app_state=app_state)
        repl.run()
        return 0


    def _reset_local_data() -> int:
        """Wipe the local data dir after an interactive y/N prompt.

        Returns 0 either way (aborted = success; no files = already reset).
        The REPL and the loguru file sink are not initialized: a destructive
        one-shot shouldn't depend on logger file-handles or open the prompt loop.
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
    ```
    `LocalPaths.reset_targets()` is responsible for filtering non-existing paths, so `_reset_local_data` does not need to handle `FileNotFoundError`.

11. **Configure logging** in `cli.py` (or a small `infrastructure/logging.py`):
    - One `loguru.logger.add(sink=log_path, level="DEBUG", rotation="10 MB", retention="7 days")`.
    - **No** sink writes to stdout/stderr.
    - Remove the default `loguru` sink (`logger.remove(0)`) before adding the file sink.
    - The logger is only added **after** the `--reset` short-circuit, so a destructive flag run does not create an empty log file.

12. **Run the gate.** Every command in `objective.md` "Gate" section. All must exit 0.

13. **Smoke test manually (in a separate terminal, not committed):** `uv run coder` — type `/help`, then `/version`, then `/clear`, then `/exit`. All four behave as in the behavioral contract. Separately: create a stub `db.sqlite` and a session file under the data dir, then run `echo y | uv run coder --reset` — both files are gone. Run `echo | uv run coder --reset` — both files remain.

14. **Commit (suggested template — adapt to actual changes):**
    ```bash
    git add src/simple_cli_coder_with_rag/__init__.py \
            src/simple_cli_coder_with_rag/cli.py \
            src/simple_cli_coder_with_rag/infrastructure/local_paths.py \
            src/simple_cli_coder_with_rag/presentation \
            tests/presentation
    git status
    git commit -m "feat(cli): REPL with Command registry, help/exit/clear/version/reset

    - prompt_toolkit-based REPL in presentation/repl.py
    - Command Protocol + CommandRegistry (dict-backed, duplicate-registration rejected)
    - built-in commands: /help, /exit, /clear, /version
    - non-slash input prints 'Type /help for available commands.'
    - unknown slash command prints 'Unknown command: /foo'
    - loguru routed to platformdirs user_log_dir, no stdout/stderr sinks
    - argparse entry point: coder [--version] [--help] [--reset]
    - --reset wipes user_data_dir (DB + sessions) after an interactive y/N prompt;
        case-sensitive, default N, missing files count as success, REPL + logger
        are not initialized on the destructive path
    - infrastructure/local_paths.py is the single source of truth for local data
        file paths (consumed by --reset and DO-07's DB default)

    Tests in tests/presentation/ mirror the source layout.
    Behavioral, architectural, and schema contracts from contracts.md all pass."
    ```
    **Note:** The above message is a template. Edit the summary and bullet points to match what was actually implemented. If any planned feature was dropped, changed, or added, reflect that in the commit body.

15. **Post-flight.** `git status` clean. Single new commit on top of DO-00.

## Failure modes

- **`prompt_toolkit` overwrites our prints:** the failure is usually that the logger writes to stderr. Confirm `logger.remove(0)` was called before adding the file sink.
- **`mypy` complains about `PromptSession.prompt`:** add a `type: ignore[assignment]` per line; `prompt_toolkit`'s types are noisy. Do not blanket-ignore the whole module.
- **Test isolation:** every `test_repl_*` test must reset the registry. The `conftest.py` at `tests/presentation/` provides a `fresh_registry` fixture.
- **`--reset` deletes too much:** the most common mistake is globbing `*` instead of `sessions/*` and wiping the model cache. `LocalPaths.reset_targets()` must only enumerate `db.sqlite[-shm/-wal]` and `sessions/*`; never `*`.
- **`--reset` hangs waiting for stdin in a non-interactive shell:** that is the desired behavior (no TTY = no accidental destructive run). Document this in the README so users pipe `y\n` when they want to automate it.
- **`--reset` race with a running REPL:** `--reset` must short-circuit **before** any data files are opened; otherwise it can race with the live SQLite connection. Hence the early return in `main()` and the rule that `--reset` never initializes the REPL or the logger.
