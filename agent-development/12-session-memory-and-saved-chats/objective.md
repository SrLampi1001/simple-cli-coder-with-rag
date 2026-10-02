# DO-12 — Session memory, context-window compaction, and saved chats

## Goal

Replace the local "trim to last 20 turns" backstop in `Repl._handle_chat`
with a context-window-driven session memory system. The chat loop:

1. Estimates the **real** request size (history + tools + recalled chunks)
   using a concrete `CharEstimateTokenCounter` (no Strategy Protocol yet;
   see *Deferred to DO-15*).
2. **Auto-compacts** when the estimate exceeds a configurable threshold
   of the active model's `context_window`, preserving the last
   `keep_last_n_messages` user/assistant turns verbatim and replacing the
   older turns with a `SystemMessage` summary produced by the existing
   `Compactor` (extended with a `summarize` method).
3. **Persists** the compacted summary alongside the raw `.jsonl` transcript
   so a resumed session does not pay the compaction cost again on the
   first turn.
4. Exposes the new behaviour through four slash commands — `/memory`,
   `/chats`, `/resume <id>`, and `/compact` — all wired through the
   existing Command pattern.

`keep_last_n_messages` defaults to **10** (TL literal acceptance criterion:
"active model context remains capped at the 10 most recent user/assistant
messages"). The default is **configurable** via `Settings.keep_last_n_messages`
so users running bigger-window models (200k, GPT-4-class) can lower it to
4 or 6 to match industry defaults (OpenCode, Codex) without breaking the
TL guarantee.

`/resume <id>` follows **option B**: it loads the full transcript, then
runs the compactor inline before rebuilding the active history, and
**blocks the REPL for the duration of the compaction LLM round-trip**.
The user cannot type a new prompt until `/resume` returns.

Satisfies TL acceptance criterion #3: *"saved chats survive an application
restart; `/chats` lists them and `/resume <session-id>` continues one, while
the active model context remains within the model's window with at least
the 10 most recent user/assistant messages kept verbatim."*

## Source of truth

- `OBJECTIVES.md` — Facade pattern (`KnowledgeService` orchestrates the
  LLM, the compactor, the embedder, and the vector store; the
  `SessionManager` slots in beside the Facade), Command pattern (four
  new commands).
- `NEW_REQUIREMENTS.md` §3 *Conversation memory and saved chats*.
- DO-11 contracts — `ProviderConfig.context_window` (added in DO-11 §5 by
  this deliverable's schema patch), `ProviderRegistry`, `LLMClient`.
- DO-04 contracts — `Compactor`, `CompactionError`, `CompactedSession`.
- DO-02 contracts — `LLMClient` Protocol, `LLMError`.
- DO-09 contracts — `RecallCoordinator` (its output is counted against
  the budget).

## Acceptance criteria

### DO-11 schema patch (one-paragraph)

- [ ] `ProviderConfig` (DO-11) gains `context_window: int = Field(ge=1024)`
      describing the model's **input-token** budget. `default_providers.py`
      pre-populates: `anthropic=200_000`, `openai=128_000`,
      `nvidia=128_000`, `mistral=128_000`, `minimax=128_000`
      (confirmed in workflow.md step 2).
- [ ] `tests/infrastructure/providers/test_provider_config.py` gains
      `test_provider_config_rejects_context_window_below_minimum`
      (`context_window=512` raises `ValidationError`) and
      `test_provider_config_default_context_window_is_anthropic_two_hundred`
      (the pre-populated `anthropic` entry has
      `context_window == 200_000`).

### Infrastructure layer

- [ ] `src/simple_cli_coder_with_rag/infrastructure/token_counters/__init__.py`
      re-exports `CharEstimateTokenCounter`.
- [ ] `src/simple_cli_coder_with_rag/infrastructure/token_counters/char_estimate.py`
      defines `class CharEstimateTokenCounter`:
      - `count(messages, *, tools=(), recalled=()) -> int`:
        - Per-message: `max(1, ceil(len(message.content) / 3))` for
          `UserMessage` / `SystemMessage`; same plus the JSON-serialised
          `tool_calls` for `AssistantMessage`; same plus the
          `tool_call_id`'s text contribution for `ToolResultMessage`.
        - Per-tool: `max(1, ceil((len(t.name) + len(t.description) +
          len(json.dumps(t.input_schema))) / 3))`.
        - Per-recalled-chunk: `max(1, ceil(len(chunk) / 4))` (recalled
          chunks are user-readable text, no JSON overhead).
        - Returns the integer sum. **No vendor imports** beyond the
          stdlib (`math.ceil`, `json`).
      - Pure-stdlib. No Protocol seam (one implementation, no
        indirection).

### Application layer

- [ ] `src/simple_cli_coder_with_rag/application/compactor.py` gains
      `Compactor.summarize(self, messages: list[Message]) -> str`:
      - Empty `messages` short-circuits to `"(empty session)"`.
      - Non-empty transcripts are sent through a **two-message** prompt:
        - `SystemMessage(content="Summarise this coding session in
          150-300 prose words: errors, decisions, files touched,
          current task.")`.
        - `UserMessage(content=<transcript>)` where the transcript is
          serialised `f"{role}: {msg.model_dump_json()}"` per message
          (same shape as `_build_compaction_messages`).
      - Returns the raw LLM reply with leading/trailing whitespace
        stripped. **No** markdown-fence stripping, **no** JSON
        validation, **no** "respond with ONLY" trailing instruction —
        a stray fence or trailing sentence is benign in a summary
        `SystemMessage`.
      - Raises `LLMError` if the LLM call fails (propagated unchanged).
      - Does **not** write to disk — the caller (`SessionManager`)
        owns persistence.
- [ ] `src/simple_cli_coder_with_rag/application/session_store.py` gains
      two methods on `SessionStore`:
      - `write_session_summary(self, session_id: str, summary: str) ->
        Path` — writes `<root>/<session_id>.summary.json` with
        `{"session_id": "...", "created_at": "...",
          "summary": "<text>"}`. Returns the path.
      - `read_session_summary(self, session_id: str) -> str | None` —
        returns the `summary` field if the file exists, else `None`.
- [ ] `src/simple_cli_coder_with_rag/application/session_manager.py`
      (new) defines `class SessionManager`:
      - `__init__(self, *, session_id: str, session_store: SessionStore,
          history: list[Message], compactor: Compactor, token_counter:
          Any, context_window: int, max_response_tokens: int = 2048,
          safety_buffer: int = 1024, threshold: float = 0.90,
          keep_last_n_messages: int = 10) -> None`.
        `history` is a **reference** to the same `list` object held by
        `AppState` — `SessionManager` mutates it in place so the REPL
        and `KnowledgeService` see the compacted view immediately.
        `token_counter` is the concrete `CharEstimateTokenCounter`
        instance — typed as `Any` (no Protocol indirection yet; see
        *Deferred to DO-15*). The composition root is the only place
        that constructs the instance.
      - `session_id: str` — read-only attribute.
      - `def current_token_estimate(self, *, recalled: tuple[str, ...] =
          (), tools: tuple[ToolSpec, ...] = ()) -> int` — calls
        `token_counter.count(self._history, recalled=recalled,
          tools=tools)`.
      - `def effective_budget(self) -> int` — returns
        `context_window - max_response_tokens - safety_buffer`.
      - `def maybe_compact_before_chat(self, *, recalled: list[str],
          tools: list[ToolSpec]) -> bool` — if
          `current_token_estimate(recalled=tuple(recalled),
          tools=tuple(tools)) > threshold * effective_budget()`,
          calls `self.compact()`. Returns `True` if compaction ran,
          `False` otherwise. Never raises on compactor failure — the
          failure is logged via `loguru` at INFO level with the
          one-line reason; the chat loop proceeds with the
          un-compacted history.
      - `def compact(self) -> str` — synchronous, **always blocks**
          until the compactor returns. Compacts `self._history` by
          calling `compactor.summarize(self._history[:
          -keep_last_n_messages])` and replacing `self._history` with
          `[SystemMessage(summary), *self._history[-
          keep_last_n_messages:]]`. Persists the summary via
          `session_store.write_session_summary(self._session_id,
          summary)`. Returns the summary text. When the history is
          shorter than `keep_last_n_messages`, the compactor
          short-circuits to `"(empty session)"` and the history is
          left unchanged (compaction is a no-op).
      - `def resume(self, session_id: str) -> str | None` —
          synchronous, **blocks** the REPL for the duration of the
          compactor LLM call. Loads the full transcript via
          `session_store.read(session_id)`. **Always** runs
          `compactor.summarize(transcript[:-keep_last_n_messages])`
          when the transcript has at least `keep_last_n_messages`
          messages (option B), then replaces `self._history` with
          `[summary, *transcript[-keep_last_n_messages:]]`, rebinds
          `self._session_id`, persists the new summary. When the
          transcript has fewer messages, no compaction runs (the
          transcript fits the cap verbatim). Returns the summary
          text. Returns **`None`** when the transcript file does not
          exist (no exception class; the existing `SessionStore.read`
          returns `[]`, which the manager treats as "unknown id").
      - `def list_sessions(self) -> list[tuple[str, float, int, bool]]`
          — returns one tuple per `*.jsonl` file under the session
          root, sorted by mtime descending. Tuple shape:
          `(session_id, mtime, message_count, has_summary)`.
          `message_count` is the line count; `has_summary` is whether
          `<id>.summary.json` exists. Empty session root → returns
          `[]`. No exceptions.

### Presentation layer

- [ ] `src/simple_cli_coder_with_rag/presentation/commands/__init__.py`
      `AppState` adds two fields: `session_manager: SessionManager | None
      = None` and `provider_config: ProviderConfig | None = None`. The
      `history_cap: int = 20` field is **removed** — SessionManager
      owns the lifecycle.
- [ ] `src/simple_cli_coder_with_rag/presentation/commands/memory.py`
      defines `class MemoryCommand`:
      - Name `memory`, summary "Show session token usage and headroom".
      - Reads `current_token_estimate()`, `effective_budget()`,
        `session_id`, and `provider_config` directly and **formats
        the readout itself** (presentation, not orchestration).
      - Readout shape (multi-line, exact format pinned in contracts.md):

        ```
        session:    <id_short>
        messages:   <kept>
        tokens:     <estimate> / <context_window>  (~<percent>%)
        budget:     <effective_budget>
        threshold:  <int(threshold * effective_budget)>
        free:       <max(0, effective_budget - estimate)>
        model:      <default_model>
        ```

      - When `session_manager is None`, returns a friendly *"No active
        session. Run `/chats` to see saved sessions, or `/resume <id>`
        to load one."* message.
- [ ] `src/simple_cli_coder_with_rag/presentation/commands/chats.py`
      defines `class ChatsCommand`:
      - Name `chats`, summary "List saved sessions on disk".
      - Calls `session_manager.list_sessions()` (returns tuples).
        **Formats the table itself** from the tuples (no
        NamedTuple). Columns: `session_id`, `last activity`,
        `messages`, `summary?` (`yes` / `no`). Sorted by mtime
        descending.
      - Includes a trailing `active: <id>` line. Returns
        `CommandResult(action="continue", message=table)`.
      - Empty session list: returns `CommandResult(message="No saved
        sessions yet.")`.
      - When `session_manager is None`, returns the same friendly
        message as `/memory`.
- [ ] `src/simple_cli_coder_with_rag/presentation/commands/resume.py`
      defines `class ResumeCommand`:
      - Name `resume`, summary "Resume a chat session by id (compacts
        inline)".
      - Usage: `/resume <session-id>`. Argument missing → friendly
        message; `session_manager.resume` returning `None` →
        *"unknown session '<id>'. Run `/chats` to list."*.
      - On a valid id, calls `session_manager.resume(session_id)`
        which **blocks** for the compactor LLM call. Returns
        `CommandResult(action="continue", message="resumed
        <session_id> (<kept> kept of <total> messages; summary + last
        <keep_last_n> turns).")`.
      - The REPL cannot accept new lines during the blocking call
        (enforced by the existing Command execution model — the REPL
        awaits `execute(...)` return before re-entering the read
        loop).
- [ ] `src/simple_cli_coder_with_rag/presentation/commands/compact.py`
      defines `class CompactCommand`:
      - Name `compact`, summary "Compact the active session now".
      - Calls `session_manager.compact()`. Returns
        `CommandResult(action="continue", message="compacted:
        <old_total> -> <new_total> messages (<old_tokens> ->
        <new_tokens> estimated tokens).")`.
- [ ] `src/simple_cli_coder_with_rag/presentation/repl.py`:
      - Removes the `history_cap` trim block in `_handle_chat`.
      - `KnowledgeService` is reached via `app_state.knowledge` (no
        change), but `app_state.history` is mutated by
        `SessionManager` instead of by the REPL.
- [ ] `src/simple_cli_coder_with_rag/cli.py` `_build_registry()` adds
      `MemoryCommand`, `ChatsCommand`, `ResumeCommand`,
      `CompactCommand`.
- [ ] `_bootstrap_app_state()` builds a `CharEstimateTokenCounter`, a
      `SessionManager` (with `history=app_state.history`,
      `session_id=session_id`, `session_store=session_store`,
      `compactor=compactor`, `context_window=
      provider_config.context_window`, `keep_last_n_messages=
      settings.keep_last_n_messages`), wires both into `AppState`,
      and passes the `SessionManager` into `KnowledgeService`.

### Settings (`infrastructure/settings.py`)

- [ ] `keep_last_n_messages: int = 10` — env var
      `KEEP_LAST_N_MESSAGES`. Validator: `ge=1, le=200`.
- [ ] `max_response_tokens: int = 2048` — env var
      `MAX_RESPONSE_TOKENS`. Validator: `gt=0`.
- [ ] `compaction_safety_buffer: int = 1024` — env var
      `COMPACTION_SAFETY_BUFFER`. Validator: `gt=0`.
- [ ] `compaction_threshold: float = 0.90` — env var
      `COMPACTION_THRESHOLD`. Validator: `ge=0.10, le=0.99`.
- [ ] The legacy `history_cap` field is removed from `Settings` and
      from `.env.example`.

### Documentation

- [ ] `docs/session-memory.md` (new, **one page**) covers: the
      rolling-window-but-bounded-by-context-window model, the
      auto-compaction trigger formula
      (`threshold * (context_window - max_response_tokens -
      safety_buffer)`), one paragraph each on `/memory`, `/chats`,
      `/resume`, `/compact`. Failure-mode discussion lives in
      `workflow.md` (linked, not duplicated).
- [ ] `README.md` "Slash commands" table gains `/memory`, `/chats`,
      `/resume`, `/compact` rows; new "Session memory and context
      compaction" section links to `docs/session-memory.md`; the
      legacy "rolling history of the last 20 turns" wording is
      replaced with "session memory is bounded by the active
      model's context window; older turns are compacted into a
      summary on demand — see `docs/session-memory.md`".
- [ ] `.env.example` adds `KEEP_LAST_N_MESSAGES=`,
      `MAX_RESPONSE_TOKENS=`, `COMPACTION_SAFETY_BUFFER=`,
      `COMPACTION_THRESHOLD=`. The legacy `HISTORY_CAP` (if
      present) is removed.

### Gate

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

- **Strategy / Protocol seam for `TokenCounter`.** A second
  implementation (e.g. `tiktoken`) lands in **DO-15**. When that
  happens, the `token_counter: Any` annotation on `SessionManager`
  becomes a `Protocol`, `CharEstimateTokenCounter` lives behind it,
  and `default_providers.py` exposes a `token_counter_strategy`
  setting.
- **Per-provider custom compaction prompts.** The compactor uses a
  single generic prompt; per-provider customisation lands in
  **DO-15**.
- **Summary-drift detection.** A `/compact` warning when the
  on-disk `.summary.json` is older than the `.jsonl` lands in
  **DO-15**.
- **Streaming summarisation** to keep `/resume` latency under ~5s
  on 200-message sessions. Lands in **DO-15**.
- `TiktokenCounter` (YAGNI — `CharEstimateTokenCounter` is good
  enough for the conservative over-estimate we need; future DO).
- Persisting the in-memory compacted form to a separate on-disk
  file beyond the raw `.jsonl` + `.summary.json` pair.
- Compaction for the tool-use loop *within* a turn (the
  auto-compaction hook fires only before the user-facing LLM call,
  not between `complete_with_tools` round-trips).

## Depends on

- DO-04 (`Compactor`, `CompactionError`, `CompactedSession` —
  reused for `Compactor.summarize`).
- DO-09 (`RecallCoordinator` — its output is part of the budget).
- DO-11 (`ProviderConfig.context_window`, `ProviderRegistry`,
  `LLMClient`, `KnowledgeService.set_llm()`).

## Blocks

- TL acceptance criterion #3 (saved chats + window management).
  The remaining TL criteria (RAG over docs, coding-assistance
  trace, custom skills, deployed vector store) are independent of
  this deliverable.