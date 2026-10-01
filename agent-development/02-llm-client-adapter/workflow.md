# DO-02 workflow

## Subagent delegation

**One subagent.** `Settings`, `LLMClient`, `Messages`, and the adapter(s) are tightly coupled (the adapter must know the message shape and the per-provider `base_url`s). Splitting risks drift.

### Context passed to the subagent

- `agent-development/README.md` (master).
- The four files in this folder.
- `docs/development-tools.md` §6 (LLM, pydantic, pydantic-settings), §8 (resilience, no extra retry library).
- The `provider-research:` findings from step 2 below.
- Nothing else.

## Web-search verification (before pinning or writing any adapter code)

This deliverable touches three providers whose API shape is unknown up front. Before writing the `Settings` schema or any adapter, run these web-searches and **capture the findings in the commit body** (the DO-02 implementer — not the planner — does the actual searches):

For **each** of NVIDIA, Mistral, MiniMax:

1. **Anthropic-SDK compatibility** — does the provider expose an endpoint that the `anthropic` Python SDK can talk to directly? That is: a `base_url` + the same request/response shape, including the `x-api-key` / `anthropic-version` headers, that makes `anthropic.Anthropic(base_url=..., api_key=...)` work. Search e.g. `websearch "<provider> anthropic compatible API base url"`, `<provider> anthropic sdk`, and the provider's own docs.
2. **Base URL, auth header, model IDs** — record the `base_url`, the auth header name(s), and the model IDs to use for chat / compaction. If the provider requires its own SDK or raw `httpx`, note that and the install command for the SDK.
3. **Reference implementation / example** — search for an existing open-source example that wires the Anthropic SDK (or `httpx`) to this provider. Prefer examples in the provider's own docs or a reputable repo. Capture the URL in the commit body.

Constraints / guardrails:

- If a provider is **not** Anthropic-compatible, **do not** add a new runtime dependency to `pyproject.toml` without flagging it to the user — the plan currently lists `anthropic` as the only LLM SDK. Adding e.g. an `mistralai` SDK is a cross-minor decision and must be confirmed.
- If a provider exposes multiple model families, pick the one closest to the existing role split (a smaller / cheaper model for `compactor_model`, a stronger model for `chat_model`) and record the choice in the commit body.

After the searches, include a `provider-research:` block in the commit body in this shape:

```
provider-research:
  nvidia:   anthropic-compat=<yes|no> base_url=<url or -> sdk> model=<id> ref=<url or "none">
  mistral:  anthropic-compat=<yes|no> base_url=<url or -> sdk> model=<id> ref=<url or "none">
  minimax:  anthropic-compat=<yes|no> base_url=<url or -> sdk> model=<id> ref=<url or "none">
strategy: <one-line description, e.g. "single Anthropic-SDK adapter with per-provider base_url",
          or "per-provider adapters: Anthropic-SDK for nvidia+minimax, mistralai SDK for mistral">
```

## Steps

1. **Pre-flight.** `git status` clean.

2. **Web-search** the three providers per the section above. Record the findings in a `provider-research:` block. Reconcile with `docs/development-tools.md` §6 — the Anthropic SDK choice still holds for any Anthropic-compatible provider; for non-compatible ones, §6 needs a small amendment which the commit body must call out.

3. **Read** `docs/development-tools.md` §6 and §8 only.

4. **Write the test files** from `tests.md` first. Confirm they fail (`uv run pytest -q` shows collection errors).

5. **Write `src/simple_cli_coder_with_rag/domain/messages.py`** with the Pydantic models from `contracts.md`. Use `model_config = ConfigDict(frozen=True)` on the leaf message classes. Use `Field(discriminator="role")` on a `Message` union type if you want to be explicit, otherwise keep `Message` as a base class with the role default and let consumers construct the right subtype.

6. **Write `src/simple_cli_coder_with_rag/domain/llm_client.py`** with:
   - `class LLMClient(Protocol)` — the two methods.
   - `class LLMError(Exception)` — a project-owned exception.
   - `ToolSpec`, `ToolCall`, `AssistantTurn` re-exported from `messages.py` (or imported; pick one and stay consistent).

