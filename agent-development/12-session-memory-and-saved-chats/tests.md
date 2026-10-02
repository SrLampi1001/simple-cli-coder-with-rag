# DO-12 tests

These tests must be written **before** any code in this deliverable.
They MUST fail on the DO-11 state (no
`infrastructure/token_counters/char_estimate.py`, no
`application/session_manager.py`, no summary read/write on
`SessionStore`, no `/memory`/`/chats`/`/resume`/`/compact`,
`AppState.history_cap=20` still present, no `ProviderConfig.context_window`
field) and MUST pass before DO-12 is marked done.

## Test files

```
tests/
├── infrastructure/
│   └── token_counters/
│       ├── __init__.py
│       └── test_char_estimate.py              # NEW — concrete class math
├── application/
│   ├── test_compactor_summarize.py            # NEW — summarize() method
│   ├── test_session_store_summary.py          # NEW — write/read summary
│   ├── test_session_manager.py                # NEW — orchestrator lifecycle
│   └── test_knowledge_service_auto_compact.py # NEW — pre-call hook
└── presentation/
    └── commands/
        ├── test_memory.py                     # NEW
        ├── test_chats.py                      # NEW
        ├── test_resume.py                     # NEW — incl. wall-clock block
        └── test_compact.py                    # NEW
```

`supplementary` (renames + add a new test):

- `tests/infrastructure/providers/test_provider_config.py` — add
  `test_provider_config_rejects_context_window_below_minimum` and
  `test_provider_config_default_context_window_is_anthropic_two_hundred`.

**Removed** from the original draft:
- `tests/domain/test_token_counter.py` — no Protocol seam.
- `tests/application/test_session_manager_resume_blocks.py` — folded
  into `test_resume.py`.
- `tests/presentation/commands/test_resume_blocks_during_compaction.py`
  — folded into `test_resume.py`.

## Test functions and assertions

### `tests/infrastructure/token_counters/test_char_estimate.py`

Pure-stdlib assertions. No mocks needed.

- `test_count_empty_messages_returns_zero` —
  `CharEstimateTokenCounter().count([], tools=(), recalled=()) ==
  0`.
- `test_count_single_short_user_message_returns_one` —
  `count([UserMessage("hi")]) == 1` (`ceil(2/3) = 1`).
- `test_count_120_char_user_message_returns_forty` —
  `count([UserMessage("x" * 120)]) == 40`.
- `test_count_includes_assistant_tool_calls_json` —
  `count([AssistantMessage(content="ok", tool_calls=[ToolCall(
  id="1", name="read", arguments={"path":"/a/b/c.py"})])])` equals
  the message text contribution plus
  `ceil((len(json.dumps([call])) + 1 + 1 + 4) / 3)` for the tool
  call. Pin the exact integer.
- `test_count_includes_tool_result_message_tool_call_id` —
  `count([ToolResultMessage(tool_call_id="abc123",
  content="some result text")])` equals the message text
  contribution plus the tool_call_id character count divided by 3.
- `test_count_includes_tool_specs` —
  `count([], tools=(ToolSpec(name="read", description="Read a
  file",
  input_schema={"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}),))
  == ceil((4 + len(description) + len(json.dumps(schema))) / 3)`.
- `test_count_includes_recalled_chunks` —
  `count([], recalled=("some text",)) == 3` (chars-per-4 for
  recalled chunks).
- `test_count_recalled_uses_chars_per_four` —
  `count([], recalled=("a" * 80,)) == 20`.
- `test_count_sums_all_inputs` — given a representative mix,
  `count(messages, tools=..., recalled=...)` equals
  `sum_of_components` (each component tested in isolation above).
- `test_count_returns_int` — return type is exactly `int`, not
  `float` or `Decimal`.
- `test_count_does_not_raise_on_missing_tool_call_id` — a
  `ToolResultMessage(tool_call_id="", content="...")` returns the
  integer without raising.
