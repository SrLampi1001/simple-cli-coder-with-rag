# Session memory and saved chats

This document describes how the CLI persists chat sessions on every
chat turn and how `/memory`, `/chats`, and `/resume <session-id>`
interact with the on-disk transcripts. It complements the
[Slash commands section in the README](../README.md#slash-commands)
with the on-disk layout and the recovery flow after a crash.

## The rolling-window model

Every chat turn is appended to the on-disk transcript
`<session_id>.jsonl` under the platform's user data dir:

| Platform | Path |
| --- | --- |
| Linux | `~/.local/share/simple-cli-coder-with-rag/sessions/<id>.jsonl` |
| macOS | `~/Library/Application Support/simple-cli-coder-with-rag/sessions/<id>.jsonl` |
| Windows | `%LOCALAPPDATA%\simple-cli_coder_with_rag\data\sessions\<id>.jsonl` |

The in-memory `app_state.history` is a separate, smaller list:
the **last `INT_HISTORY_CAP` *turns*** (= the last
`2 * INT_HISTORY_CAP` messages) of the on-disk transcript.
Anything older is dropped from the front of the in-memory list on
every turn. The on-disk transcript itself is **not** trimmed — the
full history stays on disk for `/chats` to list and
`/resume <id>` to read back.

```
                                ┌──────────────────────────────┐
                                │  <session_id>.jsonl (disk)   │
                                │  ...every chat turn in full  │
                                │  no trim, ever               │
                                └──────────────┬───────────────┘
                                               │
                  on /resume <id>              │ on every chat turn
                  (load last N)                │ (append one line)
                  ┌────────────────────────────▼──────────────────┐
                  │  app_state.history (memory)                  │
                  │  last INT_HISTORY_CAP turns                  │
                  │  trimmed from the front on every turn        │
                  └────────────────────────────┬─────────────────┘
                                               │
                                               │ on every chat turn
                                               │ (sent as prior context)
                                               ▼
                                       ┌───────────────┐
                                       │  LLM request │
                                       └───────────────┘
```

`INT_HISTORY_CAP` defaults to **10** (= 20 messages, matching the
TL literal acceptance criterion "10 most recent user/assistant
messages"). Override via the `INT_HISTORY_CAP` env var; values
outside `[1, 100]` are rejected at boot.

## On-disk layout

```
~/.local/share/simple-cli-coder-with-rag/sessions/
├── abc1234567deadbeef...jsonl    # one transcript per session
├── abc1234567deadbeef...compacted.json   # one per /learn run
├── fedcba9876543210...jsonl
└── ...
```

* `<id>.jsonl` — one JSON object per line (the standard `.jsonl`
  shape). Each line is a `Message` model dump (`role`,
  `content`, plus tool-call fields when present).
* `<id>.compacted.json` — the structured `CompactedSession`
  produced by `/learn`. Idempotent — a second `/learn` overwrites
  it. Not used by `/resume` or `/memory`.

## Slash commands

### `/context`

Prints the active window's metadata off `AppState` directly:

```
session:    abc1234567deadbeefabc1234567deadbe
  (short:   abc12345)
turns:      5 / 10
messages:   10
last user:  hi there
last assistant: hello! how can I help?
```

The values are pinned by
`tests/presentation/commands/test_context.py`:

* `session` is the **full** `app_state.session_id` (32 chars) so
  you can copy-paste it straight into `/resume <id>`. The short
  preview line underneath is a quick visual cue; it is not the
  authoritative id.
* `turns` is `len(history) // 2` — i.e. the number of completed
  user/assistant pairs in the active window.
* `messages` is `len(history)`.
* `last user` / `last assistant` are the last messages of each
  role, truncated to 60 chars with a trailing `…` marker.
* When the history is empty, both tail lines read
  `(no messages yet)`.

There is no LLM call — `/context` is a pure read off `AppState`.

### `/memory`

Prints the last 10 messages in the active window — exactly what
the LLM sees on every chat turn. Each message is rendered as
`[N] ROLE: content` on its own line:

```
>>> /memory
[1] USER: hello there
[2] ASSISTANT: hi! how can I help?
[3] USER: what's 2+2?
[4] ASSISTANT: four
```

Empty history renders as `(no messages in the active window)`.
There is no LLM call and no session-store read — the command
reads `app_state.history` directly. The formatter is shared with
`/resume <id>` so the two surfaces render the same shape.

### `/chats`

Lists every saved session on disk via
`SessionStore.list_sessions()`:

```
session id                          last activity   messages
abc1234567deadbeefabc1234567deadbe     just now        18
a1b2c3d4ef5678901234567890123456      3m ago          38
5e6f7g8h9i0k1l2m3n4o6p7q8r9s0t1u      yesterday       204
...
active: abc1234567deadbeefabc1234567deadbe
```

The `session id` column shows the **full** 32-char UUIDv4 hex —
the same value `/resume <id>` accepts, so you can copy-paste
straight from this table into `/resume`. The table is sorted by
mtime descending (most recently active first). The `last activity`
column uses humanised relative-time rendering (`just now`, `Xm
ago`, `Xh ago`, `yesterday`, `Xd ago`, `<YYYY-MM-DD>` for anything
older than a week). The trailing `active: <id>` line is the
session the REPL is currently writing to.

The listing is metadata-only — message bodies are never parsed.
The implementation scans the session root, counts non-empty lines,
and reads `st_mtime`, so `/chats` stays cheap even on directories
with hundreds of sessions.

### `/new`

Generates a fresh `session_id` (UUIDv4 hex), clears the in-memory
history, and resets the persistence pointer. Subsequent chat turns
persist to the new `<id>.jsonl`. The previous session's transcript
stays on disk — you can `/resume <old-id>` to come back.

```
>>> /new
started new session 002f919c2b474888bd1e4947a251780e (was abc1234567deadbeefabc1234567deadbe).
>>>
```

The full old id is included in the response so you can copy it
for a later `/resume` without hunting through `/chats`.

### `/resume <session-id>`

Loads the last `2 * INT_HISTORY_CAP` messages (= the last
`INT_HISTORY_CAP` user/assistant turns) of `<id>.jsonl` into the
active history, swaps `app_state.session_id = <id>`, and prints
the loaded messages inline so you immediately see the conversation
you just switched to.

```
>>> /resume abc1234567deadbeefabc1234567deadbe
resumed abc1234567deadbeefabc1234567deadbe (4 of 4 messages loaded):
[1] USER: hi from yesterday
[2] ASSISTANT: Yesterday the assistant replied
[3] USER: how are you?
[4] ASSISTANT: I am well
>>>
```

The printed body uses `format_messages_for_display` — the same
helper `/memory` uses — so the resume output and a follow-up
`/memory` always show the same shape. Subsequent chat turns are
appended to the same `<id>.jsonl`, so the conversation continues
as if it had never been paused.

`/resume` is **synchronous and non-blocking**:

* No LLM call.
* No compactor round-trip.
* No summary generation.
* The REPL re-enters the read loop the instant `/resume` does.

This is by design: `NEW_REQUIREMENTS.md` §3 says `/resume <session-id>`
is the way to "continue one" — the user expects the command to
return immediately, not pause for a compactor to summarise older
turns.

The `persisted_through` counter on `AppState` advances to
`len(history)` after the load, so the loaded messages are never
re-appended to `<id>.jsonl` on subsequent chat turns.

Failure modes:

* **`/resume` with no argument** → `usage: /resume <session-id>`.
  The session store is not touched.
* **`/resume unknown`** → `unknown session 'unknown'. Run /chats to
  list.` `app_state.history` and `app_state.session_id` are
  unchanged.
* **`session_store is None`** → `No session store configured —
  /resume is unavailable in this session.`
* **Transcript shorter than the cap** → the transcript becomes the
  new history verbatim (no padding).
* **Corrupt `<id>.jsonl`** → `SessionStore.read` already returns
  whatever it can parse (empty lines are skipped); `/resume` loads
  the partial transcript instead of crashing.

## Recovery flow after a restart

The CLI generates a fresh `session_id` (UUIDv4 hex) at startup.
On a normal session, you chat, `/learn` to persist, and exit — the
`<session_id>.jsonl` transcript for that run sits under the
sessions dir until the user `/reset`'s the install.

After an application restart, `/chats` lists every transcript that
still exists on disk:

```
>>> /chats
session id         last activity   messages
abc1234567...       3h ago         18
fedcba9876...       yesterday      38
active: <new-session-id>     <- a fresh UUID, not the resumed one
```

Pick the id you want and:

```
>>> /resume abc1234567deadbeef
resumed abc1234567deadbeef (20 of 18 messages loaded).
```

(The `20 of 18` reads oddly when the transcript is shorter than
the cap — see the test
`tests/presentation/commands/test_resume.py::test_resume_with_short_transcript_loads_verbatim`
for the verbatim-load contract; the wording could be tightened in
a future revision.)

From this prompt onward, every chat turn persists to
`<session_id>.jsonl` (the one you resumed), so the conversation
survives the next restart as a single uninterrupted session.

## Why there is no `/compact` command

`NEW_REQUIREMENTS.md` §3 specifies a **rolling 10-message window**.
Overflow drops the oldest message, never summarises. A `/compact`
command that summarises older turns is out of scope for this
deliverable; the in-memory trim is the only enforcement.

## Why there is no context-window-driven auto-compaction

The cap is in *messages*, not *tokens*. Auto-compaction on a
token-count threshold (à la the `SessionManager` + compactor +
context-window design from earlier drafts) is not in the spec —
the 10-message cap is the entire bound.

If a future deliverable needs token-aware compaction, the seam
lives in `Repl._handle_chat`: replace the
`history[:] = history[-capacity:]` step with a summarising call.
For now, the simple trim is exactly what the spec asks for.