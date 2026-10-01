# DO-00 workflow

## Subagent delegation

**One subagent.** The steps are tightly coupled (`pyproject.toml`, `uv.lock`, `.gitignore`, `.pre-commit-config.yaml`, and the package skeleton all reference each other), so splitting risks drift.

### Context passed to the subagent

- `agent-development/README.md` (master).
- The four files in this folder.
- `docs/development-tools.md` (full — this is the only deliverable that needs the whole file).
- Nothing else.

## Web-search verification (before pinning)

Before writing `pyproject.toml`, run these `websearch` calls in parallel and reconcile with `docs/development-tools.md` §1:

1. `websearch "fastembed pypi latest version 2026"` — confirm the version pinned in dev-tools.md §1 is still current.
2. `websearch "sqlite-vec pypi latest version 2026"` — same.
3. `websearch "anthropic python sdk pypi latest"` — confirm the pinned major.
4. `websearch "prompt_toolkit pypi latest"` — same.
5. `websearch "pydantic-settings pypi latest"` — same.

If any version has moved within the same minor, update `pyproject.toml` and add a `bump: <lib> <old> -> <new>` line to the commit body. If it has moved across a major, stop and ask the user.

## Steps

1. **Pre-flight.** Run `git status`. If there are unstaged or untracked files (other than this very `agent-development/` folder, which will be committed at the end of the whole plan, not now), stop and resolve them. Empty output is the goal.

2. **Read `docs/development-tools.md` in full.** This is the only deliverable that needs the whole file. Note the literal snippets for `pyproject.toml`, `import-linter`, and the `vec0` schema — they are used verbatim later.

3. **Write `pyproject.toml`.** Use the literal snippets from dev-tools.md §3 and §13. Do not paraphrase the `[tool.ruff]`, `[tool.mypy]`, or `[tool.importlinter]` sections.

4. **Generate `uv.lock`:** `uv lock`. Commit the lockfile. Confirm reproducibility by running `rm uv.lock && uv lock && git diff --exit-code uv.lock` — must be a no-op.

5. **Write `.gitignore`.** Cover everything listed in `objective.md`. The `.env*` block must be:
   ```
   .env
   .env.*
   !.env.example
   ```

6. **Write `.env.example`** with exactly:
   ```
   ANTHROPIC_API_KEY=
   COMPACTOR_MODEL=claude-haiku-4-5
   CHAT_MODEL=claude-sonnet-4-5
   ```

7. **Create the package skeleton:**
   - `src/simple_cli_coder_with_rag/__init__.py` (empty, single line `__all__: list[str] = []` is fine)
   - `src/simple_cli_coder_with_rag/presentation/__init__.py` (empty)
   - `src/simple_cli_coder_with_rag/application/__init__.py` (empty)
   - `src/simple_cli_coder_with_rag/infrastructure/__init__.py` (empty)
   - `src/simple_cli_coder_with_rag/domain/__init__.py` (empty)
   - `src/simple_cli_coder_with_rag/cli.py`:
     ```python
     def main() -> None:
         print("coder")
     ```

8. **Create `tests/`:**
   - `tests/__init__.py` (empty)
   - `tests/conftest.py` (empty)
   - `tests/test_smoke.py`, `tests/test_toolchain.py`, `tests/test_gitignore.py`, `tests/test_env_example.py` exactly as in `tests.md`.

9. **Write `.pre-commit-config.yaml`** with hooks for `ruff check --fix`, `ruff format`, `mypy`, and `lint-imports`. Reference the repo's `pyproject.toml` for tool config (do not duplicate it).

10. **Install pre-commit:** `uv run pre-commit install`. Confirm with `pre-commit run --all-files` (must exit 0; if it doesn't, the most common cause is `hatchling` not being able to build the package locally — run `uv sync` once more).

11. **Run the gate.** Every command in `objective.md` "Gate" section, in order. All must exit 0.

12. **Verify secrets safety:**
    - `git check-ignore -v .env` exits 0.
    - `git check-ignore -v .env.example` exits non-zero.
    - `git status` does not show `.env` or any `*.sqlite` file.

13. **Commit.** Stage everything and commit with the message below.

    ```bash
    git add pyproject.toml uv.lock .gitignore .env.example \
            .pre-commit-config.yaml src tests
    git status   # confirm only the expected paths are staged
    git commit -m "chore(toolchain): bootstrap uv, ruff, mypy, import-linter, pre-commit

    - pyproject.toml with all required deps per docs/development-tools.md
    - uv.lock committed for reproducible installs
    - import-linter layered-architecture contract enforced
    - mypy strict on simple_cli_coder_with_rag.* with overrides for fastembed, sqlite_vec
    - ruff + format replacing flake8/isort/black
    - pre-commit runs all four on every commit
    - .gitignore covers .env, *.sqlite, caches, build artifacts
    - .env.example committed with no real values
    - empty package skeleton for presentation/application/infrastructure/domain

    Gates DO-01 onwards."
    ```
    **Note:** The above message is a suggested template. If dependency versions were bumped during web-search verification, the `bump:` lines belong in the body. If the skeleton or config files differ from the plan, update the bullet list to describe what actually landed.

14. **Post-flight.** `git status` is clean. `git log --oneline -1` shows the commit. `git log -1 --format=%B` shows the full body.

## Failure modes and recovery

- **Pre-commit hook fails locally but tools pass when run directly:** usually a `pyproject.toml` formatting issue. Run `uv run ruff format .` then retry.
- **`mypy` complains about missing `fastembed` / `sqlite_vec` types:** the per-module override in dev-tools.md §3 must be present verbatim. Double-check the section name (`overrides`, not `override`).
- **`import-linter` complains about `presentation` importing `infrastructure`:** that is allowed by the contract; `infrastructure` importing `presentation` is not. The placeholder `cli.py` lives in `presentation` and may import nothing yet.
- **`uv lock` is non-reproducible:** likely a `gitconfig` issue (`user.email` not set). Run `git config user.email "agent@local"` once.

If any step fails, fix it and re-run from step 11. Do not commit a broken state.
