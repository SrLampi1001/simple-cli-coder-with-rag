# DO-14 tests

These tests must be written **before** any code in this deliverable.

## Test files

```
tests/domain/
└── test_skill.py  (Skill protocol, SkillResult, SkillContext, SkillError)

tests/application/skills/
├── __init__.py
├── test_knowledge_base_lookup_skill.py
└── test_summarization_skill.py

tests/presentation/commands/
├── test_kb_lookup_command.py
└── test_summarize_command.py

tests/application/
└── test_session_manager_uses_summarization_skill.py  (new — pins the
    refactor of DO-13's SessionManager.maybe_compact to call the skill)

tests/presentation/
└── test_repl_chat_uses_kb_lookup_skill.py  (new — pins the refactor
    of the chat path to call the skill instead of knowledge.recall)

tests/docs/
└── test_skills_readme.py  (greps for the required headings and substrings)
```

## Test functions and assertions

### `tests/domain/test_skill.py`

- `test_skill_result_default_metadata_is_empty_dict` —
  `SkillResult(skill="x", output="y").metadata == {}`.
- `test_skill_context_default_model_is_empty_string` —
  `SkillContext().model == ""`.
- `test_skill_error_is_exception` — `issubclass(SkillError, Exception)`.

### `tests/application/skills/test_knowledge_base_lookup_skill.py`

Uses a fake `RecallCoordinator` with both `.recall()` and `.results()`.

- `test_invoke_returns_joined_output_and_hits` — coordinator stub
  returns `["a text", "b text"]` and hits
  `[{"source": "x.md", "chunk_index": 0, "similarity": 0.9},
    {"source": "y.md", "chunk_index": 1, "similarity": 0.7}]`.
  Skill returns `output="a text\n\n---\n\nb text"` (DO-09 separator)
  and `metadata["hits"] == <the same list>`.
- `test_invoke_no_recall_coordinator_returns_empty_skill_result` —
  `SkillContext(recall_coordinator=None)` → empty output, `metadata["hits"]
  == []`, no LLM call (the test asserts the LLM fake was never invoked).
- `test_invoke_legacy_recall_coordinator_returns_empty_hits` —
  coordinator has only `.recall()` (no `.results()`); skill still
  returns the joined text in `output` and `metadata["hits"] == []`;
  emits exactly one DEBUG log.
- `test_invoke_propagates_llm_error` — coordinator stub raises
  `LLMError("boom")`; the skill re-raises the same exception.
- `test_skill_metadata_hits_is_always_present` — even with empty
  recall output, `metadata["hits"]` key exists (not just absent).

### `tests/application/skills/test_summarization_skill.py`

Uses a fake `LLMClient` whose `.complete` returns a string.

- `test_invoke_empty_input_short_circuits` — `invoke(input="  ",
  context=...)` returns `output="(empty input)"`, does NOT call the LLM,
  `metadata["chars"] == 0`, `metadata["summary_chars"] == 13`.
- `test_invoke_calls_llm_with_two_message_prompt` — captured LLM call
  contains a `SystemMessage("Summarise the following text in 150-300
  prose words: errors, decisions, key facts, current state.")` and a
  `UserMessage(input)`.
- `test_invoke_strips_whitespace_from_reply` — LLM returns `"  hello
  \n"`; skill output is `"hello"`.
- `test_invoke_propagates_llm_error` — LLM stub raises
  `LLMError("boom")`; skill re-raises verbatim.
- `test_invoke_no_llm_and_no_model_raises_skill_error` — context has
  `llm=None` and `model=""`; skill raises `SkillError("no model
  configured")`.
- `test_invoke_metadata_records_input_and_summary_lengths` —
  `metadata["chars"] == len(input)` and `metadata["summary_chars"] ==
  len(output.strip())`.

### `tests/presentation/commands/test_kb_lookup_command.py`

Uses the standard `AppState` test fixture from `tests/presentation/conftest.py`.

- `test_kb_lookup_command_prints_chunks_and_sources` — fake skill
  returns two hits; command prints the chunk text and the footer
  `hits: 2 (sources: x.md#0, y.md#1)`.
- `test_kb_lookup_command_no_args_prints_usage` — calling with no query
  prints `usage: /kb-lookup <query>` and does NOT invoke the skill.
- `test_kb_lookup_command_swallows_llm_error` — fake skill raises
  `LLMError`; REPL prints `LLM error: <reason>` and continues (does NOT
  re-raise).
