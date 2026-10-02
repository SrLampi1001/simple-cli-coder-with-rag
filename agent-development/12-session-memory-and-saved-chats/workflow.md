# DO-12 workflow

## Subagent delegation

**One subagent.** Earlier drafts split DO-12 into two subagents
(Subagent A: `CharEstimateTokenCounter` + `Compactor.summarize` +
DO-11 schema patch; Subagent C: `SessionManager` + Commands +
docs). Both halves existed to deliver a context-window-driven
auto-compaction pipeline that is **not** in `NEW_REQUIREMENTS.md`
§3 — that design is deliberate mis-planning.

Removing it collapses the work into a single subagent that owns:

- `infrastructure/settings.py` (one new field:
  `int_history_cap`).
- `application/session_store.py` (one new method:
  `list_sessions`).
- `presentation/repl.py` (`_handle_chat` trim rewrite +
  persistence hook).
- `presentation/commands/__init__.py` (`AppState.settings` field
  added; `history_cap` field removed).
- Three new commands: `presentation/commands/memory.py`,
  `presentation/commands/chats.py`,
  `presentation/commands/resume.py`.
- `cli.py` (register commands; wire `settings` into
  `AppState`).
- `README.md` and `.env.example` updates.

### Context passed to the subagent

- `agent-development/README.md` (master).
- The four files of this deliverable.
- `docs/development-tools.md` §6, §8.
- `application/session_store.py` (the class the new method is
  added to).
- `presentation/repl.py` (the file the trim + persistence live
  in).
- `presentation/commands/__init__.py` (`AppState` definition).
- `presentation/commands/{clear,exit,help,version,provider,learn}.py`
  (reference implementations of `Command`).
- `cli.py` (the composition root).
- `README.md` and `.env.example` (to be edited).
- Nothing in `11-provider-registry-and-sdk-integrations/` — DO-11
  stays untouched by this deliverable.
- Nothing in `infrastructure/llm/`, `application/compactor.py`,
  or `application/knowledge_service.py` — no LLM-facing changes
  are needed.

## Web-search verification (before pinning)

This deliverable does **not** add new vendor SDKs or model
defaults. No web search is required.

## Steps

1. **Pre-flight.** `git status` clean.
2. **Write the test files** from `tests.md` first. Confirm they
   fail (`uv run pytest -q` reports collection errors for
   `MemoryCommand` / `ChatsCommand` / `ResumeCommand`,
   `SessionStore.list_sessions`, `Settings.int_history_cap`,
   and the renamed `test_repl_caps_history_at_10_turns`).
3. **Update `Settings`** — add `int_history_cap: int = 10`
   with `INT_HISTORY_CAP` env var and `ge=1, le=100` validator.
4. **Update `SessionStore`** — add `list_sessions()` returning
   `list[tuple[str, float, int]]`. Implementation is
   `os.scandir` + `stat().st_mtime` + `len(file.readlines())`.
   No JSON parsing, no body reads.
5. **Update `AppState`** — remove `history_cap`; add
   `settings: Settings | None = None`.
6. **Update `Repl._handle_chat`**:
   - Read the cap from `app_state.settings.int_history_cap`
     (fallback `10` when `settings is None`).
   - Compute `cap_in_messages = 2 * int_history_cap`.
   - Before the LLM call, snapshot the persisted transcript via
     `session_store.read(session_id)` and build a `seen` set.
   - After appending the user turn + assistant reply, persist
     any turn not in `seen` (in order) via
     `session_store.append(session_id, msg)`.
   - Trim `history[:] = history[-cap_in_messages:]` after
     persistence.
7. **Create the three new commands** under
   `presentation/commands/`:
   - `memory.py` — `MemoryCommand`.
   - `chats.py` — `ChatsCommand`.
   - `resume.py` — `ResumeCommand`.
8. **Update `cli.py`** — register the three new commands in
   `_build_registry()`. In `_bootstrap_app_state()`, pass
   `settings=settings` into the `AppState(...)` constructor.
