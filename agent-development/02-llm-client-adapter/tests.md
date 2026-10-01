# DO-02 tests

These tests must be written **before** any code in this deliverable. They MUST fail on the DO-01 state (no `infrastructure/llm/`, no `domain/messages.py`) and MUST pass before DO-02 is marked done.

## Test files

```
tests/
├── domain/
│   ├── __init__.py
│   ├── test_messages.py
│   └── test_llm_client_protocol.py
├── infrastructure/
│   ├── __init__.py
│   ├── test_settings.py
│   └── test_anthropic_client.py
└── presentation/
    └── test_app_state_carries_llm.py  (added in DO-02; co-located with the import wiring)
```

## Test functions and assertions

### `tests/domain/test_messages.py`

- `test_user_message_role_default` — `UserMessage(content="hi").role == "user"`.
- `test_assistant_message_role_default` — `AssistantMessage(content="hi").role == "assistant"`.
- `test_system_message_role_default` — `SystemMessage(content="hi").role == "system"`.
- `test_message_union_validation` — passing `role="tool"` to `Message.model_validate(...)` raises `ValidationError`.
- `test_assistant_turn_default_empty_tool_calls` — `AssistantTurn(content="hi").tool_calls == []`.
- `test_tool_call_round_trip` — `ToolCall(id="1", name="x", arguments={"a": 1}).model_dump()` round-trips.

### `tests/domain/test_llm_client_protocol.py`

- `test_protocol_has_complete_method` — `hasattr(LLMClient, "complete")` and signature is `(self, messages, *, model)`.
- `test_protocol_has_complete_with_tools` — same for `complete_with_tools`.
- `test_llm_error_exists` — `LLMError` is importable and is an `Exception` subclass.

### `tests/infrastructure/test_settings.py`

Uses `monkeypatch.setenv` to override env; `tmp_path` for an isolated `.env`.

- `test_settings_loads_anthropic_key_from_env` — `Settings(anthropic_api_key=SecretStr("sk-test"))` (passed directly to avoid disk I/O) returns the same `SecretStr`.
- `test_settings_loads_from_dotenv` — write a `tmp_path/.env` with `ANTHROPIC_API_KEY=sk-dotenv`, instantiate `Settings(_env_file=str(tmp_path/".env"))`, assert the key matches.
- `test_settings_rejects_empty_key` — instantiating with empty key raises `RuntimeError` (not `ValidationError`).
- `test_settings_default_chat_model` — `Settings(...).chat_model == "claude-sonnet-4-5"`.
- `test_settings_default_compactor_model` — `Settings(...).compactor_model == "claude-haiku-4-5"`.
- `test_settings_repr_masks_key` — `repr(Settings(anthropic_api_key=SecretStr("sk-supersecret")))` does **not** contain `"sk-supersecret"`.
- `test_settings_str_masks_key` — `str(settings)` likewise.

### `tests/infrastructure/test_anthropic_client.py`

Uses `pytest-mock` (`mocker`) to patch `anthropic.Anthropic`.

- `test_complete_returns_message_text` — given a stub SDK whose `messages.create` returns a `Message` with `content=[TextBlock(text="hello")]`, `AnthropicLLMClient(settings).complete([UserMessage(content="hi")], model="claude-sonnet-4-5")` returns `"hello"`.
- `test_complete_passes_messages_and_model` — captured args contain the model and a transformed message list (vendor types are mapped to the SDK's shape).
- `test_complete_wraps_api_error` — stub SDK raises `anthropic.APIError`; client raises `LLMError` (not `APIError`).
- `test_complete_with_tools_stub_returns_assistant_turn` — `complete_with_tools` returns an `AssistantTurn` whose `content` matches the stub and whose `tool_calls` is empty (acceptable for this deliverable).
- `test_anthropic_client_holds_one_sdk_instance` — patching `anthropic.Anthropic` and inspecting `call_count == 1` after construction.

### `tests/presentation/test_app_state_carries_llm.py`

- `test_app_state_has_llm_field` — `AppState` has an `llm: LLMClient | None = None` field.
- `test_composition_root_wires_settings_and_client` — invoking `main([])` in a test (with `Repl.run` patched) instantiates `Settings`, builds `AnthropicLLMClient`, and assigns it to `app_state.llm`.

## Why these tests

- `test_settings_*` pins the secrets handling contract from the master README.
- `test_anthropic_client_*` pins the Adapter pattern: vendor types do not leak.
- `test_messages_*` pins the schema used by DO-04 onwards.
- The `app_state.llm` test ensures the composition root actually wires things — it is easy to forget and break DO-03.
