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

5. **Write `src/simple_cli_coder_with_rag/presentation/commands/__init__.py`** with `Command`, `CommandContext`, `CommandResult`, and `AppState`. Use `typing.Protocol` for `Command`. Use `dataclasses.dataclass` (frozen) for `CommandContext`, `CommandResult`, `AppState`.

6. **Write `src/simple_cli_coder_with_rag/presentation/registry.py`** with `CommandRegistry`. The constructor takes no args; backing storage is a `dict[str, Command]`. `register` raises `ValueError` on duplicate.

7. **Write the four command modules** under `src/simple_cli_coder_with_rag/presentation/commands/`:
   - `help.py`: iterates `registry.all()`, formats `f"{c.name:<12} {c.summary}"` into a `message`.
   - `exit.py`: calls `context.repl.request_exit()`; returns `CommandResult(action="exit")`.
   - `clear.py`: calls `prompt_toolkit.shortcuts.clear(leave_current_page=True)`; returns `CommandResult(action="continue")`.
   - `version.py`: returns `CommandResult(action="continue", message=__version__)`.

8. **Write `src/simple_cli_coder_with_rag/presentation/repl.py`** with `Repl`. Use `prompt_toolkit.PromptSession`. Parse input: if it starts with `/`, look up `name = line[1:].split()[0]` in the registry; if found, call `command.execute(context)`, handle the returned `CommandResult` (break on `action == "exit"`); if not found, print `Unknown command: /foo`. If the input does not start with `/`, print `Type /help for available commands.`. The session prompt string is `">>> "`.

9. **Write `src/simple_cli_coder_with_rag/cli.py`**:
   ```python
   import argparse
   from simple_cli_coder_with_rag import __version__
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
       args = parser.parse_args(argv)
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
   ```

10. **Configure logging** in `cli.py` (or a small `infrastructure/logging.py`):
    - One `loguru.logger.add(sink=log_path, level="DEBUG", rotation="10 MB", retention="7 days")`.
    - **No** sink writes to stdout/stderr.
    - Remove the default `loguru` sink (`logger.remove(0)`) before adding the file sink.

11. **Run the gate.** Every command in `objective.md` "Gate" section. All must exit 0.

12. **Smoke test manually (in a separate terminal, not committed):** `uv run coder` — type `/help`, then `/version`, then `/clear`, then `/exit`. All four behave as in the behavioral contract.

13. **Commit:**
    ```bash
    git add src/simple_cli_coder_with_rag/__init__.py \
            src/simple_cli_coder_with_rag/cli.py \
            src/simple_cli_coder_with_rag/presentation \
            tests/presentation
    git status
    git commit -m "feat(cli): REPL with Command registry, help/exit/clear/version

    - prompt_toolkit-based REPL in presentation/repl.py
    - Command Protocol + CommandRegistry (dict-backed, duplicate-registration rejected)
    - built-in commands: /help, /exit, /clear, /version
    - non-slash input prints 'Type /help for available commands.'
    - unknown slash command prints 'Unknown command: /foo'
    - loguru routed to platformdirs user_log_dir, no stdout/stderr sinks
    - argparse entry point: coder [--version] [--help]

    Tests in tests/presentation/ mirror the source layout.
    Behavioral, architectural, and schema contracts from contracts.md all pass."
    ```

14. **Post-flight.** `git status` clean. Single new commit on top of DO-00.

## Failure modes

- **`prompt_toolkit` overwrites our prints:** the failure is usually that the logger writes to stderr. Confirm `logger.remove(0)` was called before adding the file sink.
- **`mypy` complains about `PromptSession.prompt`:** add a `type: ignore[assignment]` per line; `prompt_toolkit`'s types are noisy. Do not blanket-ignore the whole module.
- **Test isolation:** every `test_repl_*` test must reset the registry. The `conftest.py` at `tests/presentation/` provides a `fresh_registry` fixture.
