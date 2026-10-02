# DO-12 — Session memory and saved chats

## Goal

Replace the local "trim to last 20 turns" trim in `Repl._handle_chat`
with a rolling 10-message window backed by on-disk session persistence,
exposed through three slash commands:

1. **`/memory`** — inspect the active conversation window (the messages
   currently held in `app_state.history` and sent to the LLM on every
   chat turn).
2. **`/chats`** — list every saved session on disk by stable id, with
   last-activity timestamp and message count.
3. **`/resume <session-id>`** — load the last 10 messages of a saved
   session into the active context and continue the conversation.
   New messages are appended to that same session on disk so `/resume`
   followed by typing behaves like a single uninterrupted session.

Satisfies TL acceptance criterion #3: *"saved chats survive an
application restart; `/chats` lists them and `/resume <session-id>`
continues one, while active model context remains capped at the 10
most recent user/assistant messages."*

## Non-goals (mis-planning removed)

Earlier drafts of this deliverable conflated `/resume` with an
LLM-driven compaction step (auto-summarise on a context-window
threshold, a separate `/compact` command, a `SessionManager`
orchestrator, a `CharEstimateTokenCounter`, and a "blocking"
interpretation that paused the REPL for the duration of a compactor
round-trip). None of that is in `NEW_REQUIREMENTS.md` §3.

`/resume <session-id>` per the spec is **just** a continuation:
read the saved transcript, populate the active history with its
last 10 messages, swap the active session id, and continue. No LLM
call, no compaction, no blocking pause. The user can type a new
prompt as soon as the command returns.

The trim itself stays simple — `history[:] = history[-2 * cap:]` —
and is the only thing that enforces the "10 most recent" cap.

## Source of truth

- `NEW_REQUIREMENTS.md` §3 *Conversation memory and saved chats*.
- `OBJECTIVES.md` — Command pattern (three new commands), no
  orchestrator, no compactor extension.
- DO-03 contracts — `AppState`, `Repl._handle_chat` (the chat path
  is where the trim and the persistence hook live).
- DO-04 contracts — `SessionStore.append` / `read` (already
  on-disk; reused unchanged).
- DO-11 contracts — `ProviderRegistry` (`/chats` does not need it,
  but `/resume` must not break the active provider wiring).

## Acceptance criteria

### `Settings`

- [ ] `history_cap: int = 10` — env var `INT_HISTORY_CAP`. Validator
      `ge=1, le=100`. Default **10** (= 5 user + 5 assistant turns
      = 10 messages, matching the TL literal acceptance criterion
      "10 most recent user/assistant messages"). When
      `history_cap=5`, the trim keeps the last 10 messages (= 5
      turns). The field replaces the legacy `history_cap: int = 20`
      hard-coded on `AppState`.
- [ ] `.env.example` gains `INT_HISTORY_CAP=10` with a one-line
      comment that the value is in *turns* and that each turn is
      a user/assistant pair (= 2 messages).

### `SessionStore`

- [ ] `SessionStore.append` and `SessionStore.read` already exist
      (DO-04) and are reused unchanged.
- [ ] `SessionStore.list_sessions() -> list[tuple[str, float, int]]`
      (new method). One tuple per `<id>.jsonl` file under
      `self._root`, sorted by mtime descending. Tuple shape:
      `(session_id, mtime, message_count)`. `message_count` is the
      number of non-empty JSON lines in the file (defensive — a
      trailing newline must not count). Empty session root →
      returns `[]`. No exceptions, no `None` entries.
- [ ] `SessionStore.list_sessions` does **not** read the message
      bodies — it counts lines and reads `st_mtime` only, so the
      cost stays O(files) even on a directory with hundreds of
      sessions.

### `AppState`

- [ ] `history_cap: int` field is **removed**. The cap is owned by
      `Settings`; the REPL reads it from the wired `Settings` instance
      passed via `AppState.settings` (a new field). Tests that
      construct `AppState` directly may pass `settings=None` and rely
      on the REPL's fallback `INT_HISTORY_CAP` default.

### `Repl._handle_chat`

- [ ] Trim logic changes from `history_cap = 20` (40 messages) to
      `history_cap = settings.int_history_cap` (default 10 turns =
      20 messages). The trim is `history[:] = history[-2 * cap:]`
      after appending the new turn + assistant reply.
- [ ] After appending the user turn and assistant reply, the REPL
      **persists** them via `session_store.append(session_id, msg)`
      so the on-disk transcript stays in sync with the in-memory
      history. Idempotency is provided by a `seen` set built from
      `session_store.read(session_id)` before the chat turn starts —
      re-appending on `/resume` is impossible because the `seen`
      filter drops any message already on disk.
