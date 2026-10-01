# DO-01 contracts

## Architectural

- [ ] New modules sit in the `presentation` layer only:
  - `simple_cli_coder_with_rag.presentation.repl`
  - `simple_cli_coder_with_rag.presentation.registry`
  - `simple_cli_coder_with_rag.presentation.commands`
  - `simple_cli_coder_with_rag.presentation.commands.help`
  - `simple_cli_coder_with_rag.presentation.commands.exit`
  - `simple_cli_coder_with_rag.presentation.commands.clear`
  - `simple_cli_coder_with_rag.presentation.commands.version`
  - `simple_cli_coder_with_rag.cli` (the entry point; allowed to import from any layer per the `import-linter` contract).
- [ ] `import-linter` reports zero violations. `presentation` may import from `infrastructure`, `application`, `domain`.
- [ ] `application`, `infrastructure`, and `domain` do **not** import from `presentation`.
- [ ] The `Command`, `CommandContext`, `CommandResult`, and `CommandRegistry` types live in `presentation` (no leakage into other layers).

## Behavioral

- [ ] `coder --version` exits 0 and prints the package version to stdout.
- [ ] `coder --help` exits 0 and prints a one-line usage message.
- [ ] When the REPL receives `/help`, it prints a list of all registered commands with their `summary` strings.
- [ ] When the REPL receives `/version`, it prints the package version.
- [ ] When the REPL receives `/clear`, the screen is cleared (asserted via mocked `prompt_toolkit` formatter).
- [ ] When the REPL receives `/exit`, the loop returns.
- [ ] When the REPL receives a non-slash input, it prints "Type /help for available commands." and continues.
- [ ] When the REPL receives an unknown slash command (e.g. `/foo`), it prints `Unknown command: /foo` and lists known commands.
- [ ] The REPL does **not** write to stdout/stderr from the logger; all log output goes to the file configured by `loguru`.

## Schema

- [ ] `class Command(Protocol)` with attributes `name: str`, `summary: str`, and method `execute(self, context: CommandContext) -> CommandResult`.
- [ ] `class CommandContext`: attributes `repl: Repl`, `app_state: AppState`. `AppState` is a typed dataclass or Pydantic model (a placeholder with `version: str` is fine; DO-02 will add `settings`, DO-03 will add `llm`).
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
