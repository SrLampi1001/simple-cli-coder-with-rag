# DO-11 — Provider registry, real OpenAI SDK, real Anthropic SDK

## Goal

Replace the current single-provider `.env`-based configuration with a JSON-based provider registry that uses the **official** OpenAI Python SDK and the **official** Anthropic Python SDK behind the existing `LLMClient` Protocol. The conversation logic (chat loop, `Learn`, `recall`, tool use, `/learn`, file editing) does not change — switching the provider is a matter of selecting a different adapter in the registry.

This satisfies acceptance-criterion TL-2 (*"the same chat flow works with OpenAI and Anthropic without changing the core conversation logic"*) by making the chat loop provider-agnostic and by integrating both SDKs. It also satisfies TL-2 *"the active provider must be selectable through configuration or a terminal command"* by adding `/provider <id>` and a registry-driven JSON config.

The five supported providers (nvidia, mistral, minimax, anthropic, openai) are pre-populated in a local-user JSON file with `base_url` + `default_model` filled in and the `api_key` empty; the user fills the key with `/connect <id>` (OpenCode UX). Custom providers are added with `/connect --new <id> --adapter <a> --base-url <u> --model <m>`.

The current `OpenAICompatLLMClient` (stdlib `urllib`-based) is **removed** — the official `openai` SDK with `base_url` covers every OpenAI-compat endpoint (nvidia, mistral, openai, plus custom entries).

## Source of truth

- `OBJECTIVES.md` — Adapter pattern ("allows more APIs providers with OpenAI compatibility later"), Strategy pattern.
- `docs/development-tools.md` §6 (LLM SDKs: `anthropic`, future `openai`), §8 (pydantic, pydantic-settings).
- `NEW_REQUIREMENTS.md` §2 *Multi-provider AI integration* (OpenAI SDK + Anthropic SDK, shared interface, env-var credentials).
- DO-02 contracts (`LLMClient`, `LLMError`, `Message`, `Settings`).
- DO-10 contracts (`complete_with_tools` must keep working with both new adapters).

## Acceptance criteria

- [ ] `pyproject.toml` adds `"openai>=1.0,<2"` to `dependencies`.
- [ ] `src/simple_cli_coder_with_rag/infrastructure/providers/` (new subpackage) contains:
  - `__init__.py` re-exporting `ProviderRegistry`, `ProviderConfig`, `ProvidersFile`, `AdapterKind`.
  - `models.py` — Pydantic models:
    - `AdapterKind = Literal["openai", "anthropic"]`.
    - `class ProviderConfig(BaseModel)` with `adapter: AdapterKind`, `base_url: str`, `default_model: str`, `context_window: int = Field(ge=1024)`, `api_key: SecretStr = SecretStr("")`. The `model_config = ConfigDict(extra="forbid")` rejects typos in keys. `context_window` is the model's **input-token** budget and is consumed by DO-12's `SessionManager` for auto-compaction (DO-12 contracts §Schema).
    - `class ProvidersFile(BaseModel)` with `active_provider_id: str = ""` and `providers: dict[str, ProviderConfig] = Field(default_factory=dict)`.
  - `registry.py` — `class ProviderRegistry` with:
    - `__init__(self, path: Path) -> None`. Reads `path`; if the file does not exist, writes the five pre-populated entries (nvidia / mistral / minimax / anthropic / openai) and returns. Atomic write (`write_text` to a temp file then `Path.replace`). The constructor exposes whether the file was just created via `self.was_seeded: bool` so the composition root can print a one-line `wrote <absolute path> with 5 pre-populated providers (keys empty; use /connect <id> to add one)` exactly on the first run, never on subsequent runs.
    - `def get(self, provider_id: str) -> ProviderConfig` — raises `UnknownProviderError` on miss.
    - `def list(self) -> list[tuple[str, ProviderConfig]]` — sorted by id for deterministic `/providers` output.
    - `def active(self) -> ProviderConfig` — returns the config for `active_provider_id`; raises `NoActiveProviderError` when empty.
    - `def set_active(self, provider_id: str) -> None` — sets and persists.
    - `def upsert(self, provider_id: str, config: ProviderConfig) -> None` — writes a single entry back to the file atomically.
    - `def remove(self, provider_id: str) -> None` — removes an entry; idempotent.
- [ ] `src/simple_cli_coder_with_rag/infrastructure/providers/default_providers.py` (or constant in `registry.py`) defines the pre-populated providers:

| id          | adapter     | base_url                                | default_model                  | context_window |
|-------------|-------------|-----------------------------------------|--------------------------------|----------------|
| `nvidia`    | `openai`    | `https://integrate.api.nvidia.com/v1`   | `openai/gpt-oss-20b`           | 128000         |
| `mistral`   | `openai`    | `https://api.mistral.ai/v1`            | `pythonista-latest` (or current `mistral-code-latest`) | 128000 |
| `minimax`   | `anthropic` | `https://api.minimax.io/anthropic`     | `MiniMax-M3`                   | 128000         |
| `anthropic` | `anthropic` | `https://api.anthropic.com`            | `claude-3-5-sonnet-latest`     | 200000         |
| `openai`    | `openai`    | `https://api.openai.com/v1`            | `gpt-4o-mini`                  | 128000         |

  The exact default models are confirmed by the web-search step in `workflow.md` step 2 and recorded in the commit body in a `provider-research:` block (same shape as DO-02).

- [ ] `src/simple_cli_coder_with_rag/infrastructure/llm/openai_client.py` (new) defines `class OpenAILLMClient` using the official `openai` SDK:
  - `__init__(self, *, api_key: str, base_url: str, default_model: str) -> None` — `self._client = openai.OpenAI(api_key=..., base_url=...)`. One persistent client instance per adapter (DO-02 contract).
  - `complete(self, messages, *, model: str) -> str` — calls `client.chat.completions.create(model=..., messages=[...])`; returns `choice.message.content`. Wraps SDK exceptions in `LLMError`.
  - `complete_with_tools(self, messages, *, model: str, tools: list[ToolSpec]) -> AssistantTurn` — calls with `tools=[{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}]`; parses `tool_calls[].function.arguments` as JSON into `dict[str, Any]`. Mirrors the wire-format rules already in `openai_compat.py` (now deleted) but uses the SDK instead of raw HTTP.
- [ ] `src/simple_cli_coder_with_rag/infrastructure/llm/anthropic_client.py` (renamed from `anthropic_compat.py`) defines `class AnthropicLLMClient`:
  - The class body is byte-identical to today's `AnthropicCompatLLMClient` minus the docstring's MiniMax-specific framing. The docstring notes that the adapter targets the official Anthropic Messages API and works with any Anthropic-compatible endpoint via `base_url` (e.g., minimax). The module is renamed to make the "this is the official Anthropic SDK" intent obvious.
  - `__init__` accepts `api_key`, `base_url`, `default_model`. Default `base_url` for the `anthropic` entry is `https://api.anthropic.com` (per the registry table above); for `minimax` the `base_url` in the registry overrides.
- [ ] `src/simple_cli_coder_with_rag/infrastructure/llm/openai_compat.py` is **deleted** (urllib adapter removed — covered by the official `openai` SDK now).
- [ ] `src/simple_cli_coder_with_rag/infrastructure/llm/__init__.py` exposes:
  - `def build_llm_client(config: ProviderConfig) -> LLMClient` — picks the adapter class based on `config.adapter`:
    ```python
    if config.adapter == "openai":
        return OpenAILLMClient(api_key=config.api_key.get_secret_value(), base_url=config.base_url, default_model=config.default_model)
    if config.adapter == "anthropic":
        return AnthropicLLMClient(api_key=..., base_url=..., default_model=...)
    raise ValueError(f"unknown adapter kind: {config.adapter!r}")
    ```
- [ ] The composition root in `src/simple_cli_coder_with_rag/cli.py` is updated:
  - Constructs `ProviderRegistry(LocalPaths.data_dir() / "providers.json")`.
  - If `registry.active_provider_id == ""`, the REPL starts anyway but each chat turn says *"No provider selected. Run `/providers` to list and `/provider <id>` to activate one."* and `/connect <id>` to add an API key.* (the previous "abort on missing key" behaviour is replaced with this graceful path so the user can run `/connect` to add a key before activating).
  - When `active_provider_id != ""`, builds the `LLMClient` via `build_llm_client(registry.active())` and wires it into `AppState.llm` exactly as DO-02 does today.
  - The Settings class loses the three `*_api_key` / `*_model` / `*_base_url` fields and the `default_provider` field. It keeps the non-provider config (`embedding_model`, `vector_store`, `retrieval_*`, `editor_*`, etc.) — those still load from `.env` via pydantic-settings.
