# DO-12 tests

These tests must be written **before** any code in this deliverable.
They MUST fail on the DO-11 state (no `Settings.int_history_cap`,
no `SessionStore.list_sessions`, no `/memory`/`/chats`/`/resume`,
`AppState.history_cap=20` still present, REPL still keeps the last
20 turns of history) and MUST pass before DO-12 is marked done.

## Test files

```
tests/
├── application/
│   └── test_session_store_listing.py           # NEW — list_sessions()
├── infrastructure/
│   └── test_settings_int_history_cap.py        # NEW — field + validator
├── presentation/
│   ├── test_repl_chat_path.py                  # PATCH — cap 20 -> 10
│   ├── test_repl_persists_turns.py             # NEW — _handle_chat appends
│   └── commands/
│       ├── test_memory.py                      # NEW
│       ├── test_chats.py                       # NEW
│       └── test_resume.py                      # NEW
```

The tests deliberately **drop** what was in earlier drafts:

- `tests/infrastructure/token_counters/` — no `CharEstimateTokenCounter`.
- `tests/application/test_compactor_summarize.py` — no
  `Compactor.summarize` method.
- `tests/application/test_session_manager.py` — no `SessionManager`.
- `tests/application/test_knowledge_service_auto_compact.py` —
  no auto-compaction hook.
- `tests/presentation/commands/test_compact.py` — no `/compact`
  command.
- `tests/infrastructure/providers/test_provider_config.py` patch
  for `context_window` — DO-11 stays focused on provider wiring.

## Test functions and assertions

### `tests/infrastructure/test_settings_int_history_cap.py`

Pure pydantic-settings. No mocks needed.

- `test_int_history_cap_default_is_ten` —
  `Settings().int_history_cap == 10`.
- `test_int_history_cap_env_override` — `monkeypatch.setenv(
  "INT_HISTORY_CAP", "7")` → `Settings().int_history_cap == 7`.
- `test_int_history_cap_rejects_zero` —
  `monkeypatch.setenv("INT_HISTORY_CAP", "0")` →
  `Settings()` raises `ValidationError`.
- `test_int_history_cap_rejects_too_large` —
  `monkeypatch.setenv("INT_HISTORY_CAP", "101")` →
  `Settings()` raises `ValidationError`.
- `test_int_history_cap_rejects_negative` —
  `monkeypatch.setenv("INT_HISTORY_CAP", "-1")` →
  `Settings()` raises `ValidationError`.

### `tests/application/test_session_store_listing.py`

Uses `tmp_path`; no real disk outside the temp dir.

- `test_list_sessions_empty_root_returns_empty_list` —
  `SessionStore(tmp_path / "new").list_sessions() == []`.
- `test_list_sessions_returns_tuples_for_each_jsonl` —
  Pre-write three `<id>.jsonl` files with different mtimes (touch
  them in order so the mtime ordering is deterministic).
  `list_sessions()` returns exactly three, sorted by mtime
  descending, each tuple `(str, float, int)`.
- `test_list_sessions_counts_non_empty_lines_only` — a file
  containing `"a\nb\n\nc\n"` (note the trailing empty line)
  reports `message_count == 3`, not `4`.
- `test_list_sessions_skips_unreadable_files_silently` — a
  file with no read bits (`chmod 000`); the entry is omitted,
  no exception propagates. Skip on platforms / users where
  chmod 000 is a no-op (root); document the tag to skip.
- `test_list_sessions_does_not_read_message_bodies` — a file
  containing an intentionally malformed JSON line is counted
  in `message_count` regardless (the listing is metadata-only,
  not a parse step).
- `test_list_sessions_handles_missing_root` — delete the root
  after construction; `list_sessions()` returns `[]` without
  raising.

### `tests/presentation/test_repl_chat_path.py` (DO-12 patch)

- [ ] `test_repl_caps_history_at_10_turns` (renamed from
      `test_repl_caps_history_at_20_turns`): same shape as the
      old test, but the cap is **10** turns (20 messages).
      `len(state.history) == 20`; `state.history[0] ==
      UserMessage(content="msg-15")`. The default
      `settings=None` path is covered (the fallback cap is
      `10`).
- [ ] `test_repl_caps_history_at_custom_cap` — pass an
      `AppState` with a stub `settings` whose
      `int_history_cap` is `3`. After 7 turns, the history
      has length `6` (3 turns × 2); the first two turns
      (`msg-0`, `msg-1`) are dropped.

### `tests/presentation/test_repl_persists_turns.py`

Uses `mocker` to patch `KnowledgeService.chat`. No real LLM.

- `test_repl_appends_each_turn_to_session_store` — Wire
  `app_state.session_store = SessionStore(tmp_path / "s")`
  and an empty history. Run the REPL with 3 chat turns
  followed by `/exit`. Assert that the on-disk transcript
  (`session_store.read(session_id)`) contains exactly 6
  messages in order (3 user + 3 assistant).
