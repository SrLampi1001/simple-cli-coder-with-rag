# DO-12 workflow

## Subagent delegation

**Two subagents.** The work splits along the layered-architecture
boundary, and the simplified scope (Protocol-free, no
`UnknownSessionError`, no `SessionInfo`) collapses what was three
subagents in the previous draft into two:

| # | Owns | Why split out |
|---|---|---|
| **A** | `infrastructure/token_counters/char_estimate.py` + `application/compactor.py` `summarize()` method + `application/session_store.py` `write_session_summary` / `read_session_summary` methods + the DO-11 schema patch (`ProviderConfig.context_window` + `default_providers.py` update + the two new `test_provider_config.py` tests) + the four new `Settings` fields. | Pure data + Strategy layer + the DO-11 patch. Tightly self-contained. |
| **C** | `application/session_manager.py` (the new orchestrator) + `application/knowledge_service.py` (pre-call hook) + the four slash commands (`/memory`, `/chats`, `/resume`, `/compact`) + `AppState` field changes + `Repl._handle_chat` trim removal + `cli.py` `_build_registry()` and `_bootstrap_app_state()` rewiring + `README.md` + `.env.example` + `docs/session-memory.md`. | Orchestration + presentation + composition + docs. Depends on A. |

Order: **A → C**.

A first because C uses A's outputs (the `CharEstimateTokenCounter`
class, the `Compactor.summarize` method, the `SessionStore`
summary methods, the `ProviderConfig.context_window` field, the
new `Settings` fields).

### Context passed to each subagent

**Subagent A** — concrete class + method extensions + DO-11 patch +
Settings:
- `agent-development/README.md` (master).
- The four files in this folder.
- `docs/development-tools.md` §6, §8.
- `domain/llm_client.py` and `domain/messages.py` (the types the
  counter and compactor reference).
- `application/compactor.py` (the class the `summarize` method is
  added to).
- `application/session_store.py` (the class the summary methods are
  added to).
- `infrastructure/settings.py` (the four new fields).
- The DO-11 deliverable folder
  (`11-provider-registry-and-sdk-integrations/`) — read the
  `objective.md` Schema section and the `default_providers.py`
  reference so A knows where to add `context_window`.
- `tests/infrastructure/providers/test_provider_config.py` (to add
  the two new tests).
- Nothing else.

**Subagent C** — `SessionManager` + `KnowledgeService` hook +
Commands + composition + docs:
- `agent-development/README.md` (master).
- The four files in this folder.
- `docs/development-tools.md` §6, §7, §8.
- `application/compactor.py` (uses `Compactor.summarize` from A).
- `application/session_store.py` (uses
  `session_store.write_session_summary` /
  `read_session_summary` from A).
- `application/knowledge_service.py` (adds the
  `session_manager` field and the pre-call hook).
- `application/session_manager.py` (the new file C owns).
- `infrastructure/settings.py` (uses the four new fields from A).
- `infrastructure/token_counters/char_estimate.py` (A's concrete
  class — C imports it in `cli.py` only).
- `presentation/commands/__init__.py` (`AppState`, `Command`,
  `CommandContext`).
- `presentation/commands/clear.py`, `exit.py`, `help.py`,
  `learn.py`, `version.py` (reference implementations of Command).
- `presentation/repl.py` (the trim removal lives here).
- `cli.py` (composition root — C wires the four new Commands and
  `SessionManager` into the bootstrap).
- `README.md` and `.env.example` (to be edited).
- `docs/session-memory.md` (to be created, one page).

## Web-search verification (before pinning)

This deliverable does **not** add new vendor SDKs. The only research
is:

1. **`context_window` defaults per provider** — the values in
   `default_providers.py` (`anthropic=200_000`,
   `openai=128_000`, `nvidia=128_000`, `mistral=128_000`,
   `minimax=128_000`) are reasonable defaults but should be
   confirmed against each provider's current docs. Subagent A's
   web-search step runs a quick `site:docs.anthropic.com` and
   `site:platform.openai.com` check. Findings are recorded in the
   commit body in a `context-window-research:` block:

   ```
   context-window-research:
     anthropic: claude-3-5-sonnet-latest  200_000  (verified docs.anthropic.com)
     openai:    gpt-4o-mini                128_000  (verified platform.openai.com)
     nvidia:    openai/gpt-oss-20b         128_000  (verified integrate.api.nim)
     mistral:   mistral-code-latest         128_000  (verified docs.mistral.ai)
     minimax:   MiniMax-M3             128_000  (conservative placeholder)
   ```

