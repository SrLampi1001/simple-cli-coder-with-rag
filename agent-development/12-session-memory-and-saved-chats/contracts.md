# DO-12 contracts

## Architectural

- [ ] `CharEstimateTokenCounter` is a **concrete class** in
      `infrastructure/token_counters/char_estimate.py`. No `Protocol`
      seam exists. When a second implementation arrives (DO-15),
      `domain/token_counter.py` will be reintroduced with a `Protocol`
      and `CharEstimateTokenCounter` will implement it; the
      `SessionManager` annotation will be tightened from `Any` to the
      `Protocol` in the same commit.
- [ ] `SessionManager.__init__` takes `token_counter: Any` — the
      concrete instance, duck-typed. `application/session_manager.py`
      does **not** `import` from `infrastructure/` at runtime. A
      `TYPE_CHECKING` import is permitted for type-hint resolution
      only; `import-linter` is unaffected (it ignores
      `TYPE_CHECKING`-guarded imports).
- [ ] No **new** `import-linter` contracts are added. The existing
      layered-architecture rule (DO-00) and the DO-11 fastembed /
      sqlite-vec rules continue to apply unchanged.
- [ ] `SessionManager` lives in `application/session_manager.py`. It
      imports from `domain/` only — `Message`, `ToolSpec` — and from
      sibling `application/` modules — `Compactor`, `SessionStore`.
      No imports from `infrastructure/`.
- [ ] `KnowledgeService.chat(...)` calls
      `session_manager.maybe_compact_before_chat(...)` before its
      `complete_with_tools` call. The auto-compaction hook is the
      seam where token-budget enforcement lives; `KnowledgeService`
      does not reach `Compactor` or `SessionStore` directly for the
      hook.
- [ ] `AppState` (DO-01) gains `session_manager: SessionManager | None
      = None` and `provider_config: ProviderConfig | None = None`. The
      legacy `history_cap: int = 20` field is **removed**.
- [ ] `Compactor.summarize(...)` is a new method on the existing
      `Compactor` class — no new class is introduced. `Compactor`
      already owns the LLM model; both `compact()` (RAG) and
      `summarize()` (session) use the same configured model.
- [ ] `SessionStore.write_session_summary` / `read_session_summary`
      are new methods on the existing `SessionStore` class. The
      `.summary.json` file lives in the same `root` directory as the
      `.jsonl` transcripts.
- [ ] The `Repl._handle_chat` trim block (`history[:] =
      history[-cap:]`) is **deleted**. The REPL never truncates
      history directly.

## Behavioral

### `CharEstimateTokenCounter`

- [ ] `count(messages, *, tools=(), recalled=())` returns an integer
      satisfying:
      - For an empty `messages` list (and empty `tools`, empty
        `recalled`): `0`.
      - For a single `UserMessage(content="hi")`: `1`
        (because `ceil(2 / 3) = 1`).
      - For a single `SystemMessage(content="x" * 120)`: `40`
        (`ceil(120 / 3)`).
      - For a single `AssistantMessage(content="ok",
        tool_calls=[ToolCall(id="1", name="read",
        arguments={"path": "/a"})])`: the message text contribution
        plus the JSON-serialised `tool_calls` array length, divided
        by 3 (pin the exact integer in the test).
      - For a single `ToolResultMessage(tool_call_id="abc",
        content="result")`: the message text contribution plus the
        `tool_call_id`'s character count, divided by 3.
      - For `tools=[ToolSpec(name="read", description="...",
        input_schema={"type":"object"})]`: returns
        `ceil((len(name) + len(description) +
        len(json.dumps(input_schema))) / 3)`.
      - For `recalled=["some text"]`: returns `ceil(len("some text")
        / 4) = 3`.
- [ ] The implementation never raises on malformed inputs (missing
      fields, wrong types). Defensive defaults return `0` for the
      affected piece — the function always returns an integer.
- [ ] The implementation is **deterministic** — given the same
      inputs, it always returns the same integer (no time-based
      randomness, no global state).

### `Compactor.summarize`

- [ ] Empty `messages` short-circuits to `"(empty session)"` without
      contacting the LLM.
- [ ] Non-empty `messages` are sent through a **two-message**
      prompt:
      - `SystemMessage(content="Summarise this coding session in
        150-300 prose words: errors, decisions, files touched,
        current task.")`.
      - `UserMessage(content=<transcript>)`. The transcript is
        serialised `f"{role}: {msg.model_dump_json()}"` per message.
- [ ] The returned string is the raw LLM reply with leading and
      trailing whitespace stripped via `str.strip()`. **No**
      markdown-fence stripping, **no** JSON parsing, **no**
      "respond with ONLY" trailing instruction.
- [ ] `LLMError` propagates verbatim. The REPL catches it and prints
      a one-line message; the chat loop survives.
- [ ] `summarize` does **not** write to disk — `SessionStore` is
      never touched.

