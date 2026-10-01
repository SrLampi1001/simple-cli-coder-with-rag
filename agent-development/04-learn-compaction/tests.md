# DO-04 tests

These tests must be written **before** any code in this deliverable.

## Test files

```
tests/domain/
└── test_compacted.py

tests/application/
├── test_session_store.py
├── test_compactor.py
└── test_knowledge_service_learn.py  (replaces the stub test from DO-03)

tests/presentation/commands/
└── test_learn.py
```

## Test functions and assertions

### `tests/domain/test_compacted.py`

- `test_compacted_session_round_trip` — `CompactedSession.model_validate_json(c.model_dump_json()) == c`.
- `test_error_record_occurrences_ge_one` — `ErrorRecord(occurrences=0)` raises `ValidationError`.
- `test_decision_record_round_trip` — `DecisionRecord.model_dump_json()` is stable.
- `test_compacted_default_empty_lists` — `CompactedSession(session_id="x", created_at=..., summary="s")` has `errors == []` and `decisions == []`.

### `tests/application/test_session_store.py`

Uses `tmp_path` for `root`.

- `test_session_store_creates_root` — passing a non-existent `tmp_path/sub` creates it.
- `test_current_id_is_uuid_v4` — `store.current_id()` matches the UUIDv4 regex.
- `test_append_creates_file_with_one_jsonl_line` — `store.append(id, UserMessage("hi"))` produces a file with exactly one line that round-trips through `UserMessage.model_validate_json`.
- `test_append_twice_writes_two_lines` — two `append` calls produce two lines, in order.
- `test_read_returns_messages_in_order` — `read` returns the messages in append order.
- `test_read_missing_file_returns_empty` — `read("nonexistent")` returns `[]`.
- `test_delete_is_idempotent` — `delete("nonexistent")` does not raise; `delete` of an existing file removes it.
- `test_write_compacted_creates_file` — `write_compacted(id, c)` returns a `Path` whose `.read_text()` is valid JSON matching `c.model_dump_json()`.
- `test_write_compacted_overwrites` — calling `write_compacted` twice for the same id results in a single file with the second content.

### `tests/application/test_compactor.py`

`LLMClient` mocked.

- `test_compactor_uses_compactor_model_setting` — captured `model` arg equals `settings.compactor_model` (default `claude-haiku-4-5`).
- `test_compactor_passes_messages_to_llm` — captured `messages` includes every input message in order.
- `test_compactor_validates_json_response` — mocked LLM returns a JSON string; `compact` returns a `CompactedSession` with the parsed fields.
- `test_compactor_rejects_invalid_json` — mocked LLM returns non-JSON garbage; `compact` raises a project-owned `CompactionError` (defined alongside `Compactor`).
- `test_compactor_rejects_missing_required_fields` — JSON missing `summary`; `compact` raises `CompactionError`.
- `test_compactor_uses_session_id_and_now` — the resulting `CompactedSession.session_id` matches the input; `created_at` is within the last few seconds.

### `tests/application/test_knowledge_service_learn.py`

`SessionStore` real (with `tmp_path`), `Compactor` real (with mocked LLM).

- `test_learn_appends_messages_and_writes_compacted` — given a `SessionStore` with two pre-appended messages and a mocked LLM returning valid JSON, `learn(id)` produces a `*.compacted.json` file.
- `test_learn_is_idempotent` — calling `learn` twice produces exactly one compacted file (the second overwrites); the underlying `append` is **not** called twice for messages already on disk (use `read` to verify length matches).
- `test_learn_with_empty_session_writes_empty_compacted` — `learn` on an empty session produces a `CompactedSession` with empty `errors`/`decisions` and `summary == "(empty session)"`. No LLM call is made.
- `test_learn_propagates_llm_error` — `LLMClient.complete` raises `LLMError`; `learn` raises `LLMError` (the REPL catches it).

### `tests/presentation/commands/test_learn.py`

- `test_learn_command_prints_count` — `LearnCommand.execute` returns a message `"learned 0 chunks"` (acceptable for this deliverable) or `"learned N chunks"` once DO-05 lands. The test asserts the message starts with `"learned "`.
- `test_learn_command_does_not_exit` — `action == "continue"`.
- `test_learn_command_handles_llm_error` — `KnowledgeService.learn` raises `LLMError`; `LearnCommand.execute` returns a message starting with `"learn failed: "` and `action == "continue"`.
- `test_learn_command_is_registered` — after composition, `registry.get("learn") is not None`.

## Why these tests

- `SessionStore` tests pin the on-disk format that DO-05+ consume.
- `Compactor` tests pin the structured-output contract.
- The idempotency test prevents DO-05+ from inflating cosine distances by re-storing the same chunks.
- The empty-session test prevents a regression where `/learn` crashes on a fresh session.
