# DO-01 — CLI skeleton

## Goal

The interactive REPL boots, accepts user input, parses slash commands via a `Command` registry, and runs the built-in commands (`/help`, `/exit`, `/clear`, `/version`). The `/learn` command does **not** exist yet (DO-04). Non-slash input is rejected with a clear message: "Type /help for available commands" (the actual chat is wired in DO-03).

## Source of truth

- `OBJECTIVES.md` — Command pattern, presentation layer.
- `docs/development-tools.md` §3 (architectural layers), §7 (CLI surface: `prompt_toolkit` + `argparse`).

## Acceptance criteria

- [ ] `src/simple_cli_coder_with_rag/cli.py` exposes `main(argv: list[str] | None = None) -> int`. `argparse` parses `--version`, `--help`, and `--reset`; the rest goes to the REPL.
- [ ] `coder --reset` deletes all local data (vector store DB, chat session JSON files) under `platformdirs.user_data_dir("simple-cli-coder-with-rag")`, **after** prompting the user on stdin (`Continue? [y/N] `, default `N`). On `y`, deletes `<data_dir>/db.sqlite` (+ `-shm`/`-wal` siblings if present) and every file under `<data_dir>/sessions/`, prints `Reset complete.` to stdout, and exits 0. On any other input, prints `Aborted.` and exits 0. The REPL is **not** entered. Missing files count as already-reset (no error).
- [ ] `src/simple_cli_coder_with_rag/presentation/repl.py` defines `class Repl`. Constructor takes a `CommandRegistry`. `run() -> None` enters the `prompt_toolkit` loop until a command calls `exit`.
- [ ] `src/simple_cli_coder_with_rag/presentation/commands/` is a subpackage with one module per command:
  - `help.py` — `class HelpCommand` lists all registered commands and their one-line descriptions.
  - `exit.py` — `class ExitCommand` exits the REPL (sets a flag the loop reads).
  - `clear.py` — `class ClearCommand` clears the screen via `prompt_toolkit`'s `clear()` formatter.
  - `version.py` — `class VersionCommand` prints `__version__` from `simple_cli_coder_with_rag.__init__`.
- [ ] `src/simple_cli_coder_with_rag/presentation/commands/__init__.py` defines:
  ```python
  class Command(Protocol):
      name: str
      summary: str
      def execute(self, context: CommandContext) -> CommandResult: ...
  ```
  with `CommandContext` (carries `repl`, `app_state`) and `CommandResult` (carries `action: Literal["continue", "exit"]`).
- [ ] `src/simple_cli_coder_with_rag/presentation/registry.py` defines `class CommandRegistry` with `register(command)`, `get(name)`, `names()`. Backed by a `dict[str, Command]`.
- [ ] The composition root (in `cli.py` or `app.py`) builds the registry with the four built-in commands and passes it to `Repl`.
- [ ] Logging is wired via `loguru` to `~/.local/share/simple-cli-coder-with-rag/log/app.log` (path from `platformdirs.user_log_dir`). Stdout/stderr are **not** written by the logger.
- [ ] The full gate (below) exits 0.

## Gate (all must exit 0)

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run lint-imports
uv run pytest -q
pre-commit run --all-files
```

## Out of scope

- Chat with the LLM (DO-03).
- The `/learn` command (DO-04).
- Any RAG code.
- Pretty-printing, colors, or themes.
- Cached model files in `user_cache_dir` (the local fastembed model is preserved across `--reset`; re-downloading is slow). `--reset` only touches `user_data_dir`.

## Depends on

- DO-00.

## Blocks

- DO-02, DO-03, DO-04, DO-09, DO-10.
