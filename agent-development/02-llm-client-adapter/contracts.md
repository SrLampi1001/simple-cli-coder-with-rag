# DO-02 contracts

## Architectural

- [ ] `LLMClient`, `Message`, and related types live in `domain/`.
- [ ] `AnthropicLLMClient` lives in `infrastructure/llm/` (a new subpackage under `infrastructure`).
- [ ] `Settings` lives in `infrastructure/`.
- [ ] `import-linter` reports zero violations.
- [ ] No file outside `infrastructure/llm/` imports from `anthropic`.
- [ ] No file in `domain/`, `application/`, or `presentation/` imports from `infrastructure.settings` — settings are read once in the composition root and passed down as plain values or a typed `Settings` instance injected at construction time.

## Behavioral

- [ ] `Settings()` reads `ANTHROPIC_API_KEY` from `.env` when present.
- [ ] `Settings()` raises `RuntimeError` (not `ValidationError`) if `ANTHROPIC_API_KEY` is empty or missing at startup.
- [ ] `Settings.__repr__` masks the API key: the literal string of the key never appears in `repr(settings)` or `str(settings)`.
- [ ] `Settings.logger.info(settings)` (via the file-only sink from DO-01) does not contain the API key. Test by capturing `logger.add` sink calls.
- [ ] `AnthropicLLMClient.complete(messages, model="claude-sonnet-4-5")` returns the string from the mocked SDK call.
- [ ] When the SDK raises `anthropic.APIError`, `AnthropicLLMClient` re-raises it wrapped in a project-owned `LLMError` (defined in `domain/llm_client.py`). The vendor type does not leak past the adapter.
- [ ] `AnthropicLLMClient.__init__` builds an `anthropic.Anthropic` client with the API key from `Settings`. The SDK is created **once** per `AnthropicLLMClient` instance.

## Schema

- [ ] `class Message(BaseModel)`:
  - `role: Literal["user", "assistant", "system"]`
  - `content: str`
- [ ] `class UserMessage(Message)` with `role: Literal["user"] = "user"` (frozen model_config).
- [ ] `class AssistantMessage(Message)` with `role: Literal["assistant"] = "assistant"`.
- [ ] `class SystemMessage(Message)` with `role: Literal["system"] = "system"`.
- [ ] `class ToolSpec(BaseModel)`:
  - `name: str`
  - `description: str`
  - `input_schema: dict[str, Any]` (JSON Schema)
- [ ] `class ToolCall(BaseModel)`:
  - `id: str`
  - `name: str`
  - `arguments: dict[str, Any]`
- [ ] `class AssistantTurn(BaseModel)`:
  - `content: str`
  - `tool_calls: list[ToolCall] = Field(default_factory=list)`
- [ ] `class LLMClient(Protocol)`:
  - `complete(self, messages: list[Message], *, model: str) -> str`
  - `complete_with_tools(self, messages: list[Message], *, model: str, tools: list[ToolSpec]) -> AssistantTurn`
- [ ] `class LLMError(Exception)` in `domain/llm_client.py`.
- [ ] `class Settings(BaseSettings)`:
  - `anthropic_api_key: SecretStr`
  - `chat_model: str = "claude-sonnet-4-5"`
  - `compactor_model: str = "claude-haiku-4-5"`
  - `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")`
- [ ] `class AnthropicLLMClient`:
  - `__init__(self, settings: Settings) -> None`
  - `complete(self, messages: list[Message], *, model: str) -> str`
  - `complete_with_tools(self, messages: list[Message], *, model: str, tools: list[ToolSpec]) -> AssistantTurn` (stub that returns an `AssistantTurn` with empty `tool_calls` is acceptable in this deliverable; DO-10 fills it in)
