# Simple CLI code assistant with RAG

A lightweight Python CLI coding assistant with built-in RAG (Retrieval-Augmented
Generation). Uses an external LLM provider for chat completions, compacts your
session into a JSON file on `/learn`, and stores it in a vector database so past
errors can be retrieved automatically on the next prompt.

For the project goals, design patterns, and architectural overview, see
[`OBJECTIVES.md`](./OBJECTIVES.md). For implementation choices and tool
versions, see [`docs/development-tools.md`](./docs/development-tools.md).
For chunker configuration (`CHUNKER_STRATEGY` and how to add a new
Strategy), see [`docs/chunker-strategy.md`](./docs/chunker-strategy.md).

---

## Requirements

- **Python ≥ 3.11**
- **[`uv`](https://github.com/astral-sh/uv)** (package manager; replaces `pip` + `venv`)
- A working API key for **at least one** of the supported LLM providers —
  see [`docs/providers.md`](./docs/providers.md):
  - [NVIDIA NIM](https://build.nvidia.com/)
  - [Mistral La Plateforme](https://console.mistral.ai/)
  - [MiniMax](https://minimax.io/)
  - [Anthropic](https://console.anthropic.com/)
  - [OpenAI](https://platform.openai.com/api-keys)

> The CLI is synchronous — no Docker, no async runtime, no GPU required. The
> embedding model (`bge-small-en-v1.5`, ~130 MB) downloads on first use and
> is cached under your user cache directory.

---

## Installation (git clone, no deployment)

```bash
git clone https://github.com/SrLampi1001/simple-cli-coder-with-rag.git
cd simple-cli-coder-with-rag
uv sync
```

`uv sync` reads `pyproject.toml`, creates a `.venv` inside the project, and
installs all runtime + dev dependencies (the LLM SDKs, `fastembed`,
`sqlite-vec`, `pydantic`, `prompt_toolkit`, `pytest`, `ruff`, `mypy`, etc.).
No other setup is needed — there is no server to start and nothing to deploy.

Verify the install:

```bash
uv run coder --version      # should print the package version
uv run pytest -q            # should pass (no network required)
```

---

## Initialization

Provider keys are **not** stored in `.env` anymore — they live in the
gitignored registry file
`~/.local/share/simple-cli-coder-with-rag/providers.json`.

```bash
uv run coder                 # first run seeds providers.json with 5 entries
/providers                   # list configured providers + active one
/connect openai              # prompts for the API key and validates it
/provider openai             # activate it
```

`/connect <id>` prompts for the key (no echo), validates it with a ping
round-trip, and writes it back. `/connect <id> --no-validate` skips the
round-trip. Custom endpoints:
`/connect --new <id> --adapter <openai|anthropic> --base-url <u> --model <m>`.

Copy `.env.example` to `.env` only for the **non-provider** knobs
(chunking, vector store, retrieval, editor sandbox):

```bash
cp .env.example .env
```

### Supported providers

See [`docs/providers.md`](./docs/providers.md) for the full table (id,
adapter, base URL, default model, where to get a key).

### First-run behavior

- On the very first run the CLI writes
  `~/.local/share/simple-cli-coder-with-rag/providers.json` with five
  pre-populated providers (keys empty) and prints a one-line notice.
- If no active provider is set, the REPL still starts; chat turns print
  `No active provider. Run /connect <id> to add a key, then /provider <id>
  to activate.` until you configure one.
- At startup the embedding model (~130 MB) loads on a background thread —
  downloading on first use and cached under
  `~/.cache/simple-cli-coder-with-rag/models/`. Subsequent runs are offline;
  recall degrades to "no memories" until the model is ready.

---

## Usage

```bash
uv run coder
```

You should see the prompt:

```
>>>
```

### Chat

Type any message and press Enter. The CLI sends your message (plus the
rolling window of the last 10 user/assistant turns — 20 messages — by
default) to the LLM and prints the reply. The cap is configurable
through the `INT_HISTORY_CAP` env var (see *Session memory and saved
chats* below).

```
>>> What is 2+2?
Four.
```

Before each turn, the recall pipeline searches your past sessions for
chunks relevant to the prompt and injects the best ones into the system
prompt (see *Memory and recall (RAG)* below). Trivial prompts (≤ 20
chars and ≤ 4 words by default) skip the search entirely.

The LLM can also use file tools (`read`, `write`, `edit`), sandboxed to
`EDITOR_ROOT` — see below.

### `/learn`

`/learn` compacts the current session into a JSON document, chunks it,
embeds the chunks, and stores them in the vector store for future recall.
It runs on a background thread, so you can keep chatting while it works —
it prints `learn: done — learned N chunks` (or `learn failed: …`) when
finished. You can start a new `/learn` only after the previous one
finishes. Only the messages present when `/learn` was invoked are
included; turns added while it runs belong to a later `/learn`.

### Slash commands

| Command   | Purpose                                                |
|-----------|--------------------------------------------------------|
| `/help`   | List the registered commands.                          |
| `/exit`   | Leave the REPL (also `Ctrl-D` on an empty prompt).     |
| `/clear`  | Clear the visible screen.                              |
| `/version`| Print the package version.                             |
| `/learn`  | Compact the session into a JSON file and index it in the vector store (runs in the background). |
| `/connect <id>` | Add/validate an API key for a provider (`--no-validate` to skip the ping). |
| `/connect --new <id> --adapter <a> --base-url <u> --model <m>` | Register a custom provider. |
| `/providers` | List providers (id, adapter, base URL, model, key set?) and the active one. |
| `/provider <id>` | Activate a provider (live switch, no restart).   |
| `/memory` | Show the active conversation window (full session id, kept turns, last user/assistant). |
| `/chats`  | List saved sessions on disk by id (full 32-char id, last activity, message count). |
| `/resume <session-id>` | Resume a saved chat by id; loads its last 10 messages and continues the conversation. |
| `/new`    | Start a fresh session id (same REPL, empty history); previous session stays on disk for `/resume`. |

### One-off flags

```bash
uv run coder --version       # print version, exit
uv run coder --reset         # wipe local data dir after y/N prompt
uv run coder --help          # argparse help
```

`--reset` deletes the SQLite database and any session JSON files under
`~/.local/share/simple-cli-coder-with-rag/` (configurable via
`platformdirs.user_data_dir`). It is gated behind an interactive `y/N`
prompt that defaults to `N`, so piping `y\n` is required to automate it:

```bash
echo y | uv run coder --reset
```

---

## Configuration reference

### Session memory and saved chats

Every chat turn is appended to the on-disk transcript
`<session_id>.jsonl` under `~/.local/share/simple-cli-coder-with-rag/sessions/`,
so chats survive a restart. The REPL trims the in-memory history to
the last `INT_HISTORY_CAP` *turns* (= the last
`2 * INT_HISTORY_CAP` messages) on every turn; the full transcript
stays on disk for `/chats` and `/resume <id>` to read back.

Four slash commands drive the saved-chat flow:

* **`/memory`** — show the active window (full 32-char session id,
  kept turns, last user / assistant). The id is shown verbatim so
  you can copy-paste it straight into `/resume <id>`.
* **`/chats`** — list every saved session on disk (full 32-char
  id, last activity, message count), sorted by most recently active
  first. The trailing `active: <id>` line is the session the REPL
  is currently writing to.
* **`/resume <session-id>`** — load the last 10 messages of a
  saved session into the active context and continue. New messages
  you type after `/resume` are appended to the same `<id>.jsonl`,
  so the conversation continues as if it had never been paused.
  `/resume` is a synchronous load-from-disk — no LLM call, no
  compactor round-trip, no blocking pause.
* **`/new`** — start a fresh session id (same REPL, empty
  history). The previous session stays on disk for `/resume` to
  read back at any point.

See [`docs/session-memory.md`](./docs/session-memory.md) for the
full on-disk layout, the recovery flow after a restart, and the
failure-mode catalogue.

### Memory and recall (RAG)

`/learn` turns past sessions into searchable memory:

```
session JSON → compact (LLM) → chunks → embeddings → vector store
```

On every chat turn, `RecallCoordinator` embeds your prompt, queries the
vector store, drops trivial prompts (gate), and keeps only chunks above the
similarity threshold. The hits are prepended to the system prompt so the LLM
can reference your past work. Retrieval is wrapped in a timeout
(`RETRIEVAL_TIMEOUT_SECONDS`, default 1.5s) and any failure degrades to
"no memories" — a slow or broken store never blocks your prompt.

### File tools

The chat model can call `read` / `write` / `edit` tool calls, executed by a
`SandboxedFileEditor` confined to `EDITOR_ROOT` (the current directory by
default). Paths escaping the sandbox are rejected. `EDITOR_MAX_TOOL_ROUNDS`
(default 1) caps how many tool-use rounds a single turn may take.

### Settings

All settings live in `src/simple_cli_coder_with_rag/infrastructure/settings.py`
and are loaded from environment / `.env` via `pydantic-settings`. The most
useful knobs:

| Variable                  | Default                                 | Purpose                                                       |
|---------------------------|-----------------------------------------|---------------------------------------------------------------|
| `CHUNKER_STRATEGY`        | `fixed`                                 | `fixed` (sliding window) or `semantic` (one chunk per record).|
| `VECTOR_STORE`            | `sqlite_vec`                            | `sqlite_vec` (persistent) or `brute_force` (in-memory).       |
| `DB_PATH`                 | *(empty)*                               | Override the sqlite-vec DB location.                          |
| `EMBEDDING_MODEL`         | `BAAI/bge-small-en-v1.5`                | fastembed model used for query/passage embeddings.            |
| `EMBEDDING_LOCAL_FILES_ONLY` | `1`                                  | Skip the HF network check when the model is cached.           |
| `RETRIEVAL_TIMEOUT_SECONDS` | `1.5`                                 | Max seconds for a single retrieval before "no memories".      |
| `RECALL_TOP_K`            | `3`                                     | Max chunks injected per prompt.                               |
| `RECALL_SIMILARITY_THRESHOLD` | `0.5`                              | Min cosine similarity for a recalled chunk to be injected.    |
| `TRIVIAL_GATE_MAX_CHARS`  | `20`                                    | Trivial-gate char bound (skip recall at or below).            |
| `TRIVIAL_GATE_MAX_WORDS`  | `4`                                     | Trivial-gate word bound (skip recall at or below).            |
| `EDITOR_ROOT`             | *(cwd at startup)*                      | Sandbox root for the LLM's file tools.                        |
| `EDITOR_MAX_TOOL_ROUNDS`  | `1`                                     | Max tool-use rounds per chat turn.                            |
| `INT_HISTORY_CAP`         | `10`                                    | Conversation-window cap, in user/assistant *turns* (one turn = two messages). Values outside `[1, 100]` are rejected. |

> Provider keys live in `providers.json` and are wrapped in pydantic
> `SecretStr`, so `repr` / `str` / `model_dump_json()` mask them. Logs are
> file-only (under `~/.local/share/simple-cli-coder-with-rag/log/`) so
> keys never end up in stdout/stderr while `prompt_toolkit` owns the
> screen.

---

## Project layout

```
src/simple_cli_coder_with_rag/
├── application/      # KnowledgeService facade (chat, learn, recall)
├── cli.py            # Composition root
├── domain/           # LLMClient Protocol, messages, errors
├── infrastructure/   # Settings, adapters, local paths, logging
└── presentation/     # REPL, command registry, slash commands

agent-development/    # Implementation plan (one folder per deliverable)
docs/                 # Tooling choices and rationale
tests/                # Mirrors src/ layout
```

---

## Development

```bash
uv sync                       # install everything
uv run pytest -q              # run the test suite (no network)
uv run ruff check .           # lint
uv run ruff format --check .  # format check
uv run mypy src               # type check
uv run lint-imports           # architectural boundaries
pre-commit run --all-files    # run everything pre-commit would run
```

The gate above is the same one every deliverable in `agent-development/`
must pass before it can be marked done.

---

## Helpers

### Building `coding-assitance/prompts.jsonl`

The `coding-assitance/prompts.jsonl` file is built from the OpenCode
session exports under `coding-assitance/json-sessions/`. The script reads
each `*.json` session, extracts every **user prompt** (messages with
`type: "user"`), and writes one JSON line per prompt into `prompts.jsonl`.
Assistant replies (`type: "assistant"`) and idle markers (`type: "idle"`)
are skipped, so the file contains only what was actually sent to the AI.

Each line wraps the original user message with session-level context
extracted from the parent file's `info` block:

```json
{
  "session_id":    "ses_…",
  "session_title": "…",
  "agent":         "build",
  "model":         {"id": "…", "providerID": "…", "variant": "…"},
  "source_file":   "session-<uuid>.json",
  "message": {
    "id":    "msg_…",
    "type":  "user",
    "time":  {"created": <epoch_ms>},
    "text":  "<prompt body>",
    "files": [...]
  }
}
```

The prompt body lives at `message.text`; referenced attachments (file
mentions / inline data) live at `message.files`.

Run from the project root:

```bash
uv run python scripts/prompts_jsonl.py
```

Both paths default to the locations above and can be overridden:

```bash
uv run python scripts/prompts_jsonl.py \
    --source-dir coding-assitance/json-sessions \
    --output    coding-assitance/prompts.jsonl
```

The script prints how many user prompts were written on success and
exits with status `0`. It exits `2` if the source directory is missing
and `1` with a warning if no user prompts are found (the output is still
created, empty, in that case).

---

## License

TBD.
