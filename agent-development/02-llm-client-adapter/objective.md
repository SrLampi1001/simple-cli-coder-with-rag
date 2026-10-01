# DO-02 — LLM client adapter

## Goal

The Anthropic SDK is wrapped behind a project-owned `LLMClient` Protocol so the application layer never imports a vendor type. Settings (API key, model names) are loaded from `.env` via `pydantic-settings`. Empty `ANTHROPIC_API_KEY` is a hard startup error.

## Source of truth

- `README.md` — Adapter pattern.
- `docs/development-tools.md` §6 (LLM), §8 (pydantic, pydantic-settings).

## Acceptance criteria

- [ ] `src/simple_cli_coder_with_rag/domain/llm_client.py` defines:
  ```python
  class LLMClient(Protocol):
      def complete(self, messages: list[Message], *, model: str) -> str: ...
      def complete_with_tools(self, messages: list[Message], *, model: str, tools: list[ToolSpec]) -> AssistantTurn: ...  # noqa  (used in DO-10)
  ```
- [ ] `src/simple_cli_coder_with_rag/domain/messages.py` defines `Message`, `UserMessage`, `AssistantMessage`, `SystemMessage`, `AssistantTurn`, `ToolSpec`, `ToolCall`. Pydantic v2 models. `Message` is a discriminated union via `role: Literal["user","assistant","system"]`.
- [ ] `src/simple_cli_coder_with_rag/infrastructure/llm/anthropic_client.py` defines `class AnthropicLLMClient` implementing `LLMClient`. Wraps `anthropic.Anthropic`.
- [ ] `src/simple_cli_coder_with_rag/infrastructure/settings.py` defines `class Settings(BaseSettings)`:
  - `anthropic_api_key: SecretStr`
  - `chat_model: str = "claude-sonnet-4-5"`
  - `compactor_model: str = "claude-haiku-4-5"`
  - `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")`
  - `def model_post_init(self, _):` validates `anthropic_api_key` is non-empty; raises `RuntimeError` otherwise.
- [ ] The composition root in `cli.py` (DO-01) is updated to instantiate `Settings`, build `AnthropicLLMClient`, and stash the client on `AppState` (which now has an `llm: LLMClient` field).
- [ ] No module under `domain/`, `application/`, or `presentation/` imports from `anthropic`. The only place the SDK is referenced is `infrastructure/llm/anthropic_client.py`.
- [ ] `Settings.__repr__` does not print the API key (use `SecretStr`'s `__str__` mask).
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