- `test_count_does_not_raise_on_malformed_tool_arguments` — a
  `ToolCall(id="1", name="read", arguments=None)` returns an
  integer (the JSON serialiser coerces `None` to `null`).

### `tests/application/test_compactor_summarize.py`

Uses `mocker` to patch `LLMClient.complete` (the compactor's LLM
call). No real network.

- `test_summarize_empty_messages_short_circuits` —
  `Compactor(llm_mock, "m").summarize([]) == "(empty session)"`.
  The LLM is **not** called.
- `test_summarize_non_empty_calls_llm` —
  `summarize([UserMessage("yo"), AssistantMessage("hi")])` calls
  `llm.complete(...)` exactly once with `model="m"` and a
  **two-message** prompt: `[SystemMessage("Summarise this coding
  session in 150-300 prose words: errors, decisions, files touched,
  current task."), UserMessage(<transcript>)]`. **No** schema
  description, **no** trailing reminder.
- `test_summarize_returns_raw_reply` — given a stub returning
  `"the summary text"`, the method returns `"the summary text"`
  verbatim. **No** fence stripping, **no** JSON validation.
- `test_summarize_returns_stripped_whitespace` — given a stub
  returning `"  the summary text  \n"`, the method returns
  `"the summary text"` (`str.strip()` applied).
- `test_summarize_propagates_llm_error` — stub raising
  `LLMError("boom")` causes `summarize` to raise the same
  `LLMError` (not wrapped).
- `test_summarize_does_not_write_to_disk` — `SessionStore` is
  never touched (the compactor does not own disk writes; the
  caller does).

### `tests/application/test_session_store_summary.py`

Uses `tmp_path`; no real disk outside the temp dir.

- `test_write_session_summary_creates_summary_file` —
  `SessionStore(tmp_path).write_session_summary("sid",
  "the summary")` writes `<tmp_path>/sid.summary.json` with
  JSON `{"session_id": "sid", "created_at": "<ISO>", "summary":
  "the summary"}`.
- `test_read_session_summary_returns_text` —
  `read_session_summary("sid") == "the summary"` after the write.
- `test_read_session_summary_returns_none_when_missing` —
  `read_session_summary("nope") is None`.
- `test_write_session_summary_is_idempotent` — calling `write`
  twice replaces the file (same contract as `write_compacted`).
- `test_write_session_summary_creates_missing_root` —
  `SessionStore(tmp_path / "new_root").write_session_summary("sid",
  "...")` creates the directory tree.
- `test_summary_file_does_not_collide_with_jsonl` — a `.jsonl`
  named `sid.jsonl` and a `.summary.json` named
  `sid.summary.json` coexist on disk without overwriting.
- `test_summary_round_trips_unicode` — non-ASCII content
  (`"日本語"`) survives the JSON round-trip.

### `tests/application/test_session_manager.py`

Uses `mocker` for `Compactor.summarize` and a real
`CharEstimateTokenCounter`. No real disk; uses a
`tmp_path`-backed `SessionStore`.

- `test_current_token_estimate_calls_counter` —
  `current_token_estimate(recalled=("r",), tools=(tool,))` calls
  `token_counter.count(history, recalled=("r",), tools=(tool,))`
  exactly once and returns the counter's int.
- `test_effective_budget_subtracts_response_and_buffer` —
  `effective_budget() == context_window - max_response_tokens -
  safety_buffer`.
- `test_maybe_compact_before_chat_returns_false_under_threshold`
  — stub returning `int(threshold * budget) - 1`. The method
  returns `False` and `compactor.summarize` is not called.
- `test_maybe_compact_before_chat_returns_true_over_threshold` —
  stub returning `int(threshold * budget) + 1`. The method
  returns `True` and `compactor.summarize` is called exactly
  once.