2. **`/memory` and `/chats` UX conventions** — subagent C's
   web-search step pins the relative-time formatting
   (`"3m ago"`, `"yesterday"`, `"<date>"`) used by established
   coding CLIs (OpenCode, Codex). Findings are recorded in the
   commit body in a `ux-research:` block.

## Steps

1. **Pre-flight.** `git status` clean.
2. **Web-search** the two research items above.
3. **Read** `docs/development-tools.md` §6, §7, §8 only.
4. **Write the test files** from `tests.md` first. Confirm they
   fail (`uv run pytest -q` shows collection errors). Split:
   - A writes
     `tests/infrastructure/token_counters/test_char_estimate.py`,
     `tests/application/test_compactor_summarize.py`,
     `tests/application/test_session_store_summary.py`, and the
     two new `tests/infrastructure/providers/test_provider_config.py`
     tests.
   - C writes
     `tests/application/test_session_manager.py`,
     `tests/application/test_knowledge_service_auto_compact.py`,
     and the four `tests/presentation/commands/test_*.py` files
     (with the wall-clock assertion in `test_resume.py`).
5. **Subagent A** (concrete class + extensions + DO-11 patch +
   Settings):
   - Create `infrastructure/token_counters/__init__.py` and
     `infrastructure/token_counters/char_estimate.py`.
   - Extend `application/compactor.py` with
     `Compactor.summarize(...)` (two-message prompt; no fence
     stripping; no JSON validation).
   - Extend `application/session_store.py` with
     `write_session_summary` / `read_session_summary`.
   - Patch DO-11's `ProviderConfig` (in the DO-11 deliverable
     folder) to add `context_window: int = Field(ge=1024)`.
     Update the DO-11 `default_providers.py` table with the
     five values from the `context-window-research:` block. Add
     the two new `test_provider_config.py` tests.
   - Extend `infrastructure/settings.py` with the four new
     fields (`keep_last_n_messages`, `max_response_tokens`,
     `compaction_safety_buffer`, `compaction_threshold`). Update
     `.env.example` with the four new env vars (and remove the
     legacy `HISTORY_CAP` if present).
6. **Subagent C** (`SessionManager` + `KnowledgeService` hook +
   Commands + composition + docs):
   - Create `application/session_manager.py` (the new class).
     The `token_counter: Any` annotation is **typed loosely on
     purpose** — see *Failure modes* below and the DO-15 deferred
     work in `objective.md`.
   - Extend `application/knowledge_service.py` with the
     `session_manager: SessionManager | None` ctor arg and the
     pre-call `maybe_compact_before_chat` hook in `chat()`.
   - Create `presentation/commands/{memory,chats,resume,compact}.py`.
   - Extend `presentation/commands/__init__.py` (`AppState`) with
     `session_manager` and `provider_config`; **remove**
     `history_cap`.
   - Update `presentation/repl.py`: remove the `_handle_chat`
     trim.
   - Update `cli.py` `_build_registry()` to register the four
     new commands. Update `_bootstrap_app_state()` to build the
     `CharEstimateTokenCounter`, the `SessionManager`, wire them
     into `AppState`, pass `SessionManager` into
     `KnowledgeService`, and pass `ProviderConfig` into
     `AppState`.
   - Create `docs/session-memory.md` (one page).
   - Update `README.md` (Slash commands table gains the four new
     rows; new "Session memory and context compaction" section;
     legacy "last 20 turns" wording replaced).
7. **Run the gate.** All exit 0.
8. **Verify behavior:**
   - `uv run coder` starts; type a chat line; assert no trim
     happens (history grows without bound until the threshold is
     crossed).
   - Force a small `compaction_threshold=0.10` (or similar) and
     verify auto-compaction fires after a few chat turns; assert
     `app_state.history` shrinks and `.summary.json` is written.
   - `/memory` prints the readout. `/chats` lists the saved
     session. `/resume <id>` blocks while compacting (visible in
     wall-clock timing — measured by the
     `test_resume_blocks_while_compactor_runs` test).
   - `/compact` works in isolation. The first chat turn after
     `/resume` uses the compacted history (verified via
     `mocker`).