- `test_repl_does_not_re_persist_messages_already_loaded` —
  Pre-write `<id>.jsonl` with two existing user + assistant
  pairs. Run the REPL with one new chat turn followed by
  `/exit`. The on-disk transcript contains exactly 4 messages
  in order (the original 2 + the new 2), not 6.
- `test_repl_no_session_store_skips_persistence` —
  `app_state.session_store = None`. Run the REPL with 2 chat
  turns. The history has 6 entries; no exception is raised.
- `test_repl_generates_session_id_when_missing` —
  `app_state.session_id = ""`, `app_state.session_store =
  SessionStore(tmp_path / "s")`. Run the REPL with one chat
  turn. After the turn, `app_state.session_id` is a 32-char
  hex string (UUIDv4) and the on-disk file exists.

### `tests/presentation/commands/test_memory.py`

- `test_memory_with_active_session_returns_readout` — Stub
  `app_state` with `session_id = "abc1234567deadbeef"`,
  `history = [UserMessage("hi"), AssistantMessage("hello!")]`.
  Assert the result's message contains every pinned line
  (`"session:"`, `"turns:"`, `"messages:"`, `"last user:"`,
  `"last assistant:"`), the short id, and the message count
  (`messages:   2`).
- `test_memory_with_empty_history_shows_no_messages_yet` —
  Stub `app_state` with `history = []`. The
  `"last user:"` and `"last assistant:"` lines both show
  `"(no messages yet)"`.
- `test_memory_truncates_long_content_to_60_chars` — A
  history with a `UserMessage("x" * 80)` renders the
  `"last user:"` line with the content ending in
  `"…"` after 60 chars.
- `test_memory_without_session_store_returns_friendly` —
  `app_state.session_store = None` and `app_state.session_id
  = ""`; returns the friendly fallback.
- `test_memory_does_not_mutate_state` — calling the command
  does not change `app_state.history` or
  `app_state.session_id`.

### `tests/presentation/commands/test_chats.py`

- `test_chats_renders_table_for_three_sessions` — Stub
  `session_store.list_sessions` returning
  `[("abc1234567...", 12345.0, 18), ("a1b2c3d4ef...",
    1000.0, 38), ("5e6f7g8h...", 100.0, 204)]`. The Command's
  message contains the three ids, the three relative times
  (the mtimes pin `"just now"`, `"32m ago"`, `"<some date>"`),
  and the three message counts.
- `test_chats_includes_active_id_line` — message ends with
  `active: <id>`.
- `test_chats_empty_list_returns_friendly_message` —
  `list_sessions() == []`; `command.message == "No saved
  sessions yet."`.
- `test_chats_without_session_store_returns_friendly_fallback`.

### `tests/presentation/commands/test_resume.py`

- `test_resume_with_valid_id_replaces_history_with_last_n` —
  Pre-write `<id>.jsonl` with 50 messages (24 user + 24
  assistant + 2 = 50 — odd numbers are fine; the cap is on
  raw messages). `ResumeCommand().execute(...)` with that id
  + default `int_history_cap=10` replaces
  `app_state.history[:]` with the last 20 messages (= 10
  turns). `app_state.session_id == <id>`. No LLM is called.
- `test_resume_with_short_transcript_loads_verbatim` —
  Pre-write `<id>.jsonl` with 3 messages. The command
  replaces `app_state.history` with exactly those 3 messages
  (no padding).
- `test_resume_missing_id_returns_usage_message` — input
  `"/resume"` (no arg) →
  `CommandResult(message="usage: /resume <session-id>")`;
  the session store is **not** touched.
- `test_resume_unknown_id_returns_friendly_message` —
  `session_store.read("nope") == []` →
  `CommandResult(message="unknown session 'nope'. Run
  `/chats` to list.")`. `app_state.history` and
  `app_state.session_id` are unchanged.
- `test_resume_without_session_store_returns_friendly_fallback`.
- `test_resume_does_not_call_llm` — Spy on a stub LLM
  attached to `app_state.knowledge`. The command returns
  without invoking the LLM. Pins the non-blocking,
  no-LLM-call contract.

## Why these tests

- `test_settings_int_history_cap_*` pins the new Settings field
  and the validator bounds so an out-of-range value fails fast
  at boot.
- `test_session_store_listing_*` pins the metadata-only
  behaviour of `/chats` (cheap O(files), no body reads, no
  crash on missing files).
- The two REPL chat-path tests pin the new cap (`10` turns by
  default, configurable) and the on-disk persistence hook.
  Together they prove the chat turn writes one user + one
  assistant message to the `.jsonl` per turn, never
  duplicating on re-entry.
- `test_memory_*` / `test_chats_*` / `test_resume_*` pin the
  user-facing Command contracts.
- `test_resume_does_not_call_llm` is the **single** regression
  guard against re-introducing the mis-planned LLM-driven
  compaction step. If a future refactor adds a compactor call
  to `ResumeCommand`, this test fails.