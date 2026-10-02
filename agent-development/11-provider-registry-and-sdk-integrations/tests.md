# DO-11 tests

These tests must be written **before** any code in this deliverable. They MUST fail on the DO-10 state (no `infrastructure/providers/`, no `infrastructure/llm/openai_client.py`, `openai_compat.py` still exists, `Settings` still has `*_api_key` fields) and MUST pass before DO-11 is marked done.

## Test files

```
tests/
├── infrastructure/
│   ├── llm/
│   │   ├── test_anthropic_client.py             # renamed from test_anthropic_compat_adapter.py
│   │   ├── test_openai_client.py                 # NEW
│   │   ├── test_openai_compat_adapter.py        # DELETED in step 8
│   │   └── test_build_llm_client.py             # NEW
│   └── providers/
│       ├── __init__.py
│       ├── test_provider_config.py              # Pydantic models
│       ├── test_providers_file.py               # round-trip + secrets
│       └── test_provider_registry.py            # CRUD + atomic write + first-run seeding
├── presentation/
│   └── commands/
│       ├── test_connect.py                      # NEW
│       ├── test_providers.py                    # NEW
│       ├── test_provider.py                     # NEW
│       └── test_provider_switch_chat_path.py    # NEW — switching provider mid-session works
└── application/
    └── test_knowledge_service_set_llm.py        # NEW — KnowledgeService.set_llm(...) exists
```

## Test functions and assertions

### `tests/infrastructure/providers/test_provider_config.py`

- `test_provider_config_openai` — `ProviderConfig(adapter="openai", base_url="https://x", default_model="m", context_window=128000, api_key=SecretStr("k"))` round-trips through `model_dump()` / `model_validate(...)`.
- `test_provider_config_anthropic` — same with `adapter="anthropic"`.
- `test_provider_config_rejects_unknown_adapter` — `ProviderConfig(adapter="cohere", ...)` raises `ValidationError`.
- `test_provider_config_rejects_non_https_base_url` — `ProviderConfig(adapter="openai", base_url="http://x", default_model="m", context_window=128000)` raises `ValidationError` (validator).
- `test_provider_config_rejects_empty_model` — `default_model=""` raises `ValidationError`.
- `test_provider_config_rejects_context_window_below_minimum` — `context_window=512` raises `ValidationError` (the `Field(ge=1024)` constraint). Added for DO-12's `SessionManager` consumption.
- `test_provider_config_default_context_window_is_anthropic_two_hundred` — instantiating `ProviderRegistry(tmp_path / "providers.json")` on a fresh dir writes the `anthropic` entry with `context_window == 200_000`. Pinned for DO-12's `SessionManager.effective_budget()`.
- `test_provider_config_repr_masks_api_key` — `repr(...)` does not contain the literal key.
- `test_provider_config_forbids_extra_keys` — `ProviderConfig(adapter="openai", base_url="https://x", default_model="m", context_window=128000, typo="x")` raises `ValidationError`.
- `test_provider_config_default_api_key_is_empty_secret` — a freshly constructed `ProviderConfig` has `api_key == SecretStr("")` and `get_secret_value() == ""`.

### `tests/infrastructure/providers/test_providers_file.py`