- [ ] `src/simple_cli_coder_with_rag/presentation/commands/connect.py` defines `class ConnectCommand`:
  - `/connect <id>` — if `<id>` is one of the five pre-populated providers, prompt the user for the API key (using `getpass.getpass` so the key is not echoed). Validate by calling `LLMClient.complete(messages=[SystemMessage(content="ping"), UserMessage(content="ping")], model=<default_model>)` and checking the response is non-empty; on failure print *"API key validation failed: <reason>"* and do not write back. On success, call `registry.upsert(id, config.model_copy(update={"api_key": SecretStr(key)}))`.
  - `/connect <id> --no-validate` — same prompt-for-key, but the validation round-trip is skipped (the key is written without a test ping). The flag exists for slow networks / known-good keys where the round-trip would feel unresponsive. The printed confirmation includes the literal `"no validation"` so the user knows the round-trip was skipped.
  - `/connect --new <id> --adapter <openai|anthropic> --base-url <url> --model <model>` — same prompt-for-key + validate + write back, on a new entry. Custom URLs are accepted as long as they start with `https://` and the model string is non-empty. `--no-validate` is accepted in this form too.
  - All inputs are validated; recoverable errors (network failure, bad key) do not crash the REPL — they print a one-line message and the loop continues.
- [ ] `src/simple_cli_coder_with_rag/presentation/commands/providers.py` defines `class ProvidersCommand`:
  - `/providers` — print a table: `<id>  <adapter>  <base_url>  <default_model>  <key set?>` for every entry in `registry.list()`, plus a line `active: <id>` (or `active: none`).
- [ ] `src/simple_cli_coder_with_rag/presentation/commands/provider.py` defines `class ProviderCommand`:
  - `/provider <id>` — call `registry.set_active(id)`, build the new `LLMClient` via `build_llm_client`, swap it into `AppState.llm` and `AppState.knowledge.llm`. Print *"active provider: <id>"*. If the provider's `api_key` is empty, print *"warning: <id> has no API key yet. Run `/connect <id>` to add one."* and still activate.
- [ ] All four slash commands are registered in `cli._build_registry()`.
- [ ] `docs/providers.md` (new) documents the five supported providers (id, adapter, base URL, default model, where to get a key, link to provider's API-key page).
- [ ] `README.md` is updated:
  - The "Initialization" section no longer says `cp .env.example .env` for provider keys; it says `uv run coder`, then `/providers`, then `/connect <id>` for each provider the user wants to enable.
  - The "Slash commands" table gains `/connect`, `/providers`, `/provider <id>` rows.
  - A new section "Supported providers" links to `docs/providers.md`.
  - `.env.example` is referenced only for the non-provider knobs (chunking, vector store, etc.).
- [ ] `.env.example` is updated: the three `*_API_KEY` / `*_MODEL` / `*_BASE_URL` / `DEFAULT_PROVIDER` entries are removed; a single comment line remains: `# Provider credentials are configured via the /connect command and stored in ~/.local/share/simple-cli-coder-with-rag/providers.json (gitignored). See docs/providers.md.`
- [ ] `.gitignore` adds `providers.json` and `**/providers.json` so the file is never sent even if a user accidentally drops one into the repo root.
- [ ] No file outside `infrastructure/llm/` and `infrastructure/providers/` imports `openai`, `anthropic`, or reads `providers.json` directly. The `import-linter` contract list gains:
  - `forbidden_imports`: `"openai"` from `simple_cli_coder_with_rag.{application,domain,presentation}`. (`anthropic` is already covered by the existing DO-02 contract scope; the new contract adds `openai`.)
- [ ] The full gate exits 0.

## Gate

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run lint-imports
uv run pytest -q
pre-commit run --all-files
```

## Out of scope

- Persisting conversation history across sessions (DO-12 will tackle that — `/memory`, `/chats`, `/resume`, 10-message window).
- Document ingestion RAG (DO-13).
- `coding-assistance/` trace (DO-14).
- Custom skills (DO-15).
- Deployed vector store / Supabase (DO-16).
- `/connect --delete <id>` (a future enhancement — `/provider <other>` covers the immediate TL criterion).

## Depends on

- DO-02 (`LLMClient` Protocol, `LLMError`, `Message`).
- DO-09 (recall path must keep working when the active provider changes — `KnowledgeService` already wires the LLM through `AppState.llm`).
- DO-10 (`complete_with_tools` contract).

## Blocks

- DO-12 (saved chats + 10-msg window — `/chats` reads from `LocalPaths`, but the REPL now boots even without a configured provider; the saved-chats layer does not depend on the provider).
- DO-13 (document RAG — the RAG flow uses the embedder, not the LLM).
- TL acceptance criterion #2 directly depends on this deliverable.