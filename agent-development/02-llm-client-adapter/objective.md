# DO-02 — LLM client adapter

## Goal

The three LLM providers used by this project — **NVIDIA**, **Mistral**, and **MiniMax** (minimax.io) — are wrapped behind a project-owned `LLMClient` Protocol so the application layer never imports a vendor type. Whether each provider is reached via the `anthropic` Python SDK (pointed at the provider's `base_url`) or via a provider-specific SDK / `httpx` client is **not known up front** — it is determined by the web-search step at the start of this deliverable (`workflow.md`). The chosen adapter strategy, the per-provider `base_url`s, the model IDs, and any reference implementations are all recorded there too. Settings (three API keys, a default provider, per-provider model + optional `base_url`) load from `.env` via `pydantic-settings`. An empty API key for the active provider is a hard startup error.

## Source of truth

- `OBJECTIVES.md` — Adapter pattern.
- `docs/development-tools.md` §6 (LLM), §8 (pydantic, pydantic-settings).
- The web-search findings recorded in this deliverable's commit body (which providers expose an Anthropic-compatible endpoint, their `base_url`s and auth headers, and a reference implementation per provider).

## Acceptance criteria

- [ ] A documented web-search has confirmed, for each of NVIDIA / Mistral / MiniMax: whether the provider exposes an **Anthropic-compatible** endpoint that the `anthropic` Python SDK can talk to (i.e. a `base_url` + headers + request/response shape compatible with `anthropic.Anthropic`), the auth header / model ID(s), and a reference implementation / example URL. The findings are summarised in the commit body in the `provider-research:` block defined in `workflow.md`.
- [ ] Based on the research, the adapter strategy is one of:
  - **Single Anthropic-SDK adapter** with per-provider `base_url` + `api_key` — used when all three (or a chosen subset) are Anthropic-compatible. The composition root picks the active provider.
  - **Per-provider adapters** under `infrastructure/llm/` — used when one or more providers need their own SDK or a raw `httpx` client.
  - A **mix** — one shared Anthropic-SDK adapter for the compatible providers, one or more provider-specific adapters for the rest. The plan documents which providers fall into which bucket.
- [ ] `src/simple_cli_coder_with_rag/domain/llm_client.py` defines `class LLMClient(Protocol)` with `complete` and `complete_with_tools` (the latter is a stub until DO-10), and `class LLMError(Exception)`.
- [ ] `src/simple_cli_coder_with_rag/domain/messages.py` defines `Message`, `UserMessage`, `AssistantMessage`, `SystemMessage`, `AssistantTurn`, `ToolSpec`, `ToolCall` (Pydantic v2 models; `Message` is a discriminated union via `role: Literal["user","assistant","system"]`).
- [ ] The adapter implementation(s) live in `src/simple_cli_coder_with_rag/infrastructure/llm/`. The only modules that import a vendor SDK (`anthropic`, an NVIDIA SDK, a Mistral SDK, or raw `httpx` for a non-Anthropic-compatible provider) are inside `infrastructure/llm/`.
- [ ] `src/simple_cli_coder_with_rag/infrastructure/settings.py` defines `class Settings(BaseSettings)`:
  - `nvidia_api_key: SecretStr`
  - `mistral_api_key: SecretStr`
  - `minimax_api_key: SecretStr`
  - `default_provider: Literal["nvidia", "mistral", "minimax"] = "nvidia"`
  - `nvidia_model: str` and `nvidia_base_url: str | None = None`
  - `mistral_model: str` and `mistral_base_url: str | None = None`
  - `minimax_model: str` and `minimax_base_url: str | None = None`
  - `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")`
  - `model_post_init` validates that **the API key for `default_provider`** is non-empty; raises `RuntimeError` otherwise.
- [ ] The composition root in `cli.py` (DO-01) is updated to instantiate `Settings()`, build the appropriate adapter for `default_provider` (or all three and select by `default_provider`), and stash the active client on `AppState` (which gains an `llm: LLMClient` field).
- [ ] No module under `domain/`, `application/`, or `presentation/` imports a vendor SDK. The architectural contract is the same as before; only the set of vendor SDKs has broadened to `anthropic` + any provider-specific SDK the research uncovers.
- [ ] `Settings.__repr__` / `__str__` mask all three API keys.
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

- Wiring the LLM into the REPL chat (DO-03).
- Prompt construction / system prompts (DO-03).
- Tool use (DO-10 uses `complete_with_tools`, but the integration is in DO-10).

## Depends on

- DO-00, DO-01.

## Blocks

- DO-03, DO-04 (compactor uses the LLM), DO-09, DO-10.