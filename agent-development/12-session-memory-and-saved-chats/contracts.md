# DO-12 contracts

## Architectural

- [ ] The cap on the active window is owned by `Settings` as
      `int_history_cap: int = 10` (env var `INT_HISTORY_CAP`). The
      value is in *turns*; one turn = one user + one assistant
      message = 2 messages. The REPL computes the message cap as
      `2 * int_history_cap`.
- [ ] `AppState.history_cap: int = 20` is **removed**. It used to
      back the in-REPL trim; the new `Settings.int_history_cap`
      replaces it. The REPL's `_handle_chat` reads the cap from
      `settings` (passed through `AppState.settings`) and falls back
      to 10 when `settings is None` (so a bare `AppState()` in
      pre-DO-04 / pre-DO-12 unit tests still passes through the trim
      unchanged).
- [ ] `AppState` gains a `settings: Settings | None = None` field
      so the REPL can read the cap. Tests that do not need
      `Settings` may pass `settings=None`; the REPL's fallback is
      the documented default `10`.
- [ ] `SessionStore.list_sessions()` is a new method on the
      existing `SessionStore` class. It does **not** read message
      bodies — it counts non-empty lines and reads `st_mtime`. The
      on-disk layout is unchanged (`<id>.jsonl` per session; no
      `<id>.summary.json`).
- [ ] The REPL never imports from `application/compactor.py` for
      this deliverable. `Compactor.summarize` is **not** added.
      `Compactor.compact` (the `/learn` pipeline) is untouched.
- [ ] No **new** `import-linter` contracts are added. The existing
      layered-architecture rule (DO-00) and the DO-11 fastembed /
      sqlite-vec rules continue to apply unchanged.
- [ ] `/resume <session-id>` is a synchronous, **non-blocking**
      load-from-disk. No LLM call, no background thread, no
      compactor invocation. The REPL re-enters the read loop the
      instant the command returns.
- [ ] There is no `/compact` slash command. There is no
      `SessionManager`. There is no `CharEstimateTokenCounter`.
      There is no `ProviderConfig.context_window` field added by
      this deliverable. Earlier auto-compaction planning is
      deliberate mis-planning and is removed.
- [ ] `Repl._handle_chat` persists each chat turn to the on-disk
      transcript via `session_store.append(session_id, msg)`. A
      `seen` set built from `session_store.read(session_id)` at
      the start of each chat turn drops already-persisted
      messages so `/resume` followed by typing never duplicates
      lines in the `.jsonl` file.

## Behavioral

### `Settings.int_history_cap`

- [ ] Default `10`. Env var `INT_HISTORY_CAP`. Validator
      `ge=1, le=100`.
- [ ] A value of `5` means the active window holds the last 10
      messages (= 5 user/assistant turns). A value of `1` means
      the active window holds the last 2 messages (= 1 turn).
- [ ] An out-of-range value (e.g. `0`, `101`, `-1`) raises
      `pydantic.ValidationError` at boot; the REPL does not start.

### `SessionStore.list_sessions`

- [ ] Returns `list[tuple[str, float, int]]`. Tuple shape:
      `(session_id, mtime, message_count)`.
- [ ] One tuple per `<id>.jsonl` file under `self._root`, sorted
      by mtime descending.
- [ ] `message_count` is the number of non-empty lines in the
      file. A trailing newline does not count.
- [ ] Empty session root → returns `[]`.
- [ ] Missing or unreadable files are skipped silently (logged
      at DEBUG) — a corrupt `<id>.jsonl` must not crash `/chats`.
      The corresponding entry is **omitted**, not returned with
      `message_count = -1`.
- [ ] Never raises. Returns `[]` when `self._root` does not
      exist (defensive; the constructor creates it but a test
      may pass a freshly-deleted path).

### `Repl._handle_chat` persistence + trim

- [ ] After appending the user turn + assistant reply to
      `app_state.history`, persists each new message via
      `session_store.append(app_state.session_id, msg)`.
- [ ] Builds a `seen` set from
      `session_store.read(app_state.session_id)` before the
      `complete_with_tools` call so a resumed session whose
      messages are already on disk never re-appends them.
- [ ] Trim runs **after** persistence:
      `cap_in_messages = 2 * settings.int_history_cap` (or
      fallback `10` turns = 20 messages when
      `app_state.settings is None`).
      `app_state.history[:] = app_state.history[-cap_in_messages:]`
      if the history grew past the cap. Older messages are
      dropped from the front, **never** summarised.
