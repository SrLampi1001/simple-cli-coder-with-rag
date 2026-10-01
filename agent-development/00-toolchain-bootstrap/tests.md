# DO-00 tests

These tests must be written **before** any other work in this deliverable. On a clean clone (no `pyproject.toml`, no skeleton) every test below fails. After this deliverable is complete, every test passes.

## Test files

```
tests/
├── __init__.py
├── conftest.py
├── test_smoke.py
├── test_toolchain.py
├── test_gitignore.py
└── test_env_example.py
```

## Test functions and assertions

### `tests/test_smoke.py`

- `test_package_imports` — `import simple_cli_coder_with_rag` succeeds.
- `test_layers_exist_and_import` — each of `simple_cli_coder_with_rag.presentation`, `.application`, `.infrastructure`, `.domain` is importable and is a package (has `__path__`).
- `test_cli_script_registered` — `subprocess.run(["uv", "run", "coder", "--help"], check=True)` exits 0.

### `tests/test_toolchain.py`

Each test runs the corresponding tool as a subprocess and asserts exit code 0.

- `test_ruff_check_passes` — `uv run ruff check .`
- `test_ruff_format_check_passes` — `uv run ruff format --check .`
- `test_mypy_passes` — `uv run mypy src`
- `test_import_linter_passes` — `uv run lint-imports`
- `test_pytest_collects` — `uv run pytest --collect-only -q` (the test suite must be collectable)
- `test_uv_lock_reproducible` — `rm uv.lock && uv lock && git diff --exit-code uv.lock` (skipped in CI if `uv.lock` is not in the working tree; runs locally)

### `tests/test_gitignore.py`

- `test_gitignore_exists` — `.gitignore` is present at the repo root.
- `test_gitignore_covers_python_artifacts` — `.gitignore` lines include `__pycache__`, `*.py[cod]`, `.venv/`, `dist/`, `build/`, `*.egg-info/`.
- `test_gitignore_covers_secrets` — `.gitignore` lines include `.env` and at least one of `*.sqlite` or `*.db`.
- `test_gitignore_excludes_env_example` — `git check-ignore -v .env.example` exits non-zero (i.e., `.env.example` is **not** ignored).
- `test_gitignore_would_ignore_dotenv` — `git check-ignore -v .env` exits 0 (i.e., `.env` **is** ignored).

### `tests/test_env_example.py`

- `test_env_example_exists` — `.env.example` is present.
- `test_env_example_has_provider_keys` — `.env.example` contains the lines `NVIDIA_API_KEY=`, `MISTRAL_API_KEY=`, `MINIMAX_API_KEY=`.
- `test_env_example_has_no_real_secret` — every value in `.env.example` is empty. A simple substring check is enough.
- `test_env_example_does_not_override_actual_env` — instantiating `pydantic_settings.BaseSettings` with `env_file=".env.example"` (without a real `.env` present) yields empty values for all three provider keys. (This is a soft test; the real `Settings` class is created in DO-02.)

## Why these tests

- The toolchain tests assert the gate is actually enforced, not just installed.
- The gitignore tests assert the secrets contract from the master README is real.
- The env-example test asserts the documented defaults match the actual settings defaults.
- The smoke tests give subsequent deliverables an importable package to build on.
