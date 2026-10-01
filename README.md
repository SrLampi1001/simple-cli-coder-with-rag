# Simple CLI code assistant with RAG

A lightweight Python CLI coding assistant with built-in RAG (Retrieval-Augmented
Generation). Uses an external LLM provider for chat completions, compacts your
session into a JSON file on `/learn`, and stores it in a vector database so past
errors can be retrieved automatically on the next prompt.

For the project goals, design patterns, and architectural overview, see
[`OBJECTIVES.md`](./OBJECTIVES.md). For implementation choices and tool
versions, see [`docs/development-tools.md`](./docs/development-tools.md).

---

## Requirements

- **Python ≥ 3.11**
- **[`uv`](https://github.com/astral-sh/uv)** (package manager; replaces `pip` + `venv`)
- A working API key for **at least one** of the supported LLM providers:
  - [NVIDIA NIM](https://integrate.api.nvidia.com/) (`NVIDIA_API_KEY`)
  - [Mistral La Plateforme](https://console.mistral.ai/) (`MISTRAL_API_KEY`)
  - [MiniMax](https://minimax.io/) (`MINIMAX_API_KEY`)

> The CLI is synchronous — no Docker, no async runtime, no GPU required. The
> embedding model (`bge-small-en-v1.5`, ~130 MB) downloads on first use and
> is cached under your user cache directory.

---

## Installation (git clone, no deployment)

```bash
git clone https://github.com/<your-org>/simple-cli-coder-with-rag.git
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

The CLI reads three secrets from a `.env` file at the project root. Copy the
example file and fill in the key(s) you have:

```bash
cp .env.example .env
```

Then edit `.env` and set the API key for the provider you want to use. Example
minimum config:

```ini
# Pick one provider and paste its key below. The other two can stay empty.
NVIDIA_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxxxxxxxxxx
MISTRAL_API_KEY=
MINIMAX_API_KEY=

# Which provider to use at startup. One of: nvidia, mistral, minimax.
DEFAULT_PROVIDER=nvidia
```

### Provider defaults

The default model for each provider is verified to respond to chat
completions on a real account. You can override the model with the
`*_MODEL` env vars (or `CHAT_MODEL` for the REPL chat path specifically):

| Provider   | Default model                       | Also known to work                                                          |
|------------|-------------------------------------|-----------------------------------------------------------------------------|
| NVIDIA     | `meta/llama-3.2-11b-vision-instruct`| `openai/gpt-oss-20b`, `nvidia/nemotron-3-super-120b-a12b`                   |
| Mistral    | `mistral-code-latest`               | `codestral-latest`, `ministral-8b-latest`                                   |
| MiniMax    | `MiniMax-M3`                        | (Anthropic-SDK-compatible endpoint at `https://api.minimax.io/anthropic`)   |

> The earlier defaults (`meta/llama-3.1-70b-instruct`, `mistral-large-latest`)
> were deprecated/removed by their providers and now return HTTP 410 / 403.
> See [`.env.example`](./.env.example) for the full set of overrides.

### First-run behavior

- The CLI loads your `.env` automatically via `pydantic-settings`.
- If the API key for `DEFAULT_PROVIDER` is missing, `coder` prints a friendly
  error to **stderr** and exits with code `2`. The other two keys may stay
  empty.
- On the first chat turn the first time you use it after `uv sync`, the
  embedding model (~130 MB) is downloaded in the background and cached under
  `~/.cache/simple-cli-coder-with-rag/models/`. Subsequent runs are offline.

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
rolling history of the last 20 turns) to the LLM and prints the reply.

```
>>> What is 2+2?
Four.
```

### Slash commands

| Command   | Purpose                                                |
|-----------|--------------------------------------------------------|
| `/help`   | List the registered commands.                          |
| `/exit`   | Leave the REPL (also `Ctrl-D` on an empty prompt).     |
| `/clear`  | Clear the visible screen.                              |
| `/version`| Print the package version.                             |
| `/learn`  | (Coming in DO-04) Compact the session into a JSON file.|

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

All settings live in `src/simple_cli_coder_with_rag/infrastructure/settings.py`
and are loaded from environment / `.env` via `pydantic-settings`. The most
useful knobs:

| Variable                  | Default                                 | Purpose                                                       |
|---------------------------|-----------------------------------------|---------------------------------------------------------------|
| `DEFAULT_PROVIDER`        | `nvidia`                                | Which provider's adapter to wire into `AppState`.             |
| `NVIDIA_API_KEY`          | *(empty)*                               | Required when `DEFAULT_PROVIDER=nvidia`.                      |
| `MISTRAL_API_KEY`         | *(empty)*                               | Required when `DEFAULT_PROVIDER=mistral`.                     |
| `MINIMAX_API_KEY`         | *(empty)*                               | Required when `DEFAULT_PROVIDER=minimax`.                     |
| `NVIDIA_MODEL`            | `meta/llama-3.2-11b-vision-instruct`    | Model used for chat when `DEFAULT_PROVIDER=nvidia`.           |
| `MISTRAL_MODEL`           | `mistral-code-latest`                   | Model used for chat when `DEFAULT_PROVIDER=mistral`.          |
| `MINIMAX_MODEL`           | `MiniMax-M3`                            | Model used for chat when `DEFAULT_PROVIDER=minimax`.          |
| `CHAT_MODEL`              | *(empty)*                               | Overrides the per-provider default for the REPL chat path.    |
| `NVIDIA_BASE_URL`         | *(empty)*                               | Override the NVIDIA endpoint (self-hosting).                  |
| `MISTRAL_BASE_URL`        | *(empty)*                               | Override the Mistral endpoint (self-hosting).                 |
| `MINIMAX_BASE_URL`        | *(empty)*                               | Override the MiniMax endpoint (self-hosting).                 |

> `repr(Settings(...))` and `str(settings)` mask every API key. Logs are
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

## License

TBD.
