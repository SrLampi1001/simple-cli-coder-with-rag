# DO-01 tests

These tests must be written **before** any code in this deliverable. They MUST fail on the DO-00 skeleton (no `presentation/` modules yet) and MUST pass before DO-01 is marked done.

## Test files

```
tests/presentation/
├── __init__.py
├── test_registry.py
├── test_repl.py
├── test_cli_entry.py
└── commands/
    ├── __init__.py
    ├── test_help.py
    ├── test_exit.py
    ├── test_clear.py
    └── test_version.py
```

The test layout **mirrors the source layout** under `tests/presentation/`.

## Test functions and assertions

### `tests/presentation/test_registry.py`

- `test_registry_register_and_get` — register a stub `Command`, `get(name)` returns it.
- `test_registry_register_rejects_duplicate` — registering two commands with the same `name` raises `ValueError`.
- `test_registry_get_unknown_returns_none` — `get("nope")` returns `None`.
- `test_registry_unregister` — `unregister` removes the command; subsequent `get` returns `None`.
- `test_registry_names_sorted` — `names()` returns the registered names in sorted order.
- `test_registry_all_returns_commands` — `all()` returns the same set as iterating over registered names.

### `tests/presentation/commands/test_help.py`

- `test_help_lists_all_registered_commands` — given a registry with three commands, `HelpCommand.execute` returns a `CommandResult` whose `message` contains the three `name`/`summary` pairs.
- `test_help_message_is_human_readable` — the message contains at least one newline-separated entry per command.

### `tests/presentation/commands/test_exit.py`

- `test_exit_signals_exit` — `ExitCommand.execute` returns a `CommandResult` with `action == "exit"`.
- `test_exit_calls_repl_request_exit` — `ExitCommand` calls `context.repl.request_exit()` exactly once.

### `tests/presentation/commands/test_clear.py`

- `test_clear_signals_continue` — `ClearCommand.execute` returns a `CommandResult` with `action == "continue"`.
- `test_clear_invokes_prompt_toolkit_clear` — patched `prompt_toolkit.shortcuts.clear` is called exactly once with `leave_current_page=True` (or whatever the actual API requires; pin in the test).

### `tests/presentation/commands/test_version.py`

- `test_version_prints_package_version` — `VersionCommand.execute` returns a message equal to `__version__` from `simple_cli_coder_with_rag`.
- `test_version_does_not_exit` — the result `action == "continue"`.

### `tests/presentation/test_repl.py`

`prompt_toolkit.PromptSession.prompt` is mocked. The mocked prompt yields a sequence of inputs and the test asserts the post-loop state.

- `test_repl_invokes_help_for_slash_help` — input `["/help"]` → `HelpCommand.execute` called once.
- `test_repl_invokes_exit_for_slash_exit` — input `["/exit"]` → `Repl.run` returns; the loop exited.
- `test_repl_prints_unknown_command_message` — input `["/foo"]` → a message matching `Unknown command: /foo` is emitted (capture via a mocked `print` or the registered `output` callable).
- `test_repl_echoes_non_slash_input_message` — input `["hello"]` → message `Type /help for available commands.` is emitted.
- `test_repl_does_not_call_loguru_sink_for_stderr` — patching `loguru.logger.add` and capturing calls; the file sink is registered, no sink writes to stdout/stderr.

### `tests/presentation/test_cli_entry.py`

- `test_cli_version_flag` — `main(["--version"])` exits 0 and stdout contains `0.1.0`.
- `test_cli_help_flag` — `main(["--help"])` exits 0 and stdout contains a usage line.
- `test_cli_runs_repl_when_no_args` — `main([])` calls `Repl.run()` once (patched).

## Why these tests

- `test_registry_*` pins the `Command` registry contract.
- `test_repl_*` pins the user-visible behavior of the loop.
- `test_cli_entry_*` pins the script entry point.
- The `loguru` stderr assertion prevents the well-known "loguru corrupts the prompt" failure mode flagged in dev-tools.md §8.
