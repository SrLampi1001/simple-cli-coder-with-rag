# DO-04 contracts

## Architectural

- [ ] New modules:
  - `simple_cli_coder_with_rag.domain.compacted` (Pydantic models)
  - `simple_cli_coder_with_rag.application.session_store`
  - `simple_cli_coder_with_rag.application.compactor`
  - `simple_cli_coder_with_rag.presentation.commands.learn`
- [ ] `SessionStore` lives in `application/`; it does **not** import from `infrastructure`. (No SDK touches the disk; only `pathlib`.)
- [ ] `Compactor` lives in `application/`; it imports `LLMClient` from `domain/` only.
- [ ] `import-linter` reports zero violations.
- [ ] No module outside `application/session_store.py` writes to `~/.local/share/simple-cli-coder-with-rag/sessions/`.

## Behavioral

- [ ] At REPL startup, a UUIDv4 `session_id` is generated and stored on `AppState`.
- [ ] Every chat turn (user message + assistant response) is appended to `sessions/{session_id}.jsonl` as a JSON line — exactly two lines per turn, in order.
- [ ] When the REPL receives `/learn`, `KnowledgeService.learn(session_id)` is called once.
- [ ] `learn` is idempotent: running `/learn` twice produces exactly one `*.compacted.json` (the second call overwrites).
- [ ] The compacted JSON file's schema matches `CompactedSession` (verified by reading the file back with `CompactedSession.model_validate_json`).
- [ ] If the session has zero messages, `/learn` writes a `CompactedSession` with empty `errors`/`decisions` and a `summary` of `"(empty session)"` — it does not raise.
- [ ] If `LLMClient.complete` raises `LLMError`, `/learn` prints `learn failed: <message>` and returns `CommandResult(action="continue")`; the user can retry.
- [ ] The REPL still works (chat, slash commands) after a failed `/learn`.

## Schema

- [ ] `class ErrorRecord(BaseModel)`:
  - `signature: str` — e.g., `"ModuleNotFoundError: No module named 'foo'"`.
  - `message: str` — longer human description.
  - `occurrences: int = Field(ge=1)`.
- [ ] `class DecisionRecord(BaseModel)`:
  - `summary: str`
  - `rationale: str`
- [ ] `class CompactedSession(BaseModel)`:
  - `session_id: str`
  - `created_at: datetime`
  - `summary: str`
  - `errors: list[ErrorRecord] = Field(default_factory=list)`
  - `decisions: list[DecisionRecord] = Field(default_factory=list)`
- [ ] `class SessionStore`:
  - `__init__(self, root: Path) -> None` — creates `root` if missing.
  - `current_id(self) -> str` — fresh UUIDv4.
  - `path(self, session_id: str) -> Path`
  - `append(self, session_id: str, message: Message) -> None`
  - `read(self, session_id: str) -> list[Message]`
  - `delete(self, session_id: str) -> None`
  - `write_compacted(self, session_id: str, compacted: CompactedSession) -> Path`
- [ ] `class Compactor`:
  - `__init__(self, llm: LLMClient, settings: Settings) -> None`
  - `compact(self, session_id: str, messages: list[Message]) -> CompactedSession`
- [ ] `class LearnCommand`:
  - `name = "learn"`
  - `summary = "Compact the current session and store it."`
  - `execute(self, context: CommandContext) -> CommandResult`
- [ ] `KnowledgeService.learn(self, session_id: str) -> None` — concrete implementation; no longer `NotImplementedError`.
