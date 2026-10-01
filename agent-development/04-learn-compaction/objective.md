# DO-04 — `/learn` compaction → JSON

## Goal

The `/learn` slash command reads the current session, compacts it via the LLM into a structured `CompactedSession`, and writes it to disk as JSON. The session is persisted as append-only `.jsonl` during the REPL run. This completes the second OBJECTIVES bullet: *"The command creates the JSON file."*

## Source of truth

- `OBJECTIVES.md` — "The command creates the JSON file" + compactor pipeline.
- `docs/development-tools.md` §6 (LLM compaction model is a setting, long-session strategy), §11 (testing).

## Acceptance criteria

- [ ] `src/simple_cli_coder_with_rag/domain/compacted.py` defines `class CompactedSession(BaseModel)`:
  - `session_id: str`
  - `created_at: datetime`
  - `summary: str`
  - `errors: list[ErrorRecord]`
  - `decisions: list[DecisionRecord]`
  with `class ErrorRecord(BaseModel)` (`signature: str`, `message: str`, `occurrences: int`) and `class DecisionRecord(BaseModel)` (`summary: str`, `rationale: str`).
- [ ] `src/simple_cli_coder_with_rag/application/session_store.py` defines `class SessionStore`:
  - `__init__(self, root: Path)` — `root` is `~/.local/share/simple-cli-coder-with-rag/sessions/`.
  - `current_id(self) -> str` — generates a new UUIDv4 session id.
  - `path(self, session_id: str) -> Path` — returns `root / f"{session_id}.jsonl"`.
  - `append(self, session_id: str, message: Message) -> None` — appends one JSON line per call.
  - `read(self, session_id: str) -> list[Message]` — reads all lines, returns `[]` if the file does not exist.
  - `delete(self, session_id: str) -> None` — idempotent.
- [ ] `src/simple_cli_coder_with_rag/application/compactor.py` defines `class Compactor`:
  - `__init__(self, llm: LLMClient, settings: Settings) -> None`
  - `compact(self, session_id: str, messages: list[Message]) -> CompactedSession` — calls `llm.complete` with a structured-output prompt, validates the JSON response into `CompactedSession`.
- [ ] `src/simple_cli_coder_with_rag/presentation/commands/learn.py` defines `class LearnCommand`:
  - Reads `app_state.history` and `app_state.session_id`.
  - Calls `KnowledgeService.learn(session_id)` (which is now implemented; see step 5 below).
  - Returns `CommandResult(action="continue", message="learned <N> chunks")` (chunk count is filled in by DO-05; for now `0` is acceptable, but DO-05 should be done in the same PR batch only if the count is wired up).
- [ ] `KnowledgeService.learn` is implemented: calls `SessionStore.append` for each message (idempotent — appends only what is not already on disk), then `Compactor.compact`, then writes the result via `SessionStore.write_compacted`.
- [ ] `SessionStore.write_compacted(self, session_id: str, compacted: CompactedSession) -> Path` — writes to `root / f"{session_id}.compacted.json"`. Idempotent (overwrites).
- [ ] `AppState` gains `session_id: str` and `session_store: SessionStore | None = None`.
- [ ] The composition root wires `SessionStore` and generates `session_id` at startup.
- [ ] `/learn` is registered in the REPL alongside `/help`, `/exit`, `/clear`, `/version`.
- [ ] The full gate exits 0.

## Gate

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

- Chunking the compacted session (DO-05).
- Embedding chunks (DO-06).
- Storing chunks into a vector DB (DO-07).
- Long-session segmentation (dev-tools.md §6 — split-by-token-budget). Add later behind the same `Compactor` Protocol if needed; this deliverable handles only sessions that fit one Haiku call.

## Depends on

- DO-00, DO-01, DO-02, DO-03.

## Blocks

- DO-05, DO-06, DO-07, DO-09.