- `test_providers_file_empty` — `ProvidersFile()` round-trips with `active_provider_id=""` and `providers={}`.
- `test_providers_file_dump_masks_api_keys` — given a `ProvidersFile` whose `providers: {"p": ProviderConfig(..., api_key=SecretStr("sk-supersecret"))}`, `model_dump_json()` does **not** contain `"sk-supersecret"` (pydantic's SecretStr emits `"**********"`).
- `test_providers_file_forbids_extra_keys` — `ProvidersFile(unknown_field="x")` raises `ValidationError`.

### `tests/infrastructure/providers/test_provider_registry.py`

Uses `tmp_path` for the JSON path; no real LLM calls.

- `test_registry_seeds_five_providers_when_missing` — instantiating `ProviderRegistry(tmp_path / "providers.json")` on a fresh directory writes the file with the five pre-populated entries (`nvidia`, `mistral`, `minimax`, `anthropic`, `openai`), each with empty `api_key` and `active_provider_id = ""`.
- `test_registry_seeding_is_idempotent` — calling `ProviderRegistry(...)` twice does not overwrite an existing file (the second call reads it).
- `test_registry_get_known_id` — `registry.get("openai").adapter == "openai"`.
- `test_registry_get_unknown_raises` — `registry.get("nope")` raises `UnknownProviderError`.
- `test_registry_active_empty_raises` — `registry.active()` raises `NoActiveProviderError` when `active_provider_id == ""`.
- `test_registry_set_active_persists` — `registry.set_active("openai")` writes `active_provider_id: "openai"` to the file. Re-instantiating reads it.
- `test_registry_set_active_unknown_raises` — `registry.set_active("nope")` raises `UnknownProviderError` and does not write.
- `test_registry_list_sorted` — `registry.list()` returns entries sorted by id (`anthropic, minimax, mistral, nvidia, openai`).
- `test_registry_upsert_merges_single_entry` — calling `registry.upsert("openai", new_config)` reads the file, replaces only the `openai` entry, writes the file atomically, and leaves the other four untouched.
- `test_registry_upsert_creates_new_entry` — `registry.upsert("myproxy", ProviderConfig(adapter="openai", base_url="https://x", default_model="m"))` writes a sixth entry and the JSON validates as `ProvidersFile`.
- `test_registry_remove_idempotent` — `registry.remove("nope")` is a no-op; `registry.remove("minimax")` removes the entry and persists.
- `test_registry_atomic_write_does_not_corrupt_on_failure` — patching `Path.write_text` to raise once leaves the original file untouched (verifies the temp-file + `Path.replace` pattern).
- `test_registry_default_providers_have_https_base_urls` — every pre-populated entry's `base_url` starts with `https://` (the `ProviderConfig` validator accepts them all).
- `test_registry_default_provider_anthropic_targets_official_endpoint` — the `anthropic` entry's `base_url == "https://api.anthropic.com"`.
- `test_registry_was_seeded_true_on_first_run` — instantiating `ProviderRegistry(tmp_path / "providers.json")` on a fresh directory sets `registry.was_seeded is True`. The composition root prints the one-line message exactly when this is True (verified by the `test_composition_root_prints_seed_message_path` test below).
- `test_registry_was_seeded_false_on_second_run` — instantiating `ProviderRegistry(...)` a second time on the same path (the file now exists) sets `registry.was_seeded is False`. The composition root must **not** print the one-liner again.

### `tests/infrastructure/llm/test_openai_client.py`

Uses `pytest-mock` (`mocker`) to patch `openai.OpenAI`.

- `test_complete_returns_text` — given a stub `chat.completions.create(...)` returning a `Choice(message=Message(content="hi"))`, `OpenAILLMClient(...).complete([UserMessage("yo")], model="m")` returns `"hi"`.
- `test_complete_passes_messages_and_model` — captured kwargs include `model="m"` and `messages=[{"role": "user", "content": "yo"}]` (after the adapter's `_messages_to_openai` translation).
- `test_complete_passes_base_url` — captured `openai.OpenAI(...)` constructor args include `base_url="https://x"`.
- `test_complete_wraps_vendor_error` — stub raising `openai.OpenAIError("boom")` causes the adapter to raise `LLMError("OpenAI error: boom")` (the vendor type does not leak).
- `test_complete_with_tools_returns_assistant_turn` — stub returning one `Message(content="ok", tool_calls=[ToolCall(id="1", function=Function(name="read", arguments='{"path":"x"}'))])` causes the adapter to return `AssistantTurn(content="ok", tool_calls=[ToolCall(id="1", name="read", arguments={"path": "x"})])`.
- `test_complete_with_tools_parses_arguments_json_string` — `arguments='{"a":1}'` is parsed into `{"a": 1}`.
- `test_complete_with_tools_keeps_arguments_when_dict` — `arguments={"key": "value"}` is kept verbatim.
- `test_complete_with_tools_handles_empty_arguments` — `arguments=""` or `arguments="{}"` becomes `{}`.
- `test_complete_with_tools_empty_tool_calls` — `tool_calls=None` (or `tool_calls=[]`) on the stub produces `AssistantTurn(content="...", tool_calls=[])`.
- `test_adapter_holds_one_client_instance` — patching `openai.OpenAI`, after one adapter construction `call_count == 1`.

### `tests/infrastructure/llm/test_anthropic_client.py`

Renamed from `test_anthropic_compat_adapter.py`. The class is `AnthropicLLMClient` (was `AnthropicCompatLLMClient`); the import path changes from `simple_cli_coder_with_rag.infrastructure.llm.anthropic_compat` to `simple_cli_coder_with_rag.infrastructure.llm.anthropic_client`. **Every existing assertion in the old test file passes unchanged against the new module path.** Add one new test:

- `test_complete_against_anthropic_com_endpoint` — captured `anthropic.Anthropic(...)` constructor args include `base_url="https://api.anthropic.com"` when the adapter is built with that URL (mirrors the DO-10 `test_adapter_uses_provider_base_url` but for the real Anthropic endpoint).

### `tests/infrastructure/llm/test_build_llm_client.py`

- `test_build_llm_client_returns_openai_for_openai_adapter` — `build_llm_client(ProviderConfig(adapter="openai", base_url="https://x", default_model="m"))` returns an `OpenAILLMClient`.
- `test_build_llm_client_returns_anthropic_for_anthropic_adapter` — same with `adapter="anthropic"` returning `AnthropicLLMClient`.
- `test_build_llm_client_unknown_adapter_raises` — `build_llm_client(ProviderConfig(adapter="bogus", ...))` raises `ValueError`.

### `tests/presentation/commands/test_connect.py`

Uses `mocker` to patch the SDK clients + `getpass.getpass`. No real LLM calls.

- `test_connect_existing_provider_writes_back_after_validating_key` — `/connect openai` with `getpass` returning `"sk-test"` and a stub OpenAI client returning a non-empty reply causes `registry.get("openai").api_key.get_secret_value() == "sk-test"`. The command's `message` contains `"connected openai (adapter=openai, model=gpt-4o-mini)"` and **does not** contain `"no validation"`.
- `test_connect_existing_provider_does_not_write_back_on_validation_failure` — same input but the stub raises `LLMError("nope")`; the registry's `api_key` stays empty and the command's `message` contains `"validation failed"`.
- `test_connect_existing_provider_no_validate_skips_round_trip` — `/connect openai --no-validate` with `getpass` returning `"sk-test"` and a **stub SDK that raises** if `complete(...)` is called. The key is still written (`registry.get("openai").api_key.get_secret_value() == "sk-test"`) and the stub's `complete` is **not** called (call count == 0). The command's `message` contains the literal `"no validation"` so the user knows the round-trip was skipped.
- `test_connect_existing_provider_no_validate_writes_bad_key` — `/connect openai --no-validate` with a stubbed key validation that would normally fail. The flag overrides validation, so the (bogus) key is still written. This pins the escape-hatch contract: `--no-validate` is a *deliberate* skip, not a "be lenient about failures".
- `test_connect_new_provider_creates_entry` — `/connect --new myproxy --adapter openai --base-url https://x.example/v1 --model my-model` with a passing key validation creates a sixth entry in the registry.
- `test_connect_new_provider_rejects_http_base_url` — `/connect --new myproxy --adapter openai --base-url http://x.example/v1 --model m` returns `CommandResult` with a message containing `"https://"` (the validator rejects; no entry is written).
- `test_connect_new_provider_rejects_unknown_adapter` — `--adapter cohere` returns a message containing `"unknown adapter"`; no entry written.
- `test_connect_unknown_id_returns_friendly_message` — `/connect nope` returns `CommandResult(message="unknown provider 'nope'. Run /providers to see what's available.", action="continue")`.
- `test_connect_does_not_echo_key` — `connect.execute(...)` does not contain the literal API key in its return value (defensive; the registry uses SecretStr but the command must not print the key).

### `tests/presentation/commands/test_providers.py`

- `test_providers_prints_table` — `/providers` on a registry with three entries returns a `message` containing the three ids, the three adapter kinds, the three base URLs, and a `key set?` column. The table must always be sorted.
- `test_providers_shows_active_id` — when `active_provider_id == "openai"`, the message contains `active: openai`.
- `test_providers_shows_none_when_no_active` — when `active_provider_id == ""`, the message contains `active: none`.
- `test_providers_marks_key_status` — an entry with `api_key=SecretStr("k")` is marked `yes`; an empty key is marked `no`.

### `tests/presentation/commands/test_provider.py`

- `test_provider_switch_updates_registry_and_app_state` — `/provider openai` on a fresh registry with `active_provider_id=""` causes `registry.active_provider_id == "openai"` and `app_state.llm` is an instance of the adapter the registry maps to.
- `test_provider_switch_unknown_id_returns_friendly_message` — `/provider nope` returns a `CommandResult` with `"unknown provider"`.
- `test_provider_switch_with_unconfigured_key_warns_and_activates` — `/provider myproxy` (whose `api_key` is empty) returns a `CommandResult` whose `message` contains `"warning"` and `"myproxy"`. The registry is updated and `app_state.llm` is rebuilt (so the next chat turn attempts the call and surfaces the `LLMError` gracefully).
- `test_provider_switch_rebuilds_knowledge_service_llm` — after `/provider openai`, calling `app_state.knowledge.chat("...", history=[], recalled=[])` routes through the new `OpenAILLMClient` (verified by `mocker` patching the SDK constructor and checking the call count).

### `tests/presentation/commands/test_provider_switch_chat_path.py`

End-to-end on the REPL level (mirrors `tests/presentation/test_repl_chat_path.py`):

- `test_repl_chat_after_provider_switch_uses_new_adapter` — start REPL with `active_provider_id="anthropic"` and a stubbed `AnthropicLLMClient`; type `/provider openai`; type a chat line; assert the stubbed `OpenAILLMClient.complete` was called (the Anthropic stub was **not**).
- `test_repl_chat_without_active_provider_returns_friendly_message` — start REPL with `active_provider_id=""`; type a chat line; assert the REPL output contains `"No active provider"` and does not raise.
- `test_composition_root_prints_seed_message_on_first_run` — run `main([])` with `LocalPaths.data_dir()` pointing to a fresh `tmp_path`. Capture stdout. Assert the captured output contains the literal `"wrote "` and `"/providers.json"` and `"5 pre-populated providers"` and `"/connect <id> to add one"`. The path is the absolute `tmp_path.joinpath("providers.json")`.
- `test_composition_root_does_not_print_seed_message_on_second_run` — after the test above, run `main([])` again. Capture stdout. Assert the captured output **does not** contain `"5 pre-populated providers"` (the file already exists; `was_seeded is False`).
- `test_composition_root_seed_message_is_exactly_one_line` — capture the first-run output and assert the line is a single string ending with a newline (no multi-line scaffold of paths/configs).

### `tests/application/test_knowledge_service_set_llm.py`

- `test_knowledge_service_set_llm_swaps_adapter` — building a `KnowledgeService` with one `LLMClient`, calling `set_llm(other)`, then calling `chat("...", history=[], recalled=[])` results in `other.complete_with_tools(...)` being called (the original adapter was **not**).
- `test_knowledge_service_set_llm_preserves_other_dependencies` — after `set_llm`, `chunker`, `embedder`, `vector_store`, `coordinator`, `editor` are unchanged.

## Why these tests

- `test_provider_config_*` and `test_providers_file_*` pin the secrets-handling contract (SecretStr masking, no literal keys in the dumped JSON, no extra keys).
- `test_provider_registry_*` pins the file-level contract: first-run seeding, atomic writes, CRUD, `set_active` persistence, the temp-file + `Path.replace` pattern.
- `test_openai_client_*` pins the official-SDK contract for the new adapter; the `test_anthropic_client_*` rename pins the rename + new official-adapter endpoint.
- `test_build_llm_client_*` pins the dispatch from `AdapterKind` to the right adapter class — the single point where the registry's adapter field meets the LLM layer.
- `test_connect_*`, `test_providers_*`, `test_provider_*`, `test_provider_switch_chat_path_*` pin the user-facing Commands and the live provider-switching path.
- `test_knowledge_service_set_llm_*` pins the facade's `set_llm` method (or, if `set_llm` is rejected at design review, the equivalent field used by the composition root).