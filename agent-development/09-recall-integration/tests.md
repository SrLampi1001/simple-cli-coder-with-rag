# DO-09 tests

These tests must be written **before** any code in this deliverable.

## Test files

```
tests/application/
├── test_trivial_gate.py
├── test_recall_coordinator.py
├── test_prompts_with_recall.py  (replaces the DO-03 prompts test)
└── test_knowledge_service_recall_with_coordinator.py  (replaces the DO-08 recall test)

tests/presentation/
└── test_repl_recall_path.py
```

## Test functions and assertions

### `tests/application/test_trivial_gate.py`

- `test_short_string_is_trivial` — `is_trivial("hi")` is True.
- `test_short_word_count_is_trivial` — `is_trivial("how are you")` is True (3 words).
- `test_long_prompt_is_not_trivial` — `is_trivial("why does ModuleNotFoundError happen for foo")` is False.
- `test_long_string_is_not_trivial` — `is_trivial("a" * 25)` is False.
- `test_boundary_chars` — `is_trivial("a" * 20)` is True (boundary inclusive).
- `test_boundary_words` — `is_trivial("one two three four")` is True (boundary inclusive).

### `tests/application/test_recall_coordinator.py`

- `test_trivial_prompt_skips_retriever` — `recorder_retriever` is never called when `is_trivial` is True.
- `test_long_prompt_calls_retriever_with_top_k` — retriever called once with `top_k=3`; result text returned.
- `test_similarity_threshold_filters_chunks` — retriever returns `[(c1, 0.9), (c2, 0.3)]`; threshold `0.5`; result is `[c1.text]`.
- `test_embedder_not_ready_returns_empty` — retriever raises `EmbedderNotReady`; result is `[]`.
- `test_timeout_returns_empty` — retriever wrapped in `TimeoutRetriever(timeout=0.05, executor=...)` against a blocking inner; result is `[]` within ~100 ms.
- `test_top_k_passed_through` — `RecallCoordinator(..., top_k=5)` calls retriever with `top_k=5`.

### `tests/application/test_prompts_with_recall.py`

- `test_with_recalled_injects_system_message` — `build_chat_messages("q", [], ["a", "b"])` returns `[SystemMessage("The following context may be relevant:\n\na\n\n---\n\nb"), UserMessage("q")]`.
- `test_with_empty_recalled_no_system_message` — `build_chat_messages("q", [], [])` returns `[UserMessage("q")]`.
- `test_recalled_preserves_history_order` — `build_chat_messages("q", [UserMessage("p"), AssistantMessage("r")], ["a"])` returns `[SystemMessage(...), UserMessage("p"), AssistantMessage("r"), UserMessage("q")]`.

### `tests/application/test_knowledge_service_recall_with_coordinator.py`

- `test_recall_delegates_to_coordinator` — `KnowledgeService.recall` calls `RecallCoordinator.recall` and returns its result.
- `test_recall_top_k_override` — `recall("q", top_k=7)` overrides the default top_k.

### `tests/presentation/test_repl_recall_path.py`

- `test_repl_calls_recall_before_chat` — input `["why does this fail"]` → `knowledge.recall` called once with that input, then `knowledge.chat` called once.
- `test_repl_passes_recall_result_to_chat` — `knowledge.recall` returns `["memory"]`; captured `chat` args show the recalled list is passed (the system message contains `"memory"`).
- `test_repl_skips_recall_for_slash_command` — input `["/help"]` → `knowledge.recall` not called.
- `test_repl_skips_recall_for_trivial_prompt` — input `["hi"]` → `knowledge.recall` returns `[]` (gate triggers).
- `test_repl_does_not_block_when_embedder_not_ready` — `embedder.is_ready()` is False; `recall` returns `[]`; chat still proceeds without delay.

## Why these tests

- The trivial-gate boundary tests pin the inclusive `<=` semantics, which is easy to off-by-one.
- The threshold test pins the "strong matches only" rule from the README latency tips.
- The REPL integration test pins the "recall runs concurrently / before prompt prep" behavior in user-visible terms.
