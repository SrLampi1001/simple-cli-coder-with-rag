# DO-11 contracts

## Architectural

- [ ] `LLMClient` (Protocol), `LLMError`, and `Message` types live in `domain/` and are unchanged from DO-02 / DO-10. The chat loop, `KnowledgeService`, the REPL, the compactor, and the recall path all keep using the existing `LLMClient` Protocol — this deliverable does not introduce new domain types.
- [ ] New subpackage `src/simple_cli_coder_with_rag/infrastructure/providers/` owns the JSON registry and its Pydantic models. No file outside this subpackage (and the composition root `cli.py`) imports `providers.json` directly or knows the on-disk path.
- [ ] The LLM adapters live in `src/simple_cli_coder_with_rag/infrastructure/llm/`:
  - `anthropic_client.py` (renamed from `anthropic_compat.py`) — official Anthropic SDK.
  - `openai_client.py` (new) — official `openai` SDK.
  - `openai_compat.py` (urllib) is **deleted**.
- [ ] `import-linter` adds two new contracts:
  - `forbidden_imports` for `openai` (mirror of the existing `anthropic` rule). Source modules: `application`, `domain`, `presentation`. Indirect imports through `infrastructure/llm/openai_client.py` are allowed (composition root).
  - `forbidden_modules` for `infrastructure.providers` from `domain`. The application and presentation layers may import the registry (they need to, for `/connect` and `/providers`), but the domain layer must not.
- [ ] No file in `domain/` imports from `infrastructure/` (existing contract; reinforced).
- [ ] `Settings` (pydantic-settings) loses all provider-key / provider-model / provider-base-url / default-provider fields. The composition root `cli.py` is the only place that knows how provider config is loaded.

## Behavioral

- [ ] On first run, `ProviderRegistry(LocalPaths.data_dir() / "providers.json")` writes the five pre-populated providers (`nvidia`, `mistral`, `minimax`, `anthropic`, `openai`) with empty `api_key` and `active_provider_id = ""`. The file is created atomically (write to `<path>.tmp` then `Path.replace`). After construction, `registry.was_seeded is True` exactly when the file did not exist beforehand; on every subsequent run `was_seeded is False`. The composition root reads `registry.was_seeded` and, when `True`, prints a single one-liner to stdout: `wrote <absolute path> with 5 pre-populated providers (keys empty; use /connect <id> to add one)`. The line is printed **only** on first run — never on subsequent boots.
- [ ] `ProvidersFile.model_dump_json()` never contains a literal API key — `SecretStr` round-trips through `**********` (pydantic default). A unit test asserts that no API key literal appears in the dumped JSON.
- [ ] `provider.registry.get(id)` raises `UnknownProviderError` for unknown ids.
- [ ] `provider.registry.active()` raises `NoActiveProviderError` when `active_provider_id` is empty.
- [ ] `provider.registry.set_active(id)` raises `UnknownProviderError` for unknown ids; otherwise writes the file atomically and returns.
- [ ] `provider.registry.upsert(id, config)` merges a single provider entry back into the file atomically (read all → replace one entry → write all). On an unknown id, the entry is created.
- [ ] `/connect <id>`:
  - Looks up the pre-populated `ProviderConfig` for `<id>`; raises `UnknownProviderError` (printed as *"unknown provider <id>. Run `/providers` to see what's available."*) if not found.
  - Prompts for the key with `getpass.getpass("API key for <id>: ")`.
  - **Validation (default):** builds a transient `LLMClient` via `build_llm_client(config)` (with the entered key), calls `complete(messages=[SystemMessage("ping"), UserMessage("ping")], model=config.default_model)` and asserts the response is non-empty. On failure: prints *"API key validation failed for <id>: <reason>"* and **does not** write back.
  - **No-validation escape hatch (`--no-validate`):** when the flag is present the round-trip above is skipped entirely. The key is written without testing. The confirmation message is the literal *"connected <id> (no validation; adapter=<a>, model=<m>)"* so the user always knows whether the round-trip happened. The flag is the only way to skip validation — there is no env-var bypass (the validation is the default for a reason: typos in keys fail silently otherwise).
  - On success (either path): calls `registry.upsert(id, config.model_copy(update={"api_key": SecretStr(key)}))` and prints the matching confirmation message (`"connected <id> (adapter=<a>, model=<m>)"` or the `"no validation"` variant above).
- [ ] `/connect --new <id> --adapter <openai|anthropic> --base-url <url> --model <model>`:
  - Validates `<url>` starts with `https://` and `<model>` is non-empty (rejects with a readable message; does not crash).
  - Creates a new `ProviderConfig(adapter=..., base_url=..., default_model=..., api_key=SecretStr(""))`, then prompts for the key and validates as above.