- `test_maybe_compact_before_chat_swallows_compactor_failure` —
  `compactor.summarize` raising `LLMError`. The method returns
  `False`, no exception propagates, the history is left
  unchanged.
- `test_compact_replaces_history_with_summary_and_last_n` —
  given history of 30 messages and `keep_last_n_messages=10`,
  after `compact()` the history is `[SystemMessage(summary),
  ...last_10]` (length 11).
- `test_compact_persists_summary` — after `compact()`,
  `session_store.read_session_summary(session_id) ==
  summary_text`.
- `test_compact_no_op_when_history_shorter_than_keep_last_n` —
  history of 5 messages with `keep_last_n_messages=10`. After
  `compact()`, history is unchanged.
- `test_resume_loads_full_transcript_and_compacts` — pre-write
  `<id>.jsonl` with 50 messages. `resume(id)` returns the
  summary string, history becomes
  `[summary, *last_10]`, `.summary.json` is written.
- `test_resume_unknown_session_returns_none` —
  `resume("nope")` returns `None` (no exception class).
  `SessionStore.read("nope")` returns `[]`; the manager treats
  the empty transcript as "unknown id".
- `test_resume_short_transcript_loads_verbatim` — pre-write
  `<id>.jsonl` with 3 messages and `keep_last_n_messages=10`.
  `resume(id)` returns the summary (which is `"(empty session)"`
  because there is nothing to summarise), history is exactly the
  3 raw messages, no summary file is written (the compactor
  short-circuits).
- `test_resume_rebinds_active_session_id` — after
  `resume("other")`, `app_state.session_id == "other"`.
- `test_list_sessions_returns_sorted_tuples` — pre-write three
  `.jsonl` files with different mtimes; `list_sessions()` returns
  them sorted by mtime descending, each entry is a 4-tuple
  `(str, float, int, bool)` (no NamedTuple unpacking needed).
- `test_list_sessions_marks_summary_presence` — pre-write
  `sid.summary.json` alongside `sid.jsonl`; the corresponding
  tuple's `has_summary` field is `True`.
- `test_list_sessions_empty_root_returns_empty_list` —
  `list_sessions()` on an empty directory returns `[]`.

### `tests/application/test_knowledge_service_auto_compact.py`

Uses `mocker` for `SessionManager` and `LLMClient`.

- `test_chat_calls_maybe_compact_before_llm_call` —
  `KnowledgeService(..., session_manager=sm_mock).chat(...)` calls
  `sm_mock.maybe_compact_before_chat(...)` **before**
  `llm.complete_with_tools(...)`. The test patches `LLMClient`
  and asserts call order via `mock_calls`.
- `test_chat_skips_compaction_when_session_manager_is_none` —
  constructing `KnowledgeService` without a `session_manager`
  and calling `chat(...)` does **not** raise.

### `tests/presentation/commands/test_memory.py`

- `test_memory_with_session_manager_returns_readout` — stub
  `session_manager.current_token_estimate` returning `1000`,
  `session_manager.effective_budget` returning `180000`,
  `session_manager.session_id` returning `"abc1234567deadbeef"`,
  and `app_state.provider_config.context_window = 200000`,
  `provider_config.default_model = "claude-3-5-sonnet-latest"`.
  The Command's `message` contains every pinned line
  (`"session:"`, `"messages:"`, `"tokens:"`, `"budget:"`,
  `"threshold:"`, `"free:"`, `"model:"`) and the rounded percent
  (`4.9%`).
- `test_memory_without_provider_config_uses_placeholder` —
  `app_state.provider_config = None`; the Command still emits a
  readout but uses `"(no provider configured)"` for the `model:`
  line.
- `test_memory_without_session_manager_returns_friendly_fallback` —
  `app_state.session_manager = None`; returns the friendly message.
- `test_memory_does_not_mutate_state` — the Command reads the
  app_state but does not write back to it.

### `tests/presentation/commands/test_chats.py`