9. **Commit (suggested template — adapt to actual changes):**
   two commits, one per subagent.
   - A: `feat(session-memory): CharEstimateTokenCounter +
     Compactor.summarize + SessionStore summary + ProviderConfig.context_window`
   - C: `feat(cli): SessionManager + auto-compaction hook +
     /memory + /chats + /resume + /compact commands`
   - Each commit body carries the relevant slice of the
     `context-window-research:` block (A only) and the
     `ux-research:` block (C only).
10. **Documentation consolidation (FINAL STEP — the next DO cannot
    start until this commit lands).** Subagent C already touches
    docs inline (README + `.env.example` + creates
    `docs/session-memory.md`). This step is a **final sweep**: it
    catches anything the subagents missed, removes stale mentions
    of the old 20-turn behaviour, and commits the docs as **one**
    `docs(do-12):` commit — the **last** commit of this DO,
    separate from the two subagent commits above. Scope by file:
    - **README.md** —
        - Add the four new slash commands (`/memory`, `/chats`,
          `/resume <session-id>`, `/compact`) to the slash-commands
          table; describe each in one line.
        - Replace **every** leftover mention of the old
          "rolling history of the last 20 turns" wording
          (or `history_cap=20`) with the new behaviour: the rolling
          10-message window enforced by `SessionManager` + the
          auto-compaction hook. The TL acceptance criterion
          requires the active model context to stay capped at the
          10 most recent user/assistant messages — README must
          describe exactly that.
        - Add a new top-level *Session memory and context
          compaction* section that covers: the rolling 10-message
          window, the `keep_last_n_messages` /
          `max_response_tokens` /
          `compaction_safety_buffer` /
          `compaction_threshold` env vars, the four slash
          commands, and the persisted-session model
          (`<session_id>.jsonl` + `<session_id>.summary.json`
          under `~/.local/share/simple-cli-coder-with-rag/sessions/`).
        - Update the *Deployed service URLs* section if DO-11
          already added one (no new service is introduced by
          DO-12 — only local sqlite/jsonl files — so this is
          usually a no-op).
    - **`.env.example`** —
        - Remove the legacy `HISTORY_CAP` line if present.
        - Add the four new env vars introduced by Subagent A:
          `KEEP_LAST_N_MESSAGES`, `MAX_RESPONSE_TOKENS`,
          `COMPACTION_SAFETY_BUFFER`, `COMPACTION_THRESHOLD`
          with their defaults in a comment. Confirm the four
          pydantic validators (`ge=1`, `gt=0`, `gt=0`, `le=0.99`)
          are reflected in a one-line note so a user does not set
          `COMPACTION_THRESHOLD=1.0` and wonder why the REPL
          refuses to start.
    - **`docs/session-memory.md`** —
        - Confirm the file exists (created by Subagent C) and
          documents the 10-message rolling window, the
          auto-compaction hook, the four slash commands, and the
          on-disk layout (`<id>.jsonl`, `<id>.summary.json`).
        - Patch any drift between what Subagent C wrote and what
          the code does.
    - **`coding-assistance/`** — **out of scope for DO-12**. If
      the folder exists already, skip silently. Created and
      maintained by DO-14.
    - The sweep produces **one** commit at the very end of
      DO-12:
        - `docs(do-12): consolidate README + .env.example + docs/session-memory.md for 10-message memory + saved chats`
        - The commit body lists every file touched and a
          one-line summary of the change in each (e.g.
          `- README.md: /memory /chats /resume /compact added; 20-turn wording replaced; Session memory section added`).
11. **Post-flight.** `git status` clean.

## Failure modes

- **`CharEstimateTokenCounter.count` underestimates and overflows**
  — the divisor is `3` (not `4`) specifically to over-count. If
  the estimate is still too low (provider returns
  `context_overflow`), the recoverable-overflow contract
  triggers: `LLMError` is caught by the REPL, the user sees a
  friendly message. A future `TiktokenCounter` (DO-15) can
  replace the implementation without changing the SessionManager
  API.