### `SessionStore.write_session_summary` / `read_session_summary`

- [ ] `write_session_summary(session_id, summary)` writes
      `<root>/<session_id>.summary.json` with JSON
      `{"session_id": "<id>", "created_at": "<UTC ISO>", "summary":
      "<text>"}` (pretty-printed, UTF-8). Creates the root if
      missing.
- [ ] `read_session_summary(session_id)` returns the `summary`
      string when the file exists; `None` when it does not. Never
      raises `FileNotFoundError`.

### `SessionManager.maybe_compact_before_chat`

- [ ] Returns `False` (no compaction) when
      `current_token_estimate(recalled=recalled, tools=tools) <=
      threshold * effective_budget()`.
- [ ] Returns `True` when the threshold is exceeded **and** the
      compaction succeeds.
- [ ] Returns `False` (no compaction, **and** no exception) when
      the compaction itself fails (`Compactor.summarize` raises
      `LLMError`). The failure is logged via `loguru` at INFO
      level with the one-line reason.
- [ ] `effective_budget()` = `context_window - max_response_tokens -
      safety_buffer`. A model with `context_window=200_000`,
      `max_response_tokens=2_048`, `safety_buffer=1_024` has an
      effective budget of `196_928`. At `threshold=0.90`, compaction
      triggers at `~177_235` estimated tokens.

### `SessionManager.compact`