- [ ] The REPL never calls the compactor, never makes a separate
      LLM call for "session summarisation", and never blocks on a
      background task. `/resume` is a synchronous load-from-disk,
      nothing more.

### Presentation layer — three new commands

- [ ] `presentation/commands/memory.py` defines `MemoryCommand`:
      - Name `memory`, summary "Show the active conversation
        window".
      - Reads `session_id`, `len(history)`, and the last user /
        assistant pair off `AppState` directly. Prints a
        multi-line readout (format pinned in `contracts.md`).
      - When `app_state.session_store is None` or
        `app_state.session_id == ""`, returns a friendly
        *"No active session yet — type a chat line to start one."*
        message.
- [ ] `presentation/commands/chats.py` defines `ChatsCommand`:
      - Name `chats`, summary "List saved sessions on disk".
      - Calls `session_store.list_sessions()` and formats a
        fixed-width table (id, last activity, messages). Sorted
        by mtime descending. Includes a trailing `active:
        <id>` line. Empty list returns *"No saved sessions
        yet."*.
- [ ] `presentation/commands/resume.py` defines `ResumeCommand`:
      - Name `resume`, summary "Resume a saved chat session by
        id".
      - Usage `/resume <session-id>`. Argument missing → friendly
        message; `session_store.read(session_id) == []` →
        *"unknown session '<id>'. Run `/chats` to list."*.
      - On a valid id, the command:
        1. Reads the transcript via `session_store.read(id)`.
        2. Takes the **last `2 * int_history_cap` messages** (the
           "10 most recent user/assistant messages" cap).
        3. Replaces `app_state.history[:]` with that slice.
        4. Updates `app_state.session_id = <id>` so subsequent
           chat turns persist to the resumed session.
        5. Returns
           `CommandResult(action="continue",
            message="resumed <id> (<kept> of <total> messages
            loaded).")`.
      - **No** LLM call, **no** compactor round-trip, **no**
        `history_cap`-vs-`history_size` calculation, **no**
        summary generation, **no** blocking pause. The command
        returns as soon as the file is read.

### `cli.py` wiring

- [ ] `_build_registry()` registers `MemoryCommand`,
      `ChatsCommand`, `ResumeCommand` alongside the existing
      commands.
- [ ] `_bootstrap_app_state()`:
      - Reads `settings.int_history_cap` and passes it via
        `AppState.settings`.
      - Keeps the existing `SessionStore` wiring (DO-04).
      - Generates the initial `session_id` via
        `session_store.current_id()` so the very first chat turn
        already has a stable id.

### Documentation

- [ ] `README.md` "Slash commands" table gains `/memory`,
      `/chats`, `/resume <session-id>` rows; new "Session memory
      and saved chats" section describes: the 10-message rolling
      window (env `INT_HISTORY_CAP`), the on-disk layout
      (`<session_id>.jsonl` under `~/.local/share/simple-cli-coder-with-rag/sessions/`),
      the three slash commands, and the recovery flow
      ("`/chats` after a restart to find an old session;
      `/resume <id>` to keep going").
- [ ] `.env.example` gains `INT_HISTORY_CAP=10` with a comment
      explaining the value is in turns.

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

- **Auto-compaction on a context-window threshold.** Not in
  `NEW_REQUIREMENTS.md` §3. The 10-message cap is a hard limit;
  overflow drops the oldest message, never summarises.
- **A `/compact` slash command.** Not in
  `NEW_REQUIREMENTS.md` §3.
- **A `SessionManager` orchestrator.** The cap + persistence are
  trivial enough that an orchestrator class is overkill.
- **A `CharEstimateTokenCounter` / token estimation.** The cap is
  in *messages*, not *tokens*; estimating tokens would conflate
  the requirement with the mis-planning.
- **A `Compactor.summarize` method on `Compactor`.** The compactor
  stays focused on `/learn`'s structured JSON output.
- **`<session_id>.summary.json` files.** No summaries are
  produced.
- **A `ProviderConfig.context_window` field.** DO-11 stays focused
  on provider wiring; the cap here is provider-agnostic.
- **Persisting every chat turn's first `SystemMessage` to disk.**
  The transcript contains only user / assistant turns; the system
  instruction is added by the adapter on every `chat(...)` call.

## Depends on

- DO-03 (`AppState`, `Repl._handle_chat`, the chat path).
- DO-04 (`SessionStore.append` / `read` / `current_id`).
- DO-11 (`ProviderRegistry` — `/resume` does not touch it, but
  the REPL must not break the active provider wiring on a
  resume).

## Blocks

- TL acceptance criterion #3 (saved chats + window management).
  The remaining TL criteria (RAG over docs, coding-assistance
  trace, custom skills, deployed vector store) are independent of
  this deliverable.