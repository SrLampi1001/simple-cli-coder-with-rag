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
│   └── test_llm_client_adapter.py   # covers whichever adapter strategy the research selects
└── presentation/
    └── test_app_state_carries_llm.py
```

## Test functions and assertions

### `tests/domain/test_messages.py`

(unchanged from the original plan)
- `test_user_message_role_default`, `test_assistant_message_role_default`, `test_system_message_role_default`
- `test_message_union_validation` — passing an unknown `role` (e.g. `"junior"`) to `Message.model_validate(...)` raises `ValidationError`. **Note:** DO-10 adds a legitimate `"tool"` role, so this test must be updated then to use a genuinely unknown role instead of `"tool"`.
- `test_assistant_turn_default_empty_tool_calls`
- `test_tool_call_round_trip`

### `tests/domain/test_llm_client_protocol.py`

(unchanged)
- `test_protocol_has_complete_method`, `test_protocol_has_complete_with_tools`, `test_llm_error_exists`.

### `tests/infrastructure/test_settings.py`

Uses `monkeypatch.setenv` to override env and `tmp_path` for an isolated `.env`.

- `test_settings_loads_nvidia_key_from_env` — passing `nvidia_api_key=SecretStr("nv-test")` returns the same `SecretStr`.
- `test_settings_loads_mistral_key_from_env` — same for `mistral_api_key`.
- `test_settings_loads_minimax_key_from_env` — same for `minimax_api_key`.
- `test_settings_loads_from_dotenv` — write a `tmp_path/.env` with `NVIDIA_API_KEY=nv-dotenv`, instantiate with `_env_file`, assert the key matches.
- `test_settings_rejects_empty_default_provider_key_nvidia` — with `default_provider="nvidia"` and empty `nvidia_api_key`, `Settings(...)` raises `RuntimeError` (not `ValidationError`).
- `test_settings_rejects_empty_default_provider_key_mistral` — same for `default_provider="mistral"`.
- `test_settings_rejects_empty_default_provider_key_minimax` — same for `default_provider="minimax"`.
- `test_settings_allows_empty_keys_for_inactive_providers` — with `default_provider="nvidia"` and `nvidia_api_key=SecretStr("nv")`, the other two keys may be `SecretStr("")` without raising.
- `test_settings_default_provider` — default value of `default_provider` is `"nvidia"`.
- `test_settings_repr_masks_keys` — `repr(Settings(nvidia_api_key=SecretStr("nv-secret"), mistral_api_key=SecretStr("ms-secret"), minimax_api_key=SecretStr("mx-secret")))` contains none of the three literals.

### `tests/infrastructure/test_llm_client_adapter.py`

Uses `pytest-mock` (`mocker`) to patch the vendor SDK / HTTP layer. The exact module to patch depends on the adapter strategy chosen by the research; if there are multiple adapters (one per provider), this file may split into `test_nvidia_adapter.py`, `test_mistral_adapter.py`, `test_minimax_adapter.py`. The assertion shape is the same in each case.

- `test_complete_returns_text` — given a stub backend returning text, the adapter's `complete([UserMessage(content="hi")], model=<provider's default model>)` returns that text.
- `test_complete_passes_messages_and_model` — captured args contain the model and the transformed message list (vendor types are mapped to the SDK's shape).
- `test_complete_wraps_vendor_error` — when the stub raises a vendor error (`anthropic.APIError`, `httpx.HTTPError`, or whatever the research surfaces), the adapter raises `LLMError` (not the vendor type).
- `test_complete_with_tools_stub_returns_assistant_turn` — `complete_with_tools` returns an `AssistantTurn` whose `content` matches the stub and whose `tool_calls` is empty (acceptable for this deliverable).
- `test_adapter_holds_one_sdk_instance` — patching the SDK constructor and inspecting `call_count == 1` after construction.
- `test_adapter_uses_provider_base_url` (only when the strategy requires a non-default `base_url`) — the captured SDK constructor args include the expected `base_url`.

### `tests/presentation/test_app_state_carries_llm.py`

(unchanged from the original plan)
- `test_app_state_has_llm_field` — `AppState` has an `llm: LLMClient | None = None` field.
- `test_composition_root_wires_settings_and_client` — invoking `main([])` in a test (with `Repl.run` patched) instantiates `Settings`, builds the adapter for `default_provider`, and assigns it to `app_state.llm`.

## Why these tests

- `test_settings_*` pins the secrets handling contract for the three providers, and that only the active provider's key is required.
- `test_llm_client_adapter_*` pins the Adapter pattern: vendor types do not leak, regardless of which SDK the research selects per provider.
- `test_messages_*` pins the schema used by DO-04 onwards.
- The `app_state.llm` test ensures the composition root actually wires things — it is easy to forget and break DO-03.