7. **Write `src/simple_cli_coder_with_rag/infrastructure/settings.py`** with `Settings` per the new schema (three `SecretStr` API keys, `default_provider`, per-provider `*_model` + optional `*_base_url`). `model_post_init` raises `RuntimeError("<provider> API key is required")` when `default_provider`'s key is empty. The other two keys may be empty.

8. **Write the adapter(s)** in `src/simple_cli_coder_with_rag/infrastructure/llm/`. One file per provider. Map `Message` → backend shape. Wrap vendor errors in `LLMError`.
   - **Anthropic-compatible providers:** a single `AnthropicCompatLLMClient` that takes `(api_key, base_url, default_model)` and constructs `anthropic.Anthropic(api_key=..., base_url=...)`. One instance per provider.
   - **Non-compatible providers:** a thin per-provider adapter that uses the provider's SDK or raw `httpx`, mapped to the same `complete` / `complete_with_tools` interface.
   - The composition root picks the right adapter based on `default_provider`.

9. **Update `AppState`** in `src/simple_cli_coder_with_rag/presentation/commands/__init__.py` to add `llm: LLMClient | None = None`.

10. **Update the composition root** in `cli.py`:
    - Instantiate `Settings()`. Catch the empty-key `RuntimeError` and print a friendly message to stderr (this is the **only** place we write to stderr, before `prompt_toolkit` takes over); exit with code 2.
    - Build the adapter for `default_provider` (or build all three and select by `default_provider`).
    - Assign to `app_state.llm`.

11. **Run the gate.** All exit 0.

12. **Verify secrets safety:**
    - `git status` does not show `.env`.
    - Create a temporary `.env` with a fake key for `default_provider`, run `uv run coder --version` — works. Run `git status` again — `.env` is untracked but **ignored** (`!!` marker).

13. **Commit (suggested template — adapt to actual changes):**
    ```bash
    git add src/simple_cli_coder_with_rag/domain \
            src/simple_cli_coder_with_rag/infrastructure \
            tests/domain tests/infrastructure tests/presentation/test_app_state_carries_llm.py
    git status
    git commit -m "feat(llm): NVIDIA/Mistral/MiniMax adapters behind LLMClient Protocol, Settings via .env

    provider-research:
      nvidia:   anthropic-compat=... base_url=... model=... ref=...
      mistral:  anthropic-compat=... base_url=... model=... ref=...
      minimax:  anthropic-compat=... base_url=... model=... ref=...
    strategy: <one-line description of the chosen adapter strategy>

    - domain/llm_client.py: LLMClient Protocol (complete, complete_with_tools) and LLMError
    - domain/messages.py: Pydantic models UserMessage, AssistantMessage, SystemMessage,
      ToolSpec, ToolCall, AssistantTurn
    - infrastructure/llm/<provider>_client.py: <describe per-provider adapters>
      (vendor types do not leak past the adapter)
    - infrastructure/settings.py: pydantic-settings Settings with three SecretStr API keys,
      default_provider + per-provider model/base_url; only the active provider's key is required;
      repr/str mask every key
    - presentation/commands/__init__.py: AppState gains llm field
    - cli.py composition root instantiates Settings + the adapter for default_provider

    Adapter pattern honored: vendor SDK imports are confined to infrastructure/llm/."
    ```
    **Note:** The above message is a template. The summary line, the `provider-research:` block, and the bullet list must reflect what was actually implemented. If a provider turned out not to be Anthropic-compatible and needed its own SDK (added to `pyproject.toml` with user approval), call that out explicitly. If the composition root builds all three adapters and selects by `default_provider`, describe that. If any refactoring occurred — reflect the reality.

14. **Post-flight.** `git status` clean.

## Failure modes

- **A provider turns out not to be Anthropic-compatible** — write a per-provider adapter; do not add a runtime dependency without flagging to the user.
- **`pydantic.ValidationError` instead of `RuntimeError` on empty key** — `SecretStr("")` is technically valid; the explicit check in `model_post_init` must run.
- **Vendor type leakage** — if `mypy` accepts an `anthropic.Message` (or a provider SDK type) in a non-adapter module, the `import-linter` contract is being too permissive. Tighten it (add an explicit `forbidden_imports` contract in `[tool.importlinter]` if needed) before committing.
- **Tests pass locally but fail under `pre-commit`** — usually a `mypy` cache issue. Run `uv run mypy --no-incremental src`.