- `test_chats_renders_table_for_three_sessions` — stub
  `session_manager.list_sessions` returning
  `[("abc1234567...", 12345.0, 18, True),
   ("a1b2c3d4ef...", 1000.0, 38, True),
   ("5e6f7g8h...", 100.0, 204, False)]`. The Command's message
  contains the three ids, the three relative times, the three
  message counts, and the three `summary?` flags. The table is
  fixed-width and sorted by mtime desc.
- `test_chats_includes_active_id_line` — message ends with
  `active: <id>`.
- `test_chats_empty_list_returns_friendly_message` —
  `list_sessions() == []`; `command.message == "No saved sessions
  yet."`.
- `test_chats_without_session_manager_returns_friendly_fallback`.

### `tests/presentation/commands/test_resume.py`

- `test_resume_with_valid_id_calls_session_manager_resume` —
  `ResumeCommand().execute(...)` with a valid id calls
  `session_manager.resume(<id>)` and returns
  `CommandResult(message="resumed <id> (<kept> kept of <total>
  messages; summary + last 10 turns).")`.
- `test_resume_missing_id_returns_friendly_message` — input
  `"/resume"` (no arg) → `CommandResult(message=<fallback>)`;
  `session_manager.resume` is **not** called.
- `test_resume_unknown_id_returns_friendly_message` —
  `session_manager.resume` returning `None` causes the Command to
  return
  `"unknown session '<id>'. Run `/chats` to list."`. **No**
  exception is raised.
- `test_resume_blocks_while_compactor_runs` — **wall-clock
  assertion.** Patch `session_manager._compactor.summarize` with
  a stub that sleeps 0.2 s and returns `"summary"`. Measure the
  elapsed wall-clock around `ResumeCommand().execute(...)`. Assert
  `elapsed >= 0.2` (the Command is synchronous). This is the
  **single** regression guard for option B.
- `test_resume_without_session_manager_returns_friendly_fallback`.

### `tests/presentation/commands/test_compact.py`

- `test_compact_with_session_manager_compacts_and_returns` —
  `CompactCommand().execute(...)` calls
  `session_manager.compact()` and returns the formatted message.
- `test_compact_without_session_manager_returns_friendly_fallback`.

### `tests/infrastructure/providers/test_provider_config.py` (DO-11 patch)

- `test_provider_config_rejects_context_window_below_minimum` —
  `ProviderConfig(..., context_window=512)` raises
  `ValidationError`.
- `test_provider_config_default_context_window_is_anthropic_two_hundred`
  — instantiating `ProviderRegistry(tmp_path / "providers.json")`
  on a fresh dir writes the `anthropic` entry with
  `context_window == 200_000`.

## Why these tests

- `test_char_estimate_*` pins the math for the only token counter
  Strategy. The exact integer assertions are the regression guard;
  any future change to the estimate must be deliberate.
- `test_compactor_summarize_*` pins the **separation** between
  `Compactor.compact()` (JSON for RAG) and `Compactor.summarize()`
  (prose for session). The two-message-prompt test pins the
  brevity. A future "let's share more code" pull request will
  fail these.
- `test_session_store_summary_*` pins the on-disk shape of
  `<id>.summary.json`.
- `test_session_manager_*` pins the orchestrator's lifecycle: budget
  math, compaction trigger, persistence, error swallowing.
  `test_resume_unknown_session_returns_none` is the
  no-`UnknownSessionError` contract.
- `test_knowledge_service_auto_compact_*` pins the hook between
  the chat loop and `SessionManager`.
- `test_memory_*` / `test_chats_*` / `test_resume_*` /
  `test_compact_*` pin the user-facing Command contracts.
- `test_resume_blocks_while_compactor_runs` is the **single
  regression guard** for option B. If a future refactor turns
  `resume` into a background task, the wall-clock assertion
  fails.
- `test_provider_config_*` (DO-11 patch) pins the schema change
  in DO-11's test suite.