- [ ] When `app_state.session_store is None`, the persistence
      step is a no-op (defensive — unit tests construct
      `AppState` without a store). The REPL still trims to the
      cap.
- [ ] When `app_state.session_id == ""` and `session_store is
      not None`, the REPL generates a fresh id via
      `session_store.current_id()` before persisting so the
      in-memory session always has a stable on-disk identity.

### `MemoryCommand`

- [ ] `name == "memory"`, `summary == "Show the active
      conversation window"`.
- [ ] Reads `app_state.session_id`, `app_state.history`
      directly. Counts user / assistant turns (every pair of
      user + assistant = 1 turn). Prints a multi-line readout
      (format pinned below).
- [ ] Readout shape (multi-line, exact format pinned):

      ```
      session:    <short_id>
      turns:      <kept_turns> / <max_turns>
      messages:   <len(history)>
      last user:  <last_user_content, truncated to 60 chars>
      last assistant: <last_assistant_content, truncated to 60 chars>
      ```

      `<short_id>` is the first 8 chars of `session_id`.
      `<kept_turns>` is `len(history) // 2`. `<max_turns>` is
      `settings.int_history_cap` (or `10` when settings is
      `None`). `<last user>` / `<last assistant>` truncate to
      60 chars and end with `"…"` when truncated. When the
      history is empty, those two lines are
      `"(no messages yet)"`.
- [ ] When `app_state.session_store is None` and
      `app_state.session_id == ""`, returns the friendly
      *"No active session yet — type a chat line to start
      one."* message.

### `ChatsCommand`

- [ ] `name == "chats"`, `summary == "List saved sessions on
      disk"`.
- [ ] Calls `session_store.list_sessions()` (returns
      3-tuples). Unpacks each tuple
      `(session_id, mtime, message_count)` directly. **No**
      `NamedTuple` or value type — the presentation layer
      formats from the raw tuple.
- [ ] Renders the table (fixed-width, sorted by mtime desc):

      ```
      session id         last activity   messages
      abc1234567...       just now        18
      a1b2c3d4ef...      3h ago          38
      ...
      active: <id>
      ```

      `<last activity>` is a humanised relative time
      (`"just now"`, `"3m ago"`, `"3h ago"`, `"yesterday"`,
      `"3d ago"`, `"<YYYY-MM-DD>"`).
- [ ] Empty session list: returns
      `CommandResult(message="No saved sessions yet.")`.
- [ ] When `app_state.session_store is None`, returns the
      friendly fallback.

### `ResumeCommand`

- [ ] `name == "resume"`, `summary == "Resume a saved chat
      session by id"`.
- [ ] Usage `/resume <session-id>`. Argument missing → returns
      `CommandResult(message="usage: /resume <session-id>")`;
      the session store is **not** touched.
- [ ] Valid id (transcript non-empty):
      1. Reads the transcript via
         `app_state.session_store.read(session_id)`.
      2. Takes the last `2 * settings.int_history_cap` messages
         (or fallback `10` turns = 20 messages).
      3. Replaces `app_state.history[:]` with that slice.
      4. Sets `app_state.session_id = session_id`.
      5. Returns
         `CommandResult(action="continue",
          message="resumed <id> (<kept> of <total> messages
          loaded).")`.
      No LLM call is made; no compactor is invoked.
- [ ] Unknown id (`read` returns `[]`): returns
      `CommandResult(message="unknown session '<id>'. Run
      `/chats` to list.")`. `app_state.history` is unchanged,
      `app_state.session_id` is unchanged. **No** exception is
      raised.
- [ ] When the transcript has fewer messages than the cap, the
      transcript becomes the new history verbatim (no
      truncation, no padding).
- [ ] When `app_state.session_store is None`, returns the
      friendly fallback *"No session store configured —
      `/resume` is unavailable in this session."*.

## Schema

### `Settings` (DO-12) — one new field

- [ ] `int_history_cap: int = 10` — env `INT_HISTORY_CAP`.
      Validator `ge=1, le=100`.

### `SessionStore` (DO-12) — one new method

- [ ] `list_sessions() -> list[tuple[str, float, int]]`. Pinned
      in the Behavioral section above.

### `AppState` (DO-12) — field changes

- [ ] Removes `history_cap: int = 20`.
- [ ] Gains `settings: Settings | None = None`.

### `Message` / `Compactor` / `ProviderConfig`

- [ ] **No changes.** `Compactor.summarize` is not added.
      `ProviderConfig.context_window` is not added.