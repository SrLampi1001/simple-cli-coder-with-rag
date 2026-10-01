# DO-02 workflow

## Subagent delegation

**One subagent.** `Settings`, `LLMClient`, `Messages`, and `AnthropicLLMClient` are tightly coupled (the SDK adapter must know the message shape). Splitting risks drift.

### Context passed to the subagent

- `agent-development/README.md` (master).
- The four files in this folder.
- `docs/development-tools.md` §6 (LLM, pydantic, pydantic-settings), §8 (resilience, no extra retry library).
- Nothing else.

## Web-search verification

Before pinning the `anthropic` SDK version (currently inherited from DO-00's `pyproject.toml`):

1. `websearch "anthropic python sdk pypi latest version 2026"` — confirm the pinned range is still current.

If the version has moved within the same minor, update `pyproject.toml` and add a `bump:` line to the commit body. If it has moved across a major, stop and ask the user.

## Steps

1. **Pre-flight.** `git status` clean.

2. **Read** `docs/development-tools.md` §6 and §8 only.

3. **Write the test files** from `tests.md` first. Confirm they fail (`uv run pytest -q` shows collection errors).

4. **Write `src/simple_cli_coder_with_rag/domain/messages.py`** with the Pydantic models from `contracts.md`. Use `model_config = ConfigDict(frozen=True)` on the leaf message classes. Use `Field(discriminator="role")` on a `Message` union type if you want to be explicit, otherwise keep `Message` as a base class with the role default and let consumers construct the right subtype.

5. **Write `src/simple_cli_coder_with_rag/domain/llm_client.py`** with:
   - `class LLMClient(Protocol)` — the two methods.
   - `class LLMError(Exception)` — a project-owned exception.
   - `ToolSpec`, `ToolCall`, `AssistantTurn` re-exported from `messages.py` (or imported; pick one and stay consistent).

6. **Write `src/simple_cli_coder_with_rag/infrastructure/settings.py`** with `Settings`. Use `pydantic_settings.BaseSettings` and `pydantic.SecretStr`. The `model_post_init` raises `RuntimeError("ANTHROPIC_API_KEY is required")` when the secret is empty.

7. **Write `src/simple_cli_coder_with_rag/infrastructure/llm/__init__.py`** (empty) and `src/simple_cli_coder_with_rag/infrastructure/llm/anthropic_client.py` with `AnthropicLLMClient`. Map `Message` → SDK shape:
   - `SystemMessage` → `system=...`
   - `UserMessage` → `messages=[{"role": "user", "content": "..."}]`
   - `AssistantMessage` → `messages=[{"role": "assistant", "content": "..."}]`

   The SDK's `messages.create(...)` returns a `Message` whose `content` is a list of blocks. Extract the first `TextBlock`'s `text`. Wrap `anthropic.APIError` in `LLMError`.

   `complete_with_tools` for now: pass `tools=[tool.input_schema for tool in tools]` and return `AssistantTurn(content=extracted_text, tool_calls=[])`. DO-10 fills the real tool-use logic.

8. **Update `AppState`** in `src/simple_cli_coder_with_rag/presentation/commands/__init__.py` to add `llm: LLMClient | None = None`.

9. **Update the composition root** in `src/simple_cli_coder_with_rag/cli.py`:
   - Instantiate `Settings()`. Catch the empty-key `RuntimeError` and print a friendly message to stderr (this is the **only** place we write to stderr, before `prompt_toolkit` takes over); exit with code 2.
   - Build `AnthropicLLMClient(settings)`.
   - Assign to `app_state.llm`.

10. **Run the gate.** All exit 0.

11. **Verify secrets safety:**
    - `git status` does not show `.env`.
    - Create a temporary `.env` with a fake key, run `uv run coder --version` — works. Run `git status` again — `.env` is untracked but **ignored** (`!!` marker).

12. **Commit (suggested template — adapt to actual changes):**
    ```bash
    git add src/simple_cli_coder_with_rag/domain \
            src/simple_cli_coder_with_rag/infrastructure \
            tests/domain tests/infrastructure tests/presentation/test_app_state_carries_llm.py
    git status
    git commit -m "feat(llm): Anthropic adapter behind LLMClient Protocol, Settings via .env

    - domain/llm_client.py: LLMClient Protocol (complete, complete_with_tools) and LLMError
    - domain/messages.py: Pydantic models UserMessage, AssistantMessage, SystemMessage,
      ToolSpec, ToolCall, AssistantTurn
    - infrastructure/llm/anthropic_client.py: AnthropicLLMClient wraps anthropic.Anthropic,
      maps Message -> SDK shape, wraps APIError in LLMError (vendor type does not leak)
    - infrastructure/settings.py: pydantic-settings Settings with SecretStr API key,
      empty key raises RuntimeError at startup, repr/str mask the key
    - presentation/commands/__init__.py: AppState gains llm field
    - cli.py composition root instantiates Settings + AnthropicLLMClient

    Adapter pattern honored: anthropic import is confined to infrastructure/llm/."
    ```
    **Note:** The above message is a template. Edit the summary and bullet points to match what was actually implemented. If the Protocol shape changed, if `complete_with_tools` was deferred, if Settings fields differ, or if any refactoring occurred — reflect the reality in the commit body.

13. **Post-flight.** `git status` clean.

## Failure modes

- **`pydantic.ValidationError` instead of `RuntimeError` on empty key:** make sure `model_post_init` runs the explicit check; `SecretStr("")` is technically a valid `SecretStr` and won't trip `Field(...)`.
- **Vendor type leakage:** if `mypy` accepts an `anthropic.Message` in a non-adapter module, the `import-linter` contract is being too permissive. Tighten the contract (add an explicit `forbidden_imports` contract in `[tool.importlinter]` if needed) before committing.
- **Tests pass locally but fail under `pre-commit`:** usually a `mypy` cache issue. Run `uv run mypy --no-incremental src`.
