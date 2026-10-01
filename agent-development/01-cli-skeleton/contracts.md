# DO-01 contracts

## Architectural

- [ ] New modules sit in the `presentation` and `infrastructure` layers:
  - `simple_cli_coder_with_rag.presentation.repl`
  - `simple_cli_coder_with_rag.presentation.registry`
  - `simple_cli_coder_with_rag.presentation.commands`
  - `simple_cli_coder_with_rag.presentation.commands.help`
  - `simple_cli_coder_with_rag.presentation.commands.exit`
  - `simple_cli_coder_with_rag.presentation.commands.clear`
  - `simple_cli_coder_with_rag.presentation.commands.version`
  - `simple_cli_coder_with_rag.infrastructure.local_paths` (consumed by `--reset` in `presentation` and by `Settings.db_path` default in `infrastructure/settings` later)
  - `simple_cli_coder_with_rag.cli` (the entry point; allowed to import from any layer per the `import-linter` contract).
- [ ] `import-linter` reports zero violations. `presentation` may import from `infrastructure`, `application`, `domain`.
- [ ] `application`, `infrastructure`, and `domain` do **not** import from `presentation`.
- [ ] The `Command`, `CommandContext`, `CommandResult`, and `CommandRegistry` types live in `presentation` (no leakage into other layers).

## Behavioral

- [ ] `coder --version` exits 0 and prints the package version to stdout.
- [ ] `coder --help` exits 0 and prints a one-line usage message.
- [ ] `coder --reset` reads `Continue? [y/N] ` from stdin; on `y` deletes the DB and session files under `user_data_dir`, prints `Reset complete.`, and exits 0. On any other input, prints `Aborted.` and exits 0. The REPL is not entered and the logger is not initialized (the file sink is unnecessary on a one-shot data wipe).
- [ ] `coder --reset` against an empty/missing `user_data_dir` exits 0 (no files to delete counts as success).
- [ ] `coder --reset` prints the absolute data-dir path and a relative path for every file it would delete **before** prompting, so the user can see what is about to go.
- [ ] `coder --reset` is safe to combine with other flags (`--version`, `--help`); if both `--reset` and `--version` are passed, `--reset` wins and runs to completion.
- [ ] When the REPL receives `/help`, it prints a list of all registered commands with their `summary` strings.
- [ ] When the REPL receives `/version`, it prints the package version.
- [ ] When the REPL receives `/clear`, the screen is cleared (asserted via mocked `prompt_toolkit` formatter).
- [ ] When the REPL receives `/exit`, the loop returns.
- [ ] When the REPL receives a non-slash input, it prints "Type /help for available commands." and continues.
- [ ] When the REPL receives an unknown slash command (e.g. `/foo`), it prints `Unknown command: /foo` and lists known commands.
- [ ] The REPL does **not** write to stdout/stderr from the logger; all log output goes to the file configured by `loguru`.

## Schema

- [ ] `class Command(Protocol)` with attributes `name: str`, `summary: str`, and method `execute(self, context: CommandContext) -> CommandResult`.
- [ ] `class CommandContext`: attributes `repl: Repl`, `app_state: AppState`. `AppState` is a typed dataclass or Pydantic model (a placeholder with `version: str` is fine; DO-02 adds `llm`, DO-03 adds `knowledge` and `history`). `Settings` is **not** stored on `AppState`: it is created once in the composition root and injected into the concrete adapters, then values are passed down (see DO-02 architectural contract).
- [ ] `class CommandResult`: attributes `action: Literal["continue", "exit"]` (default `"continue"`), optional `message: str`.
- [ ] `class CommandRegistry`:
  - `register(self, command: Command) -> None`
  - `unregister(self, name: str) -> None`
  - `get(self, name: str) -> Command | None`
  - `names(self) -> list[str]`
  - `all(self) -> list[Command]`
- [ ] `class Repl`:
  - constructor `(self, registry: CommandRegistry, app_state: AppState) -> None`
  - `run(self) -> None` — blocks until an `exit` command fires.
  - `request_exit(self) -> None` — public hook called by `ExitCommand`.
- [ ] `simple_cli_coder_with_rag.__init__` defines `__version__: str = "0.1.0"`.
- [ ] `class LocalPaths` (in `infrastructure/local_paths.py`):
  - `data_dir() -> Path` — returns `platformdirs.user_data_dir("simple-cli-coder-with-rag")` resolved to an absolute `Path`.
  - `reset_targets() -> list[Path]` — returns `[data_dir() / "db.sqlite", data_dir() / "db.sqlite-shm", data_dir() / "db.sqlite-wal", *sorted(data_dir().glob("sessions/*"))]`, with non-existing entries filtered (so a fresh install doesn't crash).
  - This module is the single place that names local data files. `--reset` (presentation) and DO-07's DB default (infrastructure/settings) both consume it, avoiding path drift. Putting it in `infrastructure/` (rather than `presentation/`) lets DO-07's settings default reuse it without a downward import.