9. **Update docs** — `README.md` gains the three slash
   commands and the new "Session memory and saved chats"
   section. `.env.example` gains `INT_HISTORY_CAP=10` with a
   one-line comment.
10. **Run the gate.** All exit 0.
11. **Verify behavior:**
    - `uv run coder` starts; type 12 chat lines; assert the
      in-memory history stops at the 20-message cap
      (`int_history_cap=10` turns × 2).
    - On every chat turn the `<id>.jsonl` file in
      `~/.local/share/simple-cli-coder-with-rag/sessions/`
      grows by 2 lines. Confirmed via `wc -l`.
    - `/memory` shows the active window.
    - `/chats` lists the session.
    - `/resume <id>` (run from a fresh process) restores the
      last 10 turns into the active context, sets
      `app_state.session_id = <id>`, and immediately accepts
      a new chat line that is appended to that same `<id>.jsonl`.
    - `/resume unknown` returns the friendly *"unknown
      session"* message without crashing.
12. **Commit (suggested template — adapt to actual changes):**
    - `feat(session-memory): 10-message rolling window + persistent /resume + /memory + /chats`
    - The commit body must reflect the actual changes —
      list every modified / created file and a one-line
      summary of the change in each (e.g.
      `- settings.py: int_history_cap field; - AppState.history_cap field removed; + AppState.settings field`).
13. **Post-flight.** `git status` clean.

## Failure modes

- **`int_history_cap` env var is `0` or negative** — pydantic
  Settings validator rejects it (`ge=1`). The REPL does not
  start; the user sees the pydantic validation message.
- **`int_history_cap` env var is `>100`** — pydantic Settings
  validator rejects it (`le=100`). Same as above.
- **The on-disk `.jsonl` grows unbounded across long
  sessions** — by design. The cap applies to the *active*
  window, not the on-disk transcript. The full transcript
  stays for `/chats` / `/resume` history.
- **`/resume` is called on a session whose `.jsonl` is
  corrupt or truncated** — `SessionStore.read` already
  returns whatever it can parse (defensive — empty lines
  are skipped). `/resume` loads the partial transcript and
  the user sees a slightly worse resume, not a crash.
- **`session_store.list_sessions` is called before the user
  has typed a chat line** — the session root may be empty
  (no `<id>.jsonl` files yet); returns `[]`. The Command
  prints *"No saved sessions yet."*.
- **`AppState.history_cap` references remain in unrelated
  tests** — DO-12's REPL chat-path patch updates the only
  test that pins the old `20` value
  (`test_repl_caps_history_at_10_turns`). Other tests that
  mention `history_cap` must be checked; the field is
  removed by this commit.
- **The previous draft's `SessionManager` /
  `CharEstimateTokenCounter` / `Compactor.summarize` /
  `<id>.summary.json` files leak in from a stale branch** —
  none of these files exist in DO-12. If a stale
  implementation accidentally lands, the test suite will
  fail (the `test_resume_does_not_call_llm` regression
  guard catches the mis-planning on `/resume`).

## What was deliberately **not** delivered

This deliverable ends with the cap-and-persistence design
above. The following were part of earlier drafts and are
explicitly **out of scope**:

- **Auto-compaction on a context-window threshold.** Not in
  `NEW_REQUIREMENTS.md` §3. The 10-message cap is a hard
  limit; overflow drops the oldest message, never
  summarises.
- **A `/compact` slash command.** Not in
  `NEW_REQUIREMENTS.md` §3.
- **A `SessionManager` orchestrator.** The cap +
  persistence are trivial enough that an orchestrator class
  is overkill.
- **A `CharEstimateTokenCounter` / token estimation.** The
  cap is in *messages*, not *tokens*; estimating tokens
  would conflate the requirement with the mis-planning.
- **A `Compactor.summarize` method on `Compactor`.** The
  compactor stays focused on `/learn`'s structured JSON
  output.
- **`<session_id>.summary.json` files.** No summaries are
  produced.
- **A `ProviderConfig.context_window` field.** DO-11 stays
  focused on provider wiring; the cap here is
  provider-agnostic.
- **Streaming summarisation.** Not in the spec.