- `test_kb_lookup_command_returns_continue_action` — even on usage and
  on error, the command's `execute` returns
  `CommandResult(action="continue", message="...")`. It never exits
  the REPL.

### `tests/presentation/commands/test_summarize_command.py`

- `test_summarize_command_prints_summary_and_counts` — fake skill
  returns `output="hi"`, `metadata={"chars": 100, "summary_chars": 2}`;
  REPL prints `summary: hi` and `chars: 100 -> summary_chars: 2`.
- `test_summarize_command_no_args_prints_usage` — calling with no
  text prints `usage: /summarize <text>` and does NOT invoke the skill.
- `test_summarize_command_swallows_llm_error` — fake skill raises
  `LLMError`; REPL prints `LLM error: <reason>` and continues.
- `test_summarize_command_returns_continue_action` — same as
  `kb-lookup`: never exits.

### `tests/application/test_session_manager_uses_summarization_skill.py`

Builds a real `SessionManager` (DO-12) with a stub `Compactor` whose
`summarize` returns `"OLD_DO12_SUMMARY"`, and a `SummarizationSkill`
fake that returns `"NEW_DO14_SUMMARY"`. The transcript is 11 messages
long, forcing `maybe_compact` to trigger.

- `test_session_manager_maybe_compact_uses_summarization_skill` — the
  persisted summary in `<root>/<sid>.summary.json` is
  `"NEW_DO14_SUMMARY"` (i.e. the skill ran, not the compactor).
- `test_session_manager_maybe_compact_calls_summarize_skill_once` —
  the skill fake's call count is `1` (one per compaction, not per
  message).
- `test_session_manager_maybe_compact_does_not_touch_compactor_summarize`
  — the compactor's `summarize` call count is `0`; the DO-12 method
  remains untouched.

### `tests/presentation/test_repl_chat_uses_kb_lookup_skill.py`

Builds an `AppState` with a fake `LLMClient` and a stub
`KnowledgeService` whose `.recall` would raise if called. The chat
path is fed `"hello"`; the REPL must not raise and the
`KnowledgeBaseLookupSkill` fake's call count must be `1`.

- `test_repl_chat_uses_kb_lookup_skill` — chat path invokes
  `KnowledgeBaseLookupSkill.invoke(...)`, not
  `knowledge.recall(...)`. The stub's `recall` is never called.
- `test_repl_chat_stashes_last_retrieval_hits` — after one chat turn,
  `app_state.last_retrieval_hits` equals the skill's
  `metadata["hits"]` (a list of `{source, chunk_index, similarity}`
  dicts).
- `test_repl_chat_propagates_llm_error` — the skill raises
  `LLMError`; the REPL prints `LLM error: <reason>` and continues —
  matching the DO-12 chat-path contract.

### `tests/docs/test_skills_readme.py`

Greps the README files for required sections and substrings.

- `test_skills_readme_mentions_both_skills_and_auto_invocation` —
  `/skills/README.md` contains the literal strings
  `knowledge-base-lookup`, `summarization`, and `Auto-invocation`.
- `test_kb_lookup_readme_has_purpose_input_output_invocation_demo` —
  `/skills/knowledge-base-lookup/README.md` contains the H5 headings
  `## Purpose`, `## Expected input`, `## Expected output`, `##
  Invocation`, `## Working demo`, and the substring `Auto-invoked`.
- `test_summarization_readme_has_purpose_input_output_invocation_demo`
  — same five H5 headings + `Auto-invoked` substring in
  `/skills/summarization/README.md`.

## Why these tests

- The two skill tests pin the metadata shape (`hits`, `chars`,
  `summary_chars`) that the slash commands and the chat path depend
  on. If a future refactor renames a metadata key, the slash-command
  tests fail loudly with the actual key.
- The `test_session_manager_maybe_compact_uses_summarization_skill`
  test pins the **non-breaking** refactor: DO-12's `Compactor.summarize`
  is preserved verbatim, but `/compact`'s underlying call goes through
  the skill. If a future change moves the call back to the compactor,
  the test fails.
- The `test_repl_chat_uses_kb_lookup_skill` test pins the **same**
  pattern for the chat path: the recall coordinator API is unchanged
  (DO-09 contract preserved), but the REPL routes through the skill.
- The doc tests catch the regression where a README loses its
  `Auto-invoked` paragraph — a working demo of *automatic* use is the
  whole point of this deliverable.