# DO-00 — Toolchain bootstrap

## Goal

The development environment is fully configured, version-pinned, and enforcing. Every subsequent deliverable runs the same gate at the end; this deliverable makes that gate exist and pass on an empty package skeleton.

## Source of truth

`docs/development-tools.md` — read in full. This is the only deliverable that needs the whole file.

## Acceptance criteria

- [ ] `pyproject.toml` exists with every required dep, extras, and tool config from `docs/development-tools.md` §2, §3, §10, §13.
- [ ] `uv.lock` is committed and `uv sync` is reproducible.
- [ ] `[project.scripts]` defines `coder = "simple_cli_coder_with_rag.cli:main"`.
- [ ] `[tool.ruff]` configured per `docs/development-tools.md` §3 (line-length 100, target py311, lint rules `E F I B UP N SIM RUF`).
- [ ] `[tool.mypy]` configured per `docs/development-tools.md` §3, with per-module overrides for `fastembed` and `sqlite_vec`, and strict mode on `simple_cli_coder_with_rag.*`.
- [ ] `[tool.importlinter]` configured with the `layered-architecture` contract from `docs/development-tools.md` §3.
- [ ] `.pre-commit-config.yaml` runs `ruff check --fix`, `ruff format`, `mypy`, and `lint-imports` on every commit.
- [ ] `.gitignore` covers (at minimum): `.venv/`, `__pycache__/`, `*.py[cod]`, `.env`, `.env.*` with `!.env.example` exception, `*.sqlite`, `*.sqlite-journal`, `dist/`, `build/`, `*.egg-info/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `htmlcov/`, `coverage.xml`, `.DS_Store`, `Thumbs.db`, `.vscode/`, `.idea/`.
- [ ] `.env.example` is committed with `ANTHROPIC_API_KEY=`, `COMPACTOR_MODEL=claude-haiku-4-5`, `CHAT_MODEL=claude-sonnet-4-5` (no real values).
- [ ] `src/simple_cli_coder_with_rag/` package exists with empty subpackages: `presentation/`, `application/`, `infrastructure/`, `domain/`. Each contains `__init__.py`.
- [ ] `tests/` exists at repo root with `__init__.py`, an empty `conftest.py`, and the tests in `tests.md`.
- [ ] `src/simple_cli_coder_with_rag/cli.py` contains a placeholder `def main() -> None: print("coder")` so the script entry point resolves.
- [ ] The full gate (below) exits 0 on the empty skeleton.
- [ ] `pre-commit install` has been run; `pre-commit run --all-files` exits 0.
- [ ] No application code is written in this deliverable beyond the placeholder `main`.

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

- Any application code beyond the placeholder `main`.
- The real REPL (DO-01), LLM client (DO-02), RAG pipeline (DO-04 onwards).
- Documentation beyond this folder.

## Depends on

- Nothing. This is the first deliverable.

## Blocks

- All subsequent deliverables.
