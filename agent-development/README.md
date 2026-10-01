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
4. **Conventional commit:** the work is committed with a message that follows [Conventional Commits](https://www.conventionalcommits.org/). **The commit message must reflect what was actually implemented**, not just what was planned. Each `workflow.md` provides a **suggested template** — adapt it to match the real changes.
5. **Post-flight clean:** after the commit, `git status` is clean.

If any of those fail, the deliverable is **not done**. Do not move on. Fix and re-run the gate.

### Conventional commit message format

```
<type>(<scope>): <short summary>

<optional body explaining the why>

<optional footer>
```

`<type>` is one of `feat`, `fix`, `chore`, `refactor`, `test`, `docs`, `perf`. `<scope>` is the deliverable number, e.g. `(toolchain)`, `(cli)`, `(rag)`. The summary line is imperative mood, lowercase, no period, ≤72 chars.

### Commit message guidance

- **The examples in `workflow.md` are templates/suggestions only.** During implementation, discoveries, refactors, bug fixes, or scope changes often occur. The final commit message must accurately describe what was *actually* done.
- If the implementation deviates from the plan, update the commit body accordingly — add, remove, or reword bullet points to match reality.
- Do not commit a message claiming features that don't exist or tests that weren't written. This obscures history and makes debugging harder.
- When in doubt, keep the summary line accurate and let the body explain the delta from the plan.

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
- A `workflow.md` step contradicts a `contracts.md` line, or the implementation is forced to diverge from the plan in a way the contracts do not cover.
- A known discrepancy between this plan and `docs/development-tools.md` is hit (see "Known discrepancies" below).

## Known discrepancies with `docs/development-tools.md`

These are deliberate, tracked mismatches. They are **not** licenses to improvise. Resolve each with the user before the affected deliverable, then update both documents so they agree.

**No discrepancies are currently tracked beyond the one below.**

- **Provider switch (DO-00 / DO-02).** The three LLM providers used by the project are **NVIDIA**, **Mistral**, and **MiniMax** (minimax.io) — Anthropic is no longer used. Resolution: `.env.example` now carries `NVIDIA_API_KEY=`, `MISTRAL_API_KEY=`, `MINIMAX_API_KEY=` (no real values); per-provider model defaults and Anthropic-SDK compatibility / `base_url` for each provider are determined by the web-search step that opens DO-02's `workflow.md`, with findings captured in the commit body in a `provider-research:` block. The previously-listed items have been folded back into the plan:

- `coder --reset` (`dev-tools.md` §7) is now defined in DO-01: it wipes the local data dir (DB + session JSON files) under `platformdirs.user_data_dir` after an interactive `y/N` prompt, default `N`. The single source of truth for those file paths is `infrastructure/local_paths.LocalPaths` (consumed by `--reset` and DO-07's DB default).
- The "run retrieval concurrently with prompt/LLM preparation" latency tip (`README.md` + `dev-tools.md` §9) is now a measured budget in DO-09: `test_recall_latency_under_threshold` pins end-to-end recall at < 100 ms. If the test fails, the documented resolution is to introduce a separate `LLMCallExecutor` and overlap the LLM SDK call with recall (DO-09 workflow step 10).
- The `RetrievalExecutor` scope is now pinned by an architectural contract in DO-08: `RetrievalExecutor` is retrieval-only; LLM-bound concurrency (if ever added) must use a separate executor.
- The DO-02 ↔ DO-10 message-union change has been applied: DO-02's `test_message_union_validation` uses a genuinely unknown role (`"junior"`), and DO-10 adds `tests/domain/test_messages.py` with `test_tool_result_message_has_tool_role`, `test_assistant_message_carries_tool_calls`, and `test_message_union_accepts_tool_result`.

If a new discrepancy is found, add a row here with a `Resolution` and resolve it before the affected deliverable.
