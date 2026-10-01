# agent-development/

This folder is the **implementation plan** for *Simple CLI code assistant with RAG*. It is the only document an AI agent needs to start working — together with `../README.md` (what to build and why) and `../docs/development-tools.md` (with what).

## How to read this folder

1. **Read this README first.** It defines the rules every deliverable follows.
2. **Pick one deliverable.** Each is a self-contained folder with exactly four files:
   - `objective.md` — the goal and the acceptance criteria.
   - `contracts.md` — the warranty. Three sections: **architectural**, **behavioral**, **schema**.
   - `tests.md` — the tests that must be written **before** any code in this deliverable. They must fail before the work starts and pass before it is marked done.
   - `workflow.md` — the execution plan: subagent delegation, web-search verification (if any), step-by-step implementation, commit gate.
3. **Do not read other deliverables' folders.** Their contracts are the warranty — you assume they are satisfied. If you think a prior contract is broken, stop and report.
4. **Read only the relevant sections of `docs/development-tools.md`.** Each `workflow.md` cites the exact sections it needs.

## Source of truth and conflict resolution

| Question | Source of truth |
|---|---|
| What to build, design patterns, high-level goals | `../README.md` |
| Tool choice, library version, env requirement, schema snippet, fallback | `../docs/development-tools.md` |
| Deliverable order, contracts, commit rules, subagent delegation | this folder |

If a conflict ever appears between this plan and `docs/development-tools.md`: **dev-tools wins** for tool/version questions; **this plan wins** for sequencing and contracts.

## Order of execution

Deliverables are numbered and ordered by dependency. They must be completed in order. Each one ends in exactly one conventional commit.

| # | Deliverable | Maps to README bullet |
|---|---|---|
| [00](./00-toolchain-bootstrap/) | Toolchain bootstrap (env, gates everything) | (env) |
| [01](./01-cli-skeleton/) | REPL + command registry (`/help`, `/exit`, `/clear`, `/version`) | (foundation) |
| [02](./02-llm-client-adapter/) | LLM client adapter (Anthropic SDK behind `LLMClient`) | (foundation) |
| [03](./03-agent-responds-baseline/) | Agent responds (chat loop) | *"The CLI works and the agents answer"* |
| [04](./04-learn-compaction/) | `/learn` compaction → JSON | *"The command creates the JSON file"* |
| [05](./05-chunker-strategy/) | Chunker strategy | (foundation) |
| [06](./06-embedder-strategy/) | Embedder strategy (fastembed, local) | *"The embedding model works"* |
| [07](./07-vector-store-strategy/) | Vector store strategy (sqlite-vec + numpy fallback) | *"The JSON file is stored into a vectorial database"* |
| [08](./08-retriever-with-decorator/) | Retriever + timeout decorator | (foundation) |
| [09](./09-recall-integration/) | Recall in chat (semantic search before prompt) | *"A prompt triggers semantic search and retrieves the important context"* |
| [10](./10-file-editing/) | File editing | *"The AI agent can edit files"* |

## The contract system (the warranty between deliverables)

A deliverable is **not done** until all three contracts pass.

- **Architectural** — `import-linter` is clean. New modules sit in the layer they declare. No upward import (lower layer may not import higher).
- **Behavioral** — what the system or user observes matches the assertions in `contracts.md`. Verified by the tests in `tests.md`.
- **Schema** — every Pydantic model, every `Protocol` method, every DB column listed in `contracts.md` exists with the listed shape.

The next deliverable assumes the previous one's contracts are satisfied. It does not re-verify them; it builds on top.

## The commit rule — HARD GATE

A deliverable cannot be marked complete unless **all** of the following are true:

1. **Pre-flight clean:** at the start of the deliverable, `git status` shows no unstaged or untracked files. If it does not, stop and resolve them before doing anything else. (Untracked files in this folder from prior deliverables are fine — they will be committed by the time we get here.)
2. **All tests pass**, including the new ones in `tests.md`.
3. **Linters clean:** `ruff check`, `ruff format --check`, `mypy src`, `lint-imports` all exit 0.
4. **Conventional commit:** the work is committed with a message that follows [Conventional Commits](https://www.conventionalcommits.org/). Suggested prefixes per deliverable are in each `workflow.md`.
5. **Post-flight clean:** after the commit, `git status` is clean.

If any of those fail, the deliverable is **not done**. Do not move on. Fix and re-run the gate.

### Conventional commit message format

```
<type>(<scope>): <short summary>

<optional body explaining the why>

<optional footer>
```

`<type>` is one of `feat`, `fix`, `chore`, `refactor`, `test`, `docs`, `perf`. `<scope>` is the deliverable number, e.g. `(toolchain)`, `(cli)`, `(rag)`. The summary line is imperative mood, lowercase, no period, ≤72 chars.

## Subagent delegation

The default is **one subagent per deliverable**. Two deliverables are large enough to split — their `workflow.md` says so explicitly:

- **04** splits into two subagents: session storage and compactor pipeline.
- **08** splits into two subagents: base retriever and timeout decorator + executor.

**Context to pass to a subagent** (no more, no less):

- This `README.md`.
- The four files of the deliverable the subagent owns.
- The exact `docs/development-tools.md` sections cited inside the deliverable's `workflow.md`.
- **Nothing else.** Do not pass other deliverables' folders. Do not pass the rest of the repo.

If a subagent feels it needs more context than that, the deliverable is underspecified — stop and report, do not improvise.

## Web-search policy (verify-before-pinning)

A few deliverables touch fast-moving dependencies. Before pinning anything in those, the agent must run a quick web search to confirm the version in `docs/development-tools.md` §1 is still current.

| Deliverable | Web-search before pinning |
|---|---|
| 00 | `fastembed`, `sqlite-vec`, `anthropic`, `prompt_toolkit`, `pydantic`, `pydantic-settings`, `loguru` |
| 02 | `anthropic` SDK |
| 06 | `fastembed` (model ID + version) |
| 07 | `sqlite-vec` (version + cosine support) |
| 10 | `anthropic` SDK tool-use API |

If the version has moved, update `pyproject.toml` and add a `bump: <lib> <old> -> <new>` line in the commit body. Do not bump beyond a minor version without flagging it to the user.

Other deliverables do not require web-search; `docs/development-tools.md` is sufficient.

## Secrets handling

- `.env` is in `.gitignore` from DO-00. **Never committed.**
- `.env.example` is committed and shows the required keys without values.
- Tests that need an API key **mock the SDK** via `pytest-mock`. They never read `.env` and never hit the network.
- The `Settings` class (pydantic-settings) reads `.env` at runtime. It must never log key values, even at DEBUG level.
- DO-02 has a behavioral contract that fails the startup if `ANTHROPIC_API_KEY` is empty.
- DO-10 (file editing) must sandbox edits to a configurable allow-list of paths; the test suite asserts the sandbox cannot be bypassed by path traversal.

## Development environment

All tool requirements live in `docs/development-tools.md` and are enforced from DO-00 onwards:

- Python `>=3.11`, `uv`, `ruff`, `mypy`, `import-linter`, `pre-commit`
- `fastembed` + `bge-small-en-v1.5`, `sqlite-vec`, `anthropic`
- `pydantic`, `pydantic-settings`, `loguru`, `prompt_toolkit`, `platformdirs`
- `pytest`, `pytest-cov`, `pytest-mock`, `hatchling`

The gate at the end of every deliverable is:

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run lint-imports
uv run pytest -q
pre-commit run --all-files
```

If any of those fail, the deliverable is not done. Period.

## When to stop and ask the user

Stop and ask the user (do not guess) if:

- A contract in this folder is unsatisfiable with the current `docs/development-tools.md` choices.
- A library version has moved beyond a minor bump.
- A deliverable's `workflow.md` cannot complete in one focused session.
- The agent's context is getting bloated and a subagent is needed but not budgeted.
- A pre-flight `git status` shows files the agent does not recognize.