- [ ] `/providers` prints a sorted table of every entry with `<id>  <adapter>  <base_url>  <default_model>  <key set?>`. The `<key set?> is `yes` when `SecretStr.get_secret_value() != ""`, otherwise `no`. A trailing line shows `active: <id>` or `active: none`.
- [ ] `/provider <id>` calls `registry.set_active(id)`, rebuilds `AppState.llm` and `AppState.knowledge._llm` (via the existing `_llm` field on `KnowledgeService`; if the field is private, expose a `set_llm(...)` method on the facade), and prints `"active provider: <id>"`. If the entry's `api_key` is empty, prints an additional warning line and still activates — the next chat turn will hit `LLMError` and the REPL prints the friendly message instead of crashing.
- [ ] Switching the active provider mid-session does not require restarting the REPL. A chat turn that completed before `/provider <id>` uses the previous adapter; a chat turn after uses the new one. No state on the previous adapter is retained (stateless SDK clients).
- [ ] `OpenAILLMClient.complete` returns the text from a mocked `openai.OpenAI().chat.completions.create(...)` call. The mock verifies the SDK is constructed exactly once per adapter instance (DO-02 contract).
- [ ] `OpenAILLMClient.complete` wraps any `openai.OpenAIError` (and `httpx.HTTPError` if it ever surfaces) in `LLMError`. The vendor type does not leak past the adapter.
- [ ] `OpenAILLMClient.complete_with_tools` returns `AssistantTurn(content=<text>, tool_calls=[ToolCall(id=..., name=..., arguments={...}), ...])`. `arguments` is parsed from the JSON-string the SDK returns (or kept as-is if it is already a dict).
- [ ] `AnthropicLLMClient.complete_with_tools` (renamed from `AnthropicCompatLLMClient`) keeps the existing behaviour but is now also valid against `https://api.anthropic.com` — the `base_url` parameter comes from `ProviderConfig.base_url` and is passed verbatim to `anthropic.Anthropic(base_url=..., auth_token=...)`. The existing DO-10 tests for `complete_with_tools` pass against the renamed module with **zero** changes to the assertions.
- [ ] The composition root in `cli.py` does **not** exit with code 2 when `active_provider_id` is empty. The REPL starts; chat turns that require the LLM print a one-line *"No active provider. Run `/connect <id>` to add a key, then `/provider <id>` to activate."* message; `/connect` and `/providers` work normally.

## Schema

- [ ] `class AdapterKind = Literal["openai", "anthropic"]` in `infrastructure/providers/models.py`.
- [ ] `class ProviderConfig(BaseModel)`:
  - `adapter: AdapterKind`
  - `base_url: str` — `Field(min_length=1)` and a `field_validator` rejecting non-`https://` URLs (custom providers only; the pre-populated ones already pass).
  - `default_model: str` — `Field(min_length=1)`.
  - `context_window: int = Field(ge=1024)` — the model's **input-token** budget. Consumed by DO-12's `SessionManager.effective_budget()` (DO-12 contracts §Behavioral) to drive auto-compaction. Defaults per pre-populated provider are pinned in `default_providers.py` (`anthropic=200_000`, others `128_000`).
  - `api_key: SecretStr = SecretStr("")` — `repr(...)` and `str(...)` mask the value.
  - `model_config = ConfigDict(extra="forbid")`.
- [ ] `class ProvidersFile(BaseModel)`:
  - `active_provider_id: str = ""` — empty until `/provider <id>` is run.
  - `providers: dict[str, ProviderConfig] = Field(default_factory=dict)`.
  - `model_config = ConfigDict(extra="forbid")`.
- [ ] `class ProviderRegistry` (not a Pydantic model — it owns the file I/O):
  - `__init__(self, path: Path) -> None` — sets `self.was_seeded: bool = True` when the file did not exist beforehand, `False` otherwise. Both branches end with the same in-memory state (the file is loaded or freshly seeded).
  - `get(self, provider_id: str) -> ProviderConfig`
  - `list(self) -> list[tuple[str, ProviderConfig]]`
  - `active(self) -> ProviderConfig`
  - `set_active(self, provider_id: str) -> None`
  - `upsert(self, provider_id: str, config: ProviderConfig) -> None`
  - `remove(self, provider_id: str) -> None`
  - `path` property exposing the on-disk path (used by `/connect` to show where the file lives on first run).
  - `was_seeded: bool` — public read-only flag; the composition root prints the first-run one-liner exactly when this is `True`.
- [ ] `class UnknownProviderError(KeyError)` and `class NoActiveProviderError(Exception)` in `infrastructure/providers/errors.py`.
- [ ] `OpenAILLMClient` in `infrastructure/llm/openai_client.py`:
  - `__init__(self, *, api_key: str, base_url: str, default_model: str) -> None`
  - `complete(self, messages: list[Message], *, model: str) -> str`
  - `complete_with_tools(self, messages: list[Message], *, model: str, tools: list[ToolSpec]) -> AssistantTurn`
- [ ] `AnthropicLLMClient` (renamed from `AnthropicCompatLLMClient`) — schema unchanged from DO-10:
  - `__init__(self, *, api_key: str, base_url: str, default_model: str) -> None`
  - `complete(self, messages: list[Message], *, model: str) -> str`
  - `complete_with_tools(self, messages: list[Message], *, model: str, tools: list[ToolSpec]) -> AssistantTurn`
- [ ] `def build_llm_client(config: ProviderConfig) -> LLMClient` in `infrastructure/llm/__init__.py` — picks `OpenAILLMClient` or `AnthropicLLMClient` based on `config.adapter`.
- [ ] `ConnectCommand`, `ProvidersCommand`, `ProviderCommand` follow the DO-01 Command contract (`name`, `summary`, `execute(context: CommandContext) -> CommandResult`).
- [ ] `Settings` keeps only non-provider config (a representative list — final field set is whatever is in DO-10 today minus provider fields). Provider-specific fields removed: `nvidia_api_key`, `mistral_api_key`, `minimax_api_key`, `default_provider`, `nvidia_model`, `mistral_model`, `minimax_model`, `nvidia_base_url`, `mistral_base_url`, `minimax_base_url`, `chat_model`, `compactor_model`, `CHAT_MODEL`. The chat model is now sourced from `ProviderConfig.default_model` (or overridden per-turn via a future Command; out of scope here). The compactor model is sourced from `ProviderConfig.default_model` (single-model-per-session policy; matches the current single-`DEFAULT_PROVIDER` setup).