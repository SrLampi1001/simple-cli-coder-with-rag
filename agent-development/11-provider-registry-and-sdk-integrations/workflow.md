# DO-11 workflow

## Subagent delegation

**Three subagents.** The work splits cleanly along the Adapter pattern itself:

| # | Owns | Why split out |
|---|---|---|
| **A** | `infrastructure/providers/` (models, registry, errors, first-run seeding) + `docs/providers.md` | Pure data layer — no SDK calls, no UI. Tightly self-contained. |
| **B** | `infrastructure/llm/openai_client.py` + the `import-linter` contract + the `openai` dependency bump. Delete `infrastructure/llm/openai_compat.py` and its test. | Touches `pyproject.toml`, `import-linter`, the wire-format logic in `_messages_to_openai` / `_parse_response` (transferred verbatim from the urllib version). |
| **C** | `infrastructure/llm/anthropic_client.py` rename + `infrastructure/llm/__init__.py`'s `build_llm_client` rewrite + the rename of `tests/infrastructure/llm/test_anthropic_compat_adapter.py` to `test_anthropic_client.py`. | The Anthropic SDK already exists and works; this subagent's only real work is the rename + updating the docstring to remove the MiniMax-specific framing. |
| **D** | The four slash commands (`/connect`, `/providers`, `/provider`, plus the registry → AppState wiring), the Settings pruning, the composition-root rewrite in `cli.py`, the README + `.env.example` + `.gitignore` updates. | Touches the presentation + composition layer; depends on A, B, C. **D runs after A, B, C finish.** |

Order: **A → (B and C in parallel) → D**.

A, B, C can run concurrently because A owns the registry (no SDK changes) and B/C own the adapters (no registry knowledge). D wires them together.

### Context passed to each subagent

**Subagent A** — provider registry + docs:
- `agent-development/README.md` (master).
- The four files in this folder.
- `docs/development-tools.md` §6 (pydantic, pydantic-settings — for SecretStr) and §8 (no extra retry library).
- `infrastructure/local_paths.py` (so A knows how `LocalPaths.data_dir()` is shaped).
- Nothing else.

**Subagent B** — official OpenAI SDK adapter:
- `agent-development/README.md` (master).
- The four files in this folder.
- `docs/development-tools.md` §6 (LLM).
- The current `infrastructure/llm/openai_compat.py` (to be deleted) — A's reference for the wire format, since B's SDK-based code follows the same translation rules.
- The existing `tests/infrastructure/llm/test_openai_compat_adapter.py` (to be deleted) — A's reference for the test shape (B's `test_openai_client.py` covers the same assertions against the SDK).
- Nothing else.

**Subagent C** — Anthropic adapter rename + official endpoint:
- `agent-development/README.md` (master).
- The four files in this folder.
- `docs/development-tools.md` §6 (LLM).
- The current `infrastructure/llm/anthropic_compat.py` (the file body is mostly unchanged — just renamed and re-documented).
- The existing `tests/infrastructure/llm/test_anthropic_compat_adapter.py` (rename only).
- Nothing else.

**Subagent D** — commands + composition + docs:
- `agent-development/README.md` (master).
- The four files in this folder.
- `docs/development-tools.md` §6, §7, §8.
- `src/simple_cli_coder_with_rag/cli.py` (composition root).
- `src/simple_cli_coder_with_rag/presentation/commands/__init__.py` (`AppState`, `Command`, `CommandContext`).
- `src/simple_cli_coder_with_rag/presentation/commands/clear.py`, `exit.py`, `help.py`, `learn.py`, `version.py` (reference implementations of Command).
- `README.md` and `.env.example` and `.gitignore` (to be edited).
- Nothing else (e.g., do **not** re-read the adapter internals — D only uses them via `build_llm_client`).

## Web-search verification (before pinning or writing any adapter code)

This deliverable touches five providers, three of which already have research recorded (nvidia, mistral, minimax — see DO-02 commit history). Two are new and need fresh research: **real Anthropic** (`api.anthropic.com` via `anthropic.Anthropic(...)`) and **real OpenAI** (`api.openai.com` via `openai.OpenAI(...)`).

Before pinning the `openai` dependency or writing `OpenAILLMClient`, subagent B must verify:

1. **Current `openai` SDK version** (PyPI: `openai`). Pin to the major version listed in DO-02's `provider-research:` history or newer. `>=1.0,<2` is the safe lower bound (DO-02 already pins `anthropic>=1.0,<2`).
2. **Auth header for `https://api.openai.com/v1`** — `Authorization: Bearer <key>` (the SDK handles it).
4. **Auth header for `https://api.anthropic.com`** — Anthropic SDK default is `x-api-key`, but the current `AnthropicCompatLLMClient` uses `auth_token` (Bearer) because minimax requires Bearer. **Decision needed:** keep `auth_token` for the renamed `AnthropicLLMClient` (it works for both Anthropic and minimax), or branch per `base_url`. The simpler answer is to keep `auth_token`; subagent C's research must confirm Anthropic's `api.anthropic.com` accepts `Authorization: Bearer` for the Anthropic SDK client (it does, but verify with one web-search citing Anthropic's docs).
5. **Reference implementation** — find one well-known open-source example that wires `openai.OpenAI(base_url=...)` to a non-OpenAI endpoint (nvidia or together.ai). Capture the URL in the commit body.

Include a `provider-research:` block in the commit body:

```
provider-research:
  nvidia:    already-known (DO-02)  anthropic-compat=no   base_url=https://integrate.api.nvidia.com/v1  model=openai/gpt-oss-20b           sdk=openai
  mistral:   already-known (DO-02)  anthropic-compat=no   base_url=https://api.mistral.ai/v1          model=mistral-code-latest            sdk=openai
  minimax:   already-known (DO-02)  anthropic-compat=yes  base_url=https://api.minimax.io/anthropic   model=MiniMax-M3                      sdk=anthropic
  anthropic: NEW                    auth=Bearer (verified) base_url=https://api.anthropic.com          model=claude-3-5-sonnet-latest       sdk=anthropic   ref=<url>
  openai:    NEW                    auth=Bearer           base_url=https://api.openai.com/v1          model=gpt-4o-mini                     sdk=openai      ref=<url>
strategy: one adapter per vendor type (openai, anthropic); providers.json's adapter field dispatches.
```

## Steps

1. **Pre-flight.** `git status` clean.
2. **Web-search** the two new providers (subagents B and C run the searches in their own web-search step; this is step 2 in their sub-tasks). Reconcile the `provider-research:` block above.
3. **Read** `docs/development-tools.md` §6, §7, §8 only.
4. **Write the test files** from `tests.md` first. Confirm they fail (`uv run pytest -q` shows collection errors). Split:
   - A writes `tests/infrastructure/providers/test_*.py`.
   - B writes `tests/infrastructure/llm/test_openai_client.py` and `tests/infrastructure/llm/test_build_llm_client.py`.
   - C writes `tests/infrastructure/llm/test_anthropic_client.py` (renamed) and the official-endpoint test.
   - D writes the four `tests/presentation/commands/test_*.py` and `tests/application/test_knowledge_service_set_llm.py`.
5. **Subagent A** (registry + docs):
   - Create `infrastructure/providers/__init__.py`, `models.py`, `errors.py`, `registry.py`, `default_providers.py` per the contracts.
   - Create `docs/providers.md` documenting the five providers (id, adapter, base URL, default model, signup URL, where to put the key).
6. **Subagent B** (OpenAI SDK adapter):
   - Add `"openai>=1.0,<2"` to `pyproject.toml`. Run `uv lock` to update `uv.lock`.
   - Create `infrastructure/llm/openai_client.py` mirroring the wire-format rules of the deleted `openai_compat.py` but using the SDK.
   - Delete `infrastructure/llm/openai_compat.py` and `tests/infrastructure/llm/test_openai_compat_adapter.py`.
   - Add the `import-linter` `forbidden_imports` contract for `openai`.
7. **Subagent C** (Anthropic adapter rename):
   - Rename `infrastructure/llm/anthropic_compat.py` → `infrastructure/llm/anthropic_client.py`. Update the class name (`AnthropicCompatLLMClient` → `AnthropicLLMClient`) and the docstring (remove the "Used by MiniMax" framing; keep the wire-format translation rules and the `auth_token` note).
   - Rename `tests/infrastructure/llm/test_anthropic_compat_adapter.py` → `tests/infrastructure/llm/test_anthropic_client.py` and update the import. Add the official-endpoint test.
   - Update `infrastructure/llm/__init__.py`'s import.
8. **Subagent D** (commands + composition + docs): runs after A, B, C finish.
   - Create `presentation/commands/connect.py`, `providers.py`, `provider.py` (and any small helpers — e.g., a `prompt_for_key` helper in `presentation/commands/_connect_helpers.py` if it makes the tests cleaner).
   - Add `set_llm(...)` to `KnowledgeService` (or expose `_llm` for the composition root; pick based on the docstring style of the rest of the application layer).
   - Update `cli.py` to construct `ProviderRegistry(...)`, build the active `LLMClient` from `registry.active()` (when set), and register the three new Commands in `_build_registry()`. Update `Settings` to remove the provider fields.
   - Update `README.md`, `.env.example`, `.gitignore`.
9. **Run the gate.** All exit 0.
10. **Verify secrets safety:**
    - `git status` does not show `providers.json`.
    - `python -c "import json; print(json.dumps(json.load(open('~/.local/share/simple-cli-coder-with-rag/providers.json'))['providers']['openai'], indent=2))"` does **not** reveal a key literal in the output — the `SecretStr` representation masks it (use `get_secret_value()` to confirm the key was actually saved).
    - `uv run coder` boots into the REPL even with no `providers.json` (the registry writes the five entries with empty keys, prints the `wrote <path> with 5 pre-populated providers (keys empty; use /connect <id> to add one)` one-liner once, then says *"No active provider"* on the first chat turn).
    - `uv run coder` on a **second** boot (same machine, same user) prints **nothing** about the file (the registry reads it; `was_seeded is False`; the one-liner is suppressed).
    - `uv run coder --version` exits 0 even when the JSON file is missing (no crash on first-run seeding).
    - `/connect openai --no-validate` writes the entered key without any network round-trip (verified by capturing outbound traffic or by stubbing the SDK and confirming `complete(...)` was never called).
11. **Commit (suggested template — adapt to actual changes):** four commits, one per subagent. Each one uses the conventional-commit format from `agent-development/README.md`.
    - A: `feat(providers): ProviderConfig / ProvidersFile models + ProviderRegistry with first-run seeding`
    - B: `feat(llm): official openai SDK adapter (OpenAILLMClient), drop urllib OpenAICompatLLMClient`
    - C: `refactor(llm): rename AnthropicCompatLLMClient to AnthropicLLMClient (official endpoint)`
    - D: `feat(cli): /connect + /providers + /provider commands; Settings loses provider fields`
    - Each commit body carries the relevant slice of the `provider-research:` block above.
12. **Documentation consolidation (FINAL STEP — the next DO cannot start until this commit lands).**
    The subagents above already touch docs inline (D edits README + .env.example + .gitignore;
    A creates `docs/providers.md`). This step is a **final sweep**: it catches anything the
    subagents missed, removes stale mentions, and commits the docs as **one** `docs(do-11):`
    commit — the **last** commit of this DO, separate from the four subagent commits above.
    Scope by file:
    - **README.md** —
        - Add a *Providers* section with the registry table (id, adapter kind, default model,
          env var name, signup URL, deployed base URL — populated from
          `infrastructure/providers/default_providers.py`).
        - Add the three new slash commands (`/connect`, `/providers`, `/provider`) to the
          slash-commands table; describe each in one line.
        - Replace any leftover mentions of `DEFAULT_PROVIDER`, `NVIDIA_API_KEY`,
          `MISTRAL_API_KEY`, `MINIMAX_API_KEY`, `NVIDIA_MODEL`, `MISTRAL_MODEL`,
          `MINIMAX_MODEL`, `*_BASE_URL` in the *Requirements*, *Initialization*, and
          *Configuration reference* sections (these env vars were removed in Subagent D's
          Settings pruning).
        - Update the *How to run* / *Invocation* section to mention `/connect <id>` as the
          in-REPL way to set a key, alongside editing `~/.local/share/.../providers.json`.
        - Update the *Deployed service URLs* (or add one) so every service the chatbot now
          consumes (openai.com, anthropic.com, integrate.api.nvidia.com, api.mistral.ai,
          api.minimax.io) is listed by URL with no secrets exposed.
    - **`.env.example`** —
        - Remove the per-provider `*_API_KEY`, `*_MODEL`, `*_BASE_URL`, and
          `DEFAULT_PROVIDER` lines.
        - Add any env vars the new code path introduced (e.g. a flag for the providers
          file location, if Subagent A added one — verify against
            `infrastructure/settings.py` before adding).
        - Keep the chunking / embedding / vector-store / retriever / file-editor knobs
          untouched (later DOs own them).
    - **`docs/providers.md`** —
        - Confirm the file exists (created by Subagent A) and lists all five pre-populated
          providers (openai, anthropic, nvidia, mistral, minimax) with adapter kind,
          deployed base URL, default model, signup URL, and the
          `~/.local/share/.../providers.json` location.
        - Confirm the cross-link from README's *Providers* section points at
          `docs/providers.md`.
        - Patch any drift between what Subagent A wrote and what the code does.
    - **`coding-assistance/`** — **out of scope for DO-11**. If the folder exists already
      (it should not by DO-11), skip silently. The folder is created and maintained by
      DO-14.
    - The sweep produces **one** commit at the very end of DO-11:
        - `docs(do-11): consolidate README + .env.example + docs/providers.md for provider registry + SDK integrations`
        - The commit body lists every file touched and a one-line summary of the change in
          each (e.g. `- README.md: new Providers section; /connect /providers /provider added to slash commands; legacy env vars removed`).
13. **Post-flight.** `git status` clean.

## Failure modes

- **`SecretStr` round-trip is not masked in `model_dump_json()`** — pin a test (`test_providers_file_dump_masks_api_keys`) that explicitly greps the dumped JSON for the literal key. If pydantic's behaviour changes, the test catches it before commit.
- **`/connect` echoes the key to stdout because the secret is passed through `f"..."` formatting** — `SecretStr.__str__` masks it, but a stray `repr(...)` call leaks it. The `test_connect_does_not_echo_key` test pins this.
- **Switching provider mid-session crashes because the embedder or vector store holds an LLM reference** — none of them does (the embedder is `fastembed`; the vector store is `sqlite-vec`). The `test_provider_switch_rebuilds_knowledge_service_llm` test asserts that only the LLM changes.
- **Atomic write leaves a `.tmp` file when the process is interrupted mid-write** — `Path.replace` is atomic on POSIX and Windows, so the original file is never half-written. The `.tmp` file is left behind but harmless; a future cleanup pass can sweep stale `*.tmp` files at startup if desired (out of scope).
- **First-run seeding on a read-only filesystem fails with `PermissionError`** — the REPL catches it via the existing graceful-error contract (`LLMError`-style one-liner), prints `"cannot write providers.json: <reason>"`, and falls back to in-memory-only mode (no registry on disk; `/connect` still works for the session but the change is lost on restart). Future deliverable can add `--config <path>` for advanced users.
- **`/connect <id>` with `id="anthropic"` and a key that has no credits** — the validation call returns an empty / 402 reply; the command prints `"API key validation failed for anthropic: <reason>"` and does not write back. The user can re-try `/connect anthropic` once credits are topped up.
- **`openai.OpenAI(base_url="https://api.openai.com/v1")` raises `NotFoundError` because of a wrong path** — the SDK uses `v1`; the pre-populated URL is correct. If the provider's docs ever drop `/v1`, the `base_url` in `default_providers.py` needs a one-line update.
- **The `auth_token` parameter (Bearer) is not accepted by `api.anthropic.com`** — web-search confirms it is (Anthropic's docs say SDK accepts `Authorization: Bearer`). If this changes, the rename of `AnthropicLLMClient` to a class that picks `api_key` vs `auth_token` based on `base_url` is a one-line follow-up.
- **DO-10's `complete_with_tools` tests fail because the adapter rename broke an import path** — `test_anthropic_client.py` (renamed) covers the same shape, but the import path changes. The rename commit must update **all** imports — subagent C's git grep must cover `src/`, `tests/`, and any `agent-development/` references.
- **`/connect --no-validate` accidentally writes a bogus key** — that is the contract; the flag is the user's *deliberate* skip of the round-trip, not a lenient retry. `test_connect_existing_provider_no_validate_writes_bad_key` pins this: even when validation would fail, `--no-validate` writes the (bogus) key. The user's `getpass` entry is what they intended; we don't second-guess it.
- **The seed-message one-liner fires on every boot** — `registry.was_seeded` is the single source of truth; `test_registry_was_seeded_false_on_second_run` + `test_composition_root_does_not_print_seed_message_on_second_run` pin both directions. If a future refactor accidentally re-prints on every boot (e.g., by moving the seed-write to a method that runs at the top of every method), the second-run test catches it.
- **`/connect` with the user's key paste trailing a `\n` (terminal paste artifact)** — `getpass.getpass` strips the trailing newline; the `SecretStr` saves exactly what was typed. If the user pastes a multi-line secret (rare but possible), the command saves the first line only and silently drops the rest; a future deliverable could improve by reading until `\n\n`. Out of scope here.