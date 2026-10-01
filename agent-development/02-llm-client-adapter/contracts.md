# DO-02 contracts

## Architectural

- [ ] `LLMClient`, `Message`, and related types live in `domain/`.
- [ ] The LLM adapter(s) live in `infrastructure/llm/` (a subpackage under `infrastructure`). One file per provider, OR one shared file if the Anthropic-SDK-with-`base_url` strategy covers all three (as decided by the `provider-research` block in the commit body).
- [ ] `Settings` lives in `infrastructure/`.
- [ ] `import-linter` reports zero violations.
- [ ] No file outside `infrastructure/llm/` imports a vendor SDK (the `anthropic` SDK, any provider-specific SDK, or raw `httpx` for a non-Anthropic-compatible provider).
- [ ] No file in `domain/`, `application/`, or `presentation/` imports from `infrastructure.settings` — settings are read once in the composition root and passed down as plain values or a typed `Settings` instance injected at construction time.

## Behavioral

- [ ] `Settings()` reads `NVIDIA_API_KEY`, `MISTRAL_API_KEY`, `MINIMAX_API_KEY` from `.env` when present.
- [ ] `Settings()` raises `RuntimeError` (not `ValidationError`) if the API key for `default_provider` is empty or missing at startup. The other two keys may be empty without raising (a user might only use one provider).
- [ ] `Settings.__repr__` / `str(settings)` mask all three API keys: the literal string of any key never appears.
- [ ] Logging the settings (file-only sink from DO-01) does not contain any API key.
- [ ] The active adapter's `complete(messages, model=...)` returns the text from the (mocked) backend call.
- [ ] When the backend raises an SDK / HTTP error, the adapter re-raises it wrapped in `LLMError` (defined in `domain/llm_client.py`). The vendor type does not leak past the adapter.
- [ ] The adapter is constructed **once** per provider instance.

## Schema

- [ ] `class Message(BaseModel)` with `role: Literal["user", "assistant", "system"]`, `content: str`. (DO-10 extends the union with a `"tool"` role.)
- [ ] `UserMessage`, `AssistantMessage`, `SystemMessage` as frozen leaf models.
- [ ] `class ToolSpec(BaseModel)`: `name: str`, `description: str`, `input_schema: dict[str, Any]`.
- [ ] `class ToolCall(BaseModel)`: `id: str`, `name: str`, `arguments: dict[str, Any]`.
- [ ] `class AssistantTurn(BaseModel)`: `content: str`, `tool_calls: list[ToolCall] = Field(default_factory=list)`.
- [ ] `class LLMClient(Protocol)`:
  - `complete(self, messages: list[Message], *, model: str) -> str`
  - `complete_with_tools(self, messages: list[Message], *, model: str, tools: list[ToolSpec]) -> AssistantTurn`
- [ ] `class LLMError(Exception)` in `domain/llm_client.py`.
- [ ] `class Settings(BaseSettings)`:
  - `nvidia_api_key: SecretStr`
  - `mistral_api_key: SecretStr`
  - `minimax_api_key: SecretStr`
  - `default_provider: Literal["nvidia", "mistral", "minimax"] = "nvidia"`
  - `nvidia_model: str`
  - `mistral_model: str`
  - `minimax_model: str`
  - Optional per-provider `*_base_url: str | None = None` (present if the research shows a non-default `base_url` is needed; `None` means "use the SDK's default").
  - `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")`.
- [ ] Adapter class(es) in `infrastructure/llm/`:
  - `__init__(self, settings: Settings) -> None`
  - `complete(self, messages: list[Message], *, model: str) -> str`
  - `complete_with_tools(self, messages: list[Message], *, model: str, tools: list[ToolSpec]) -> AssistantTurn` (stub returning empty `tool_calls` is acceptable in this deliverable; DO-10 fills it in).