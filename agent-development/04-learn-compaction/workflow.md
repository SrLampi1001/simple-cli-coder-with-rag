# DO-04 workflow

## Subagent delegation — SPLIT INTO TWO

This deliverable is large enough to split. Two subagents work in parallel on disjoint files; the orchestrator (the agent running this `workflow.md`) merges and runs the gate.

### Subagent A — session storage + models

**Owns:**
- `src/simple_cli_coder_with_rag/domain/compacted.py`
- `src/simple_cli_coder_with_rag/application/session_store.py`
- `tests/domain/test_compacted.py`
- `tests/application/test_session_store.py`

**Context:**
- `agent-development/README.md`.
- This folder's four files.
- `docs/development-tools.md` §8 (no extra retry lib), §11 (testing).
- Nothing else.

**Contract to satisfy:** the schema in `contracts.md` for `CompactedSession`, `ErrorRecord`, `DecisionRecord`, `SessionStore`.

**No commits.** Returns when the tests in `test_compacted.py` and `test_session_store.py` pass locally.

### Subagent B — compactor + learn command + wiring

**Owns:**
- `src/simple_cli_coder_with_rag/application/compactor.py`
- `src/simple_cli_coder_with_rag/presentation/commands/learn.py`
- Edits to `src/simple_cli_coder_with_rag/application/knowledge_service.py` (replacing the `learn` stub)
- `tests/application/test_compactor.py`
- `tests/application/test_knowledge_service_learn.py` (replaces DO-03's stub test)
- `tests/presentation/commands/test_learn.py`
- Edits to `src/simple_cli_coder_with_rag/cli.py` (register `/learn`)

**Context:** as above, plus the schema for `CompactedSession` and `SessionStore` (so the compactor knows what to produce). The schema is given verbatim in this `workflow.md`; subagent B does not need to read subagent A's code.

**Contract to satisfy:** the schema in `contracts.md` for `Compactor`, `LearnCommand`, and the implementation of `KnowledgeService.learn`.

**No commits.** Returns when the tests pass locally.

### Orchestrator (the agent running this workflow)

1. Runs pre-flight.
2. Spawns subagents A and B in parallel.
3. After both return, runs the full gate.
4. If gate is green, makes a single commit covering all of subagent A's + B's changes.
5. If gate fails, fixes or routes the fix back to the right subagent.

## Web-search verification

Not required. `pydantic`, `pydantic-settings`, `anthropic` are already pinned by DO-00/02.

## Steps

1. **Pre-flight.** `git status` clean.

2. **Spawn subagents A and B in parallel.** Both run on the DO-03 state. Both return only when their tests pass locally.

3. **Orchestrator merges.** After both return, re-run `uv run pytest -q` end-to-end to confirm nothing was double-implemented or missed.

4. **Run the full gate.** All exit 0.

5. **Smoke test** (separate terminal):
   - With a **fake** `ANTHROPIC_API_KEY`, run `uv run coder` and immediately `/learn` (do **not** type chat turns — they would fail with `LLMError` on a fake key). The empty session short-circuits, so expect `learned 0 chunks` and an empty `~/.local/share/simple-cli-coder-with-rag/sessions/<uuid>.jsonl` + `<uuid>.compacted.json` on disk. Run `/learn` again — only one `.compacted.json` should exist (idempotency).
   - To exercise **real** compaction output (non-empty `errors`/`decisions`), repeat with a working API key and a few real chat turns. The fake-key run only proves the short-circuit and file-writing path.

6. **Verify secrets safety:** `git status` does not show any file under `~/.local/share/...`.

7. **Commit (suggested template — adapt to actual changes):**
   ```bash
   git add src/simple_cli_coder_with_rag/domain/compacted.py \
           src/simple_cli_coder_with_rag/application/session_store.py \
           src/simple_cli_coder_with_rag/application/compactor.py \
           src/simple_cli_coder_with_rag/application/knowledge_service.py \
           src/simple_cli_coder_with_rag/presentation/commands/learn.py \
           src/simple_cli_coder_with_rag/cli.py \
           tests/domain/test_compacted.py \
           tests/application/test_session_store.py \
           tests/application/test_compactor.py \
           tests/application/test_knowledge_service_learn.py \
           tests/presentation/commands/test_learn.py
   git status
   git commit -m "feat(learn): session storage, compactor, /learn command, idempotent JSON output

    - domain/compacted.py: CompactedSession, ErrorRecord, DecisionRecord (Pydantic v2).
    - application/session_store.py: SessionStore(root) with current_id/append/read/delete/
      write_compacted. Append-only .jsonl; compacted JSON is overwrite-on-write (idempotent).
    - application/compactor.py: Compactor(llm, settings) calls llm.complete with the
      compactor model, validates JSON into CompactedSession, raises CompactionError on
      bad JSON or missing fields. Empty session short-circuits without an LLM call.
    - KnowledgeService.learn replaces the DO-03 stub; calls append (skips already-on-disk)
      then Compactor.compact then SessionStore.write_compacted.
    - presentation/commands/learn.py: LearnCommand registered in cli.py.
    - composition root generates UUIDv4 session_id at startup and wires SessionStore.

    Satisfies OBJECTIVES bullet 2: 'The command creates the JSON file'."
   ```
   **Note:** The above message is a template. The single commit merges two subagents' work. If the compactor schema changed, if idempotency was handled differently, if the session ID strategy differs, or if any file paths/names changed — update the commit body to reflect what actually landed.

8. **Post-flight.** `git status` clean. Single new commit on top of DO-03.

## Failure modes

- **Subagent A and B both create `CompactedSession` slightly differently:** the orchestrator catches this on the merge step — the schema in `contracts.md` is authoritative. If they differ, take A's version (it's in `domain/` and is the source of truth).
- **Idempotency broken on retry:** the `append` method must check `read` first and skip messages whose `(role, content)` is already present. Or simpler: persist a "last appended index" in `AppState` and append only newer messages.
- **Empty-session crash:** the compactor short-circuit must run **before** `LLMClient.complete`. The test `test_learn_with_empty_session_writes_empty_compacted` will catch this.