- [ ] Synchronous, **always blocks** until the compactor returns
      (the compactor's LLM call is itself synchronous).
- [ ] The compaction input is
      `self._history[:-keep_last_n_messages]` (when the history
      has more than `keep_last_n_messages` messages). When shorter,
      the compactor short-circuits and the history is left
      unchanged.
- [ ] The replacement is `self._history = [SystemMessage(summary),
      *self._history[-keep_last_n_messages:]]`. The old list object
      is rebound in place; `AppState.history` (which holds the same
      reference) sees the change.
- [ ] The summary is persisted via
      `session_store.write_session_summary(self._session_id,
      summary)` **after** the history is replaced.

### `SessionManager.resume`

- [ ] Synchronous, **blocks the REPL** for the duration of the
      compactor LLM call. The REPL's read loop only resumes after
      `execute(...)` returns — the existing Command execution model
      enforces this naturally.
- [ ] Loads the full transcript via
      `session_store.read(session_id)`. When the file is missing,
      `SessionStore.read` returns `[]`; `resume()` returns
      `None` to signal "unknown session".
- [ ] When the transcript has `keep_last_n_messages` or more
      messages, **always** runs
      `compactor.summarize(transcript[:-keep_last_n_messages])`
      (option B), replaces `self._history` with
      `[summary, *transcript[-keep_last_n_messages:]]`, rebinds
      `self._session_id`, persists the new summary.
- [ ] When the transcript has fewer messages, no compaction runs;
      the transcript becomes the new history verbatim.
- [ ] Updates `AppState.session_id` to the resumed id.

### `SessionManager.list_sessions`

- [ ] Returns `list[tuple[str, float, int, bool]]`. Tuple shape:
      `(session_id, mtime, message_count, has_summary)`.
- [ ] Sorted by mtime descending (most recently modified first).
- [ ] `message_count` is the line count of `<id>.jsonl`.
- [ ] `has_summary` is `True` when `<id>.summary.json` exists, else
      `False`.
- [ ] Empty session root → returns `[]`. No exceptions.

### `MemoryCommand`

- [ ] `name == "memory"`, `summary == "Show session token usage and
      headroom"`.
- [ ] Reads `session_manager.current_token_estimate()`,
      `session_manager.effective_budget()`,
      `session_manager.session_id`, and
      `app_state.provider_config.context_window` /
      `provider_config.default_model` directly. Formats the readout
      in the Command (presentation, not orchestration).
- [ ] Returns `CommandResult(action="continue",
      message=<readout>)` of the shape (pinned line by line):

      ```
      session:    <id_short>
      messages:   <kept>
      tokens:     <estimate> / <context_window>  (~<percent>%)
      budget:     <effective_budget>
      threshold:  <int(threshold * effective_budget)>
      free:       <max(0, effective_budget - estimate)>
      model:      <default_model>
      ```

      `<id_short>` is the first 8 chars of `session_id`.
      `<kept>` is `len(session_manager._history)` (private read; or
      a new public `history_size` property — design choice; pin in
      the test).
      `<percent>` is `round(estimate / context_window * 100, 1)`.
      `<free>` is `max(0, effective_budget - estimate)`.
- [ ] When `app_state.session_manager is None`, returns the
      friendly fallback.
- [ ] When `app_state.provider_config is None` but
      `session_manager` is present, omits the `model:` line and
      uses the placeholder `"(no provider configured)"`.

### `ChatsCommand`

- [ ] `name == "chats"`, `summary == "List saved sessions on
      disk"`.
- [ ] Calls `session_manager.list_sessions()` (returns tuples).
      Unpacks each tuple `(session_id, mtime, message_count,
      has_summary)` directly. **No** `NamedTuple` or value type —
      the presentation layer formats from the raw tuple.
- [ ] Renders the table (fixed-width, sorted by mtime desc):

      ```
      session id         last activity   messages   summary?
      abc1234567...       just now        18         yes
      a1b2c3d4ef...      3h ago          38         yes
      ...
      active: <id>
      ```

      `<last activity>` is a humanised relative time (`"just now"`,
      `"3m ago"`, `"3h ago"`, `"yesterday"`, `"3d ago"`, `"<date>"`).
      `<summary?>` is `"yes"` when `has_summary` is `True`,
      otherwise `"no"`.

- [ ] Empty session list: returns `CommandResult(message="No saved
      sessions yet.")`.
- [ ] When `session_manager is None`: returns the same friendly
      fallback as `/memory`.

### `ResumeCommand`

- [ ] `name == "resume"`, `summary == "Resume a chat session by id
      (compacts inline)"`.
- [ ] Usage: `/resume <session-id>`. Argument missing → friendly
      message.
- [ ] Valid id → calls `session_manager.resume(session_id)` (which
      **blocks** for the compactor LLM round-trip). When the
      returned value is `None`, returns the friendly *"unknown
      session"*. When non-`None`, returns
      `CommandResult(action="continue", message=<formatted>)`
      where `<formatted>` is `"resumed <id> (<kept> kept of <total>
      messages; summary + last <keep_last_n> turns)."`.

### `CompactCommand`

- [ ] `name == "compact"`, `summary == "Compact the active session
      now"`.
- [ ] Calls `session_manager.compact()`. Returns
      `CommandResult(action="continue", message=<formatted>)` where
      `<formatted>` is `"compacted: <old_total> -> <new_total>
      messages (<old_tokens> -> <new_tokens> estimated tokens)."`.

## Schema

### `ProviderConfig` (DO-11) — schema patch

- [ ] Gains `context_window: int = Field(ge=1024)`. Default in
      `default_providers.py` per provider:
      - `nvidia`: `128_000`
      - `mistral`: `128_000`
      - `minimax`: `128_000`
      - `anthropic`: `200_000`
      - `openai`: `128_000`

### `CharEstimateTokenCounter` (DO-12) — concrete class

- [ ] `infrastructure/token_counters/char_estimate.py` defines the
      concrete class. Pure-stdlib (`math.ceil`, `json`). No IO.

### `SessionManager` (DO-12) — new class

- [ ] `__init__(self, *, session_id: str, session_store:
      SessionStore, history: list[Message], compactor: Compactor,
      token_counter: Any, context_window: int,
      max_response_tokens: int = 2048, safety_buffer: int = 1024,
      threshold: float = 0.90, keep_last_n_messages: int = 10) ->
      None`. `history` is a reference to the same list object held
      by `AppState.history` (mutation in place).
- [ ] `session_id: str` — read-only attribute.
- [ ] `def current_token_estimate(self, *, recalled: tuple[str,
      ...] = (), tools: tuple[ToolSpec, ...] = ()) -> int`.
- [ ] `def effective_budget(self) -> int`.
- [ ] `def maybe_compact_before_chat(self, *, recalled: list[str],
      tools: list[ToolSpec]) -> bool`.
- [ ] `def compact(self) -> str`.
- [ ] `def resume(self, session_id: str) -> str | None`.
- [ ] `def list_sessions(self) -> list[tuple[str, float, int,
      bool]]`.

### `Compactor.summarize` (DO-12) — new method

- [ ] Signature: `def summarize(self, messages: list[Message]) ->
      str`. Empty input short-circuits; non-empty input goes
      through the two-message prompt and returns the raw reply
      with `str.strip()`.

### `SessionStore.write_session_summary` / `read_session_summary`

- [ ] Pinned in the Behavioral section above.

### `Settings` (DO-12) — four new fields

- [ ] `keep_last_n_messages: int = 10` — env
      `KEEP_LAST_N_MESSAGES`. Validator: `ge=1, le=200`.
- [ ] `max_response_tokens: int = 2048` — env
      `MAX_RESPONSE_TOKENS`. Validator: `gt=0`.
- [ ] `compaction_safety_buffer: int = 1024` — env
      `COMPACTION_SAFETY_BUFFER`. Validator: `gt=0`.
- [ ] `compaction_threshold: float = 0.90` — env
      `COMPACTION_THRESHOLD`. Validator: `ge=0.10, le=0.99`.
- [ ] The legacy `history_cap` field is removed from `Settings` and
      from `.env.example`.

### `AppState` (DO-12) — field changes

- [ ] Gains `session_manager: SessionManager | None = None` and
      `provider_config: ProviderConfig | None = None`.
- [ ] Removes `history_cap: int = 20`.