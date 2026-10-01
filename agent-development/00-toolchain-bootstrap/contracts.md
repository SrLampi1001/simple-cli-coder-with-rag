# DO-00 contracts

A deliverable is done only when all three contracts pass.

## Architectural

- [ ] `pyproject.toml` declares `[tool.importlinter]` with the `layered-architecture` contract **exactly** as in `docs/development-tools.md` §3 — `root_package = simple_cli_coder_with_rag`, layers ordered `presentation` → `infrastructure` → `application` → `domain`.
- [ ] `src/simple_cli_coder_with_rag/{presentation,application,infrastructure,domain}/` each contain `__init__.py` and no other files.
- [ ] `import-linter` reports zero violations on the empty skeleton.
- [ ] `mypy` strict mode (`disallow_untyped_defs = true`) is applied to `simple_cli_coder_with_rag.*` per `docs/development-tools.md` §3.
- [ ] `mypy` has per-module overrides (`ignore_missing_imports = true`) for `fastembed` and `sqlite_vec` per `docs/development-tools.md` §3.
- [ ] No source file under `src/` imports from a higher layer (e.g., `domain/` must not import from `application/`).

## Behavioral

- [ ] `pre-commit run --all-files` exits 0 on a fresh clone (after `pre-commit install`).
- [ ] The full gate (objective.md) exits 0 on the empty skeleton.
- [ ] `coder --help` exits 0 and prints a one-line usage message to stdout (placeholder main acceptable here; the real main is DO-01).
- [ ] `git check-ignore .env` exits 0 (the path would be ignored even if the file existed).
- [ ] `git status` does not show `.env` or any `*.sqlite` file, even when run from a directory that contains them.

## Schema

- [ ] `pyproject.toml` `[project]` table has: `name = "simple-cli-coder-with-rag"`, `version = "0.1.0"`, `requires-python = ">=3.11"`, `dependencies = [...]` per `docs/development-tools.md` §13, `optional-dependencies.remote-embedder = ["httpx", "tenacity"]`, `[project.scripts] coder = "simple_cli_coder_with_rag.cli:main"`, `[build-system] requires = ["hatchling"]`, `build-backend = "hatchling.build"`.
- [ ] `.pre-commit-config.yaml` defines hooks for `ruff check --fix`, `ruff format`, `mypy`, and `lint-imports` (or `import-linter`).
- [ ] `.gitignore` contains every line listed in `objective.md`.
- [ ] `.env.example` has exactly the three keys listed in `objective.md`, all with empty or non-sensitive default values.
- [ ] `uv.lock` is committed and is reproducible: `rm uv.lock && uv lock && git diff uv.lock` produces no diff.