- **Compaction runs but the new context still overflows** — the
  `safety_buffer=1024` plus `threshold=0.90` together give ~10%
  headroom; if a single chat turn happens to be larger than
  that (e.g., a 50k-token recalled batch), the provider's overflow
  error surfaces. The user can run `/compact` to shrink again
  manually.
- **`Compactor.summarize` returns prose that starts with
  ```` ``` ````** — by design, `summarize` does not strip
  fences. A stray fence in a summary `SystemMessage` is benign
  (the LLM ignores it). If a future test wants to assert no
  fence, it's the LLM's job to comply, not the compactor's.
- **`Compactor.summarize` raises `LLMError`** — propagated to
  `SessionManager.maybe_compact_before_chat`, which catches
  it, logs a one-line `loguru` INFO message, and returns
  `False`. The chat loop proceeds with the un-compacted history.
- **Resumed session's `.jsonl` is corrupt or truncated** — the
  existing `SessionStore.read` returns whatever messages it can
  parse (defensive — empty lines are skipped). The compaction
  runs on the partial transcript; the user sees a slightly worse
  resume, not a crash.
- **`/resume` blocks for 30+ seconds on a long session** —
  that's the cost of an LLM round-trip on a full transcript.
  Mitigation (DO-15): streaming summarisation or a cheaper model.
  The CLI shows the user the command is still working via the
  existing `prompt_toolkit` redraw.
- **`.summary.json` is stale (compactor model changed between
  sessions)** — `resume()` ignores the stale summary and runs a
  fresh `summarize` on the transcript (option B always
  re-summarizes for transcripts ≥ `keep_last_n_messages`). For
  shorter transcripts, no compaction runs at all (the transcript
  fits verbatim).
- **`keep_last_n_messages` env var is set to `0`** — pydantic
  Settings validator rejects it (`ge=1`). The user sees the
  pydantic validation message; the REPL does not start.
- **`max_response_tokens` or `compaction_safety_buffer` set to
  `0`** — pydantic Settings validator rejects (`gt=0`).
- **`compaction_threshold` is `1.0` or higher** — pydantic
  Settings validator rejects (`le=0.99`). The user gets the
  validation message.
- **The `token_counter: Any` annotation on `SessionManager` lets
  type errors slip through** — known and accepted. The DO-15
  follow-up reintroduces a `TokenCounter` Protocol and tightens
  the annotation. Until then, `mypy strict` does not flag
  unknown-method calls on `Any` (it treats them as
  `Any`-returning), so the worst case is a runtime `AttributeError`
  if a wrong object is passed. Caught by the integration tests.
- **DO-11 has already merged without `context_window`** — the
  schema patch must be applied as a separate commit on top of
  DO-11 (DO-11 → DO-12-ctx-window-patch → DO-12). The DO-11
  contracts are updated in-place in the same patch commit so
  the deliverable numbering stays consistent.

## Deferred to DO-15 (v1 follow-up)

When the v1 ship is out, DO-15 will reintroduce the Strategy
indirection:

- A second `TokenCounter` implementation (most likely
  `TiktokenCounter`).
- `domain/token_counter.py` defining a `TokenCounter` Protocol
  with `count(messages, *, tools=(), recalled=()) -> int`.
- `CharEstimateTokenCounter` rewritten to implement the Protocol.
- `SessionManager.__init__`'s `token_counter: Any` annotation
  tightened to `TokenCounter`.
- A new `token_counter_strategy: Literal["char_estimate",
  "tiktoken"] = "char_estimate"` Settings field (env
  `TOKEN_COUNTER_STRATEGY`).
- Per-provider custom compaction prompts in `default_providers.py`
  (each provider's compactor gets a prompt tailored to the model
  family).
- A `summary_drift_warn` flag on `/compact` that warns when the
  on-disk `.summary.json` is older than the `.jsonl`.
- Streaming summarisation to keep `/resume` latency under ~5s
  on 200-message sessions (likely a `StreamingCompactor` class
  that emits partial summaries and the REPL buffers them).

Until DO-15 lands, DO-12 ships with the simpler concrete-only
design. The `token_counter: Any` annotation is the **single**
interface that DO-15 will tighten.