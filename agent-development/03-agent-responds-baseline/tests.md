# DO-03 tests

These tests must be written **before** any code in this deliverable.

## Test files

```
tests/application/
├── __init__.py
├── test_knowledge_service.py
└── test_prompts.py

tests/presentation/
└── test_repl_chat_path.py  (new; augments test_repl.py)
```

## Test functions and assertions

### `tests/application/test_knowledge_service.py`

Uses `pytest-mock` to patch `LLMClient`.

- `test_chat_calls_llm_with_messages` — given `[UserMessage("hi")]`, `chat("hi", history=[])` calls `llm.complete(messages, model=...)` with messages ending in `UserMessage("hi")` and returns the LLM response.
- `test_chat_returns_llm_string` — `chat` returns exactly what `llm.complete` returns (string).
- `test_chat_uses_chat_model_from_settings` — captured `model` argument equals `settings.chat_model`.
- `test_learn_raises_not_implemented` — `learn("any")` raises `NotImplementedError` with message `"DO-04"`.
- `test_recall_returns_empty_list` — `recall("any")` returns `[]`.
- `test_llm_error_is_wrapped_or_re_raised_verbatim` — when `llm.complete` raises `LLMError`, `chat` re-raises it (no further wrapping; the REPL handles it).

### `tests/application/test_prompts.py`

- `test_prompts_returns_history_plus_user` — given history `[UserMessage("a"), AssistantMessage("b")]` and user `"c"`, result is exactly those three messages.
- `test_prompts_ignores_recalled_for_now` — given empty history and `recalled=["x","y"]`, result is `[UserMessage(user_message)]`.
- `test_prompts_returns_user_message_only_when_history_empty` — given `history=[]` and user `"hi"`, result is `[UserMessage("hi")]`.

### `tests/presentation/test_repl_chat_path.py`

`LLMClient` is mocked via `pytest-mock`. `prompt_toolkit.PromptSession.prompt` is patched to yield `["hello", "/exit"]`.

- `test_repl_calls_chat_for_non_slash_input` — `Repl.run()` invokes `knowledge_service.chat("hello", history=[])` once.
- `test_repl_prints_llm_response` — captured stdout contains the mocked response string.
- `test_repl_appends_to_history` — after one chat turn, `app_state.history` ends with `[UserMessage("hello"), AssistantMessage(<response>)]`.
- `test_repl_does_not_call_chat_for_slash_command` — input `["/help"]` does **not** invoke `chat`.
- `test_repl_caps_history_at_20_turns` — feeding 25 chat inputs leaves `len(app_state.history) == 40` (20 user + 20 assistant), oldest dropped.
- `test_repl_swallows_llm_error` — `knowledge_service.chat` raises `LLMError("boom")`; REPL prints `LLM error: boom` and continues to next prompt; it does **not** exit.
- `test_repl_history_persists_across_turns` — input `["a", "b", "/exit"]` → `chat` called twice with history growing between calls.

## Why these tests

- The chat path is the first README bullet. These tests are the contract that bullet is satisfied.
- The history-cap test prevents an unbounded-context DoS in long sessions.
- The `LLMError` swallow test pins the user-visible error UX without leaking the stack trace.
