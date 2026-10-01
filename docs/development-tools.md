# Development Tools

This document lists and justifies every tool the dev needs to build, run, and
ship **Simple CLI code assistant with RAG** correctly. The choices are
aligned with the layered modular monolith architecture and the design
patterns defined in `README.md` (Command, Facade, Strategy, Decorator,
Adapter).

The guiding principle is **lightweight**: no Docker, no async stack, no
external services, no heavy ML framework. A single `pip`/`uv` install, a
single SQLite file, and one local embedding model in a background thread.

> Required items ship in `pyproject.toml` as default dependencies.
> Optional items live behind Strategy boundaries, pulled in only by the
> extras that need them (e.g. `[remote-embedder]`).

---

## 1. Pre-flight: maturity check for the two fast-moving deps

| Library | Latest stable | Released | License | Notes |
|---|---|---|---|---|
| **`fastembed`** | `0.8.1` | Sep 22 2026 | Apache-2.0 | Backed by Qdrant, 2 maintainers, regular releases. ONNX runtime, no PyTorch. |
| **`sqlite-vec`** | `0.1.9` | Mar 31 2026 | MIT / Apache-2.0 | Single maintainer, homepage field unfilled on PyPI. Small wheels, vector search works. **Risk to track:** bus-factor of 1 — pin the exact version in `uv.lock` and re-check before any bump. |

> ⚠️ Both libraries move fast. Re-verify the version and release date on
> PyPI **immediately before pinning**. The numbers above were correct at
> the time of writing (Oct 1 2026) but should not be trusted verbatim.

---

## 2. Runtime & project tooling

| Tool | Version | Why |
|---|---|---|
| **Python** | `>=3.11` | Modern type syntax (`Self`, `Literal`, `tomllib`), perf gains. Required by `fastembed` (`>=3.10`). |
| **`uv`** | latest | Package manager + virtualenvs + lockfile. Replaces `pip`/`pyenv`/`pip-tools`. Deterministic `uv.lock` is the install contract. |
| **Git** | latest | Version control; baseline. |

---

## 3. Code quality

| Tool | Scope | Why |
|---|---|---|
| **`ruff`** | Lint + format + import sort + upgrade | One binary replaces `flake8`, `isort`, `pyupgrade`, `black`. |
| **`mypy`** | Static type checking (relaxed at the edges, strict in core) | The architecture relies on Facade ↔ Strategy ↔ Adapter boundaries. We do not enable `--strict` globally because two untyped third-party libs would force a sea of overrides. Strict mode is scoped to the core package only. |
| **`import-linter`** | Architectural boundaries | Enforces layering contracts that `ruff` cannot — e.g. *presentation may import infrastructure, never the reverse*. |
| **`pre-commit`** | Git hook runner | Runs `ruff` + `mypy` + `import-linter` on every commit. |

### Corrected `pyproject.toml`

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "N", "SIM", "RUF"]

[tool.mypy]
python_version = "3.11"
check_untyped_defs = true

# Per-module overrides. ignore_missing_imports is a boolean (not a list).
# anthropic ships types, so it is NOT overridden.
[[tool.mypy.overrides]]
module = "fastembed"
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = "sqlite_vec"
ignore_missing_imports = true

# Strict mode applies only to our own code.
[[tool.mypy.overrides]]
module = "simple_cli_coder_with_rag.*"
disallow_untyped_defs = true
```

### Corrected `import-linter` contract

In a `layers` contract, **upper layers may import lower layers**, never
the reverse. Infrastructure (adapters) must be able to import the
Protocols/entities it implements — so infrastructure sits **above**
domain, not below it. The composition root (where concrete classes are
wired) lives in the presentation layer.

```ini
[importlinter]
root_package = simple_cli_coder_with_rag

[importlinter:contract:layered-architecture]
type = layers
layers =
    simple_cli_coder_with_rag.presentation
    simple_cli_coder_with_rag.infrastructure
    simple_cli_coder_with_rag.application
    simple_cli_coder_with_rag.domain
```

Allowed imports:

- `presentation` → `infrastructure`, `application`, `domain`
- `infrastructure` → `application`, `domain`
- `application` → `domain`
- `domain` → *(nothing)*

---

## 4. Data layer: vector store + paths

**No Docker. No server. One file.**

### Storage layout (via `platformdirs`)

| What | Path |
|---|---|
| Config | `~/.config/simple-cli-coder-with-rag/config.toml` |
| DB + vectors + metadata | `~/.local/share/simple-cli-coder-with-rag/db.sqlite` |
| Sessions | `~/.local/share/simple-cli-coder-with-rag/sessions/` |
| Embedding model cache | `~/.cache/simple-cli-coder-with-rag/models/` |
| Log file | `~/.local/share/simple-cli-coder-with-rag/log/app.log` |

### sqlite-vec schema

`vec0` defaults to **L2** distance. We want cosine, so declare it
explicitly. Long chunk text must be an **auxiliary** column (`+` prefix);
plain columns are metadata for filtering and have size restrictions that
will fail or misbehave on long passages.

```sql
-- Auxiliary columns (+) are returned with hits but not searched.
-- Plain columns are metadata for filtering.
-- distance_metric=cosine overrides the L2 default.
CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING vec0(
    embedding float[384] distance_metric=cosine,
    +text      TEXT,
    session_id TEXT,
    created_at INTEGER
);
```

### Required startup check

`sqlite3.Connection.enable_load_extension` is **not available on every
Python build** — notably some macOS and pyinstaller / pyenv builds ship
SQLite without it, and `sqlite-vec` cannot load without it. We detect
this on startup:

```python
conn = sqlite3.connect(db_path)
try:
    conn.enable_load_extension(True)
    conn.load_extension("vec0")
except (AttributeError, sqlite3.NotSupportedError, sqlite3.OperationalError) as exc:
    # AttributeError:     method is NULL (SQLite built with SQLITE_OMIT_LOAD_EXTENSION)
    # NotSupportedError:  method exists but disabled on this build
    # OperationalError:   method exists but raises on call
    raise RuntimeError(
        "This Python build does not support sqlite3 extension loading, "
        "so sqlite-vec cannot be used. Install CPython from python.org "
        "or a build with --enable-loadable-sqlite-extensions. "
        "Alternatively, set VECTOR_STORE=brute_force to use the "
        "numpy fallback."
    ) from exc
```

### Fallback `VectorStore`

Behind the same `VectorStore` Protocol we ship a `NumpyBruteForceStore`:
list of `(vector, chunk)` tuples, cosine similarity in Python. It is the
**fallback only** — activated when the startup check above fails or when
the user explicitly opts in (e.g. on a locked-down machine). Fine for
the few-hundred-chunks corpus expected during first delivery.

```python
class VectorStore(Protocol):
    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None: ...
    def query(self, vector: list[float], top_k: int) -> list[Chunk]: ...
```

### `/learn` idempotency

Re-running `/learn` on the same session would otherwise duplicate rows
(and inflate cosine distances by ranking the same chunk repeatedly).
The upsert is **delete-then-insert by `session_id`**:

```python
with conn:
        conn.execute("DELETE FROM chunks WHERE session_id = ?", (session_id,))
        conn.executemany(
            "INSERT INTO chunks(embedding, text, session_id, created_at) VALUES (?, ?, ?, ?)",
            rows,
        )
```

### SQLite thread safety

Python's `sqlite3` raises if a connection opened on the main thread is
used from a worker thread. Our retrieval runs on a
`ThreadPoolExecutor` (§9), so we have two options, both valid:

- **Recommended:** open the connection *inside the worker*. Each
  retrieval opens one short-lived connection. Zero shared mutable state,
  no locks needed.
- Alternative: `check_same_thread=False` plus a `threading.Lock` around
  every read/write. Less code, but still single-threaded under the hood.

---

## 5. Embedding layer

| Mode | Library | Model | Why |
|---|---|---|---|
| **Local (default)** | **`fastembed`** | `BAAI/bge-small-en-v1.5` | ONNX-based, no PyTorch. Same model the README targeted. 384-dim, fast on CPU. |
| **Remote (optional)** | `httpx` | Any OpenAI-compatible endpoint | Pulled in only with the `[remote-embedder]` extra. `tenacity` retries live here too. |

### Cache and first run

`fastembed` defaults to a temp cache directory that the OS may wipe,
forcing a re-download. We point it at a `platformdirs` user-cache path
so the model survives reboots and reinstalls.

```python
from pathlib import Path
from platformdirs import user_cache_dir
from fastembed import TextEmbedding

cache = Path(user_cache_dir("simple-cli-coder-with-rag")) / "models"
model = TextEmbedding(
    model_name="BAAI/bge-small-en-v1.5",
    cache_dir=str(cache),
)
```

**First run UX.** The first invocation downloads the model (~130 MB).
The REPL prints a one-line message: `downloading embedding model (one
time only)…`. While the model is still loading, retrieval returns
"no memories" without blocking.

**Subsequent runs hit HuggingFace even when the model is cached.**
`fastembed` still calls the HuggingFace API on every `TextEmbedding()`
init to check the repo, even with `cache_dir` set. To make subsequent
runs truly offline, either:

- pass `local_files_only=True` to `TextEmbedding(...)`, or
- set the env var `HF_HUB_OFFLINE=1` before constructing the model.

```python
model = TextEmbedding(
    model_name="BAAI/bge-small-en-v1.5",
    cache_dir=str(cache),
    local_files_only=True,   # skip the HF network check
)
```

**fastembed 0.8.1 cache naming gotcha.** From the 0.8.1 release notes:
the default `BAAI/bge-small-en-v1.5` now resolves to
`Qdrant/bge-small-en-v1.5-onnx-Q` for download, and cache dirs follow
the repo ID casing. On case-sensitive filesystems (Linux) the previous
`models--BAAI--bge-small-en-v1.5` cache from 0.7.x will not be reused
and the model will re-download once. Safest move when upgrading across
a minor version is to delete the old cache.

### Two-method embedder interface

BGE models retrieve better when **queries** get an instruction prefix
and **passages** do not. `fastembed` exposes `query_embed` /
`passage_embed` and bakes in the prefix internally. The project must
honour this — retrieval quality is its whole reason for existing.

```python
class Embedder(Protocol):
    def embed_query(self, text: str) -> list[float]: ...
    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...
```

The retriever calls `embed_query` for the user's prompt and
`embed_passages` during `/learn`.

### Known limitation (first delivery)

`bge-small-en-v1.5` is **English-only**. Non-English chunks will embed
into nonsense space and retrieval will silently degrade. This is an
accepted limitation for v1; we swap the model behind the same `Embedder`
Protocol when multilingual support is needed.

---

## 6. LLM & the `/learn` compaction pipeline

| Tool | Role | Why |
|---|---|---|
| **`anthropic`** SDK | LLM calls (Adapter pattern) | Wrapped behind the project's `LLMClient` interface. The SDK already ships with `max_retries` + exponential backoff, so no extra retry library is needed. |
| **`pydantic`** | Schemas for compaction output + chunk metadata + settings | `/learn` compaction calls the LLM with a structured-output prompt and validates the JSON through a `CompactedSession` model. Cheap, parseable, type-checked. |
| **`pydantic-settings`** | Env-driven config (`ANTHROPIC_API_KEY`, `COMPACTOR_MODEL`, paths) | Reads `.env` natively — no separate `python-dotenv` needed. |

### Compaction model is a setting, not a constant

```toml
[project]
# .env (example)
COMPACTOR_MODEL=claude-haiku-4-5          # cheap, for /learn compaction
CHAT_MODEL=claude-sonnet-4-5              # strong, for the actual chat step
```

Default for `COMPACTOR_MODEL` is a current Haiku-class model; users
override via env var without code changes.

### Long-session strategy

Big sessions will exceed the compactor's context window and rack up
cost. Pipeline for `/learn` when the session is large:

1. Split the session into time-based or token-budgeted **segments**.
2. Compact each segment independently (one Haiku call per segment).
3. Merge the structured results in-process (dedupe on `error_signature`).
4. Then chunk → embed → store as usual.

This stays a **plain data pipeline** (sequence of pure-function stages);
it is **not** Chain of Responsibility — no stage decides whether to
"handle or pass along"; each stage transforms its input.

---

## 7. CLI surface

The product is an **interactive REPL**. Everything else is in service of
it.

| Tool | Why |
|---|---|
| **`prompt_toolkit`** | REPL with history, multi-line editing, slash-command autocompletion. Pairs naturally with the **Command** registry — the loop parses `/token` and dispatches. No async ceremony. |
| **stdlib `argparse`** | One tiny entry point: `coder [--version] [--reset]`. Just enough for `--help` and a couple of bootstrap flags. |

> `typer` is **not** pulled in. It would transitively install `rich` and
> ~10 more packages for a one-flag entry point that `argparse` already
> covers. The REPL is the product, not a sub-command.

Recall is **not** a command. It runs automatically before every prompt
when the embedder is warm; if the warm-up thread is still loading, the
retrieval simply returns no memories and logs at `DEBUG`.

---

## 8. App glue & resilience

| Library | Purpose | Notes |
|---|---|---|
| **`pydantic`** | Schemas for compacted sessions, chunks, configs. | Required by `/learn`. |
| **`pydantic-settings`** | Settings via env / `.env`. | Replaces `python-dotenv` — reads `.env` natively. |
| **`loguru`** | Structured logging, **to file** under platformdirs `user_log_dir`. | Routed to `~/.local/share/simple-cli-coder-with-rag/log/app.log`. Stdlib `logging` would work just as well — pick one and stay consistent. |
| **`tenacity`** | Retries on the **remote embedder only**. | Declared in the `[remote-embedder]` extra. Never used on the local embedder, the LLM, or the SQLite store. |

### Logging doesn't go to the terminal

Anything written to stdout/stderr while `prompt_toolkit` owns the screen
will corrupt the prompt. Logs are file-only by default. If you want
tail-like visibility during development, run `tail -f` on the log file
in a second terminal.

### Things deliberately NOT pulled in

- `httpx` — only needed for the optional remote embedder; declared in
  the `[remote-embedder]` extra so the default install stays slim.
- `numpy` — comes transitively with `fastembed`. No direct import.
- `python-dotenv` — superseded by `pydantic-settings`.
- `rich` — only useful for terminal pretty-printing we don't ship yet.
- `openai` SDK — `httpx` against an OpenAI-compatible endpoint is one
  short POST; the full SDK is not worth its install size.

---

## 9. Concurrency model: sync + `ThreadPoolExecutor`

The README suggests running retrieval concurrently while the rest of the
request is being prepared. The app is **synchronous** — no `asyncio`,
no async DB driver, no async tests.

| Concern | Decision |
|---|---|
| Concurrent retrieval | `concurrent.futures.ThreadPoolExecutor(max_workers=2)` |
| Worker thread lifetime | Default non-daemon. We call `executor.shutdown(wait=False, cancel_futures=True)` on REPL exit so Ctrl-D doesn't hang briefly waiting for in-flight retrieval. |
| Timeout fallback | `future.result(timeout=…)` — note: this **stops waiting, it does not cancel** the running work. The fallback is "no memories returned this turn". |
| Embedder warm-up | A separate `threading.Thread(daemon=True)` started at boot. Daemon, so a slow first-time download never delays process exit. |

The single executor replaces `psycopg[binary,pool]` (no async driver
needed), `pytest-asyncio`, and ruff's `ASYNC` rule set. Less ceremony,
same latency win.

---

## 10. Distribution & install story

The CLI installs with **one** command. No Docker, no `git clone`, no
`pip install -r`.

```toml
[project.scripts]
coder = "simple_cli_coder_with_rag.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

End-user install:

```bash
uv tool install simple-cli-coder-with-rag
coder
```

Optional extras:

```bash
# Remote embedder pulls httpx + tenacity
uv tool install "simple-cli-coder-with-rag[remote-embedder]"
```

---

## 11. Testing

| Tool | Why |
|---|---|
| **`pytest`** | Standard, plugin ecosystem. |
| **`pytest-cov`** | Coverage gate; useful for tracking untested Strategy branches. |
| **`pytest-mock`** | Clean mocking of `LLMClient` and `Embedder` interfaces — exactly the seams the Adapter + Strategy patterns expose. |

`pytest-asyncio` is **not** used (sync app). Tests mirror source layout in
a single `tests/` tree.

---

## 12. Decorator pattern: what survives and what doesn't

The README suggested `Retriever → CachedRetriever → TimeoutRetriever`.
After pressure-testing:

- **`TimeoutRetriever`** — kept. Real value: bounds worst-case latency on
  retrieval so RAG never blocks the user. Uses `future.result(timeout=…)`.
- **`CachedRetriever`** — **dropped for v1**. User requests rarely repeat
  verbatim, so hit rates are low; the real cost is the query embedding
  (tens of ms) and the SQLite lookup, both already cheap. Add the cache
  behind the same Decorator wrapper later if profiling shows it helps.

The Decorator wrappers above still compose around a `Retriever`
Protocol, so swapping in a cache later is a one-line change at the
composition root.

---

## 13. Summary — required vs optional

### Required (default `pip install …`)

- [ ] Python `>=3.11`
- [ ] `uv`
- [ ] `ruff`
- [ ] `mypy` (relaxed at edges, strict in core)
- [ ] `import-linter`
- [ ] `pre-commit install`
- [ ] `fastembed` + `bge-small-en-v1.5`
- [ ] `sqlite-vec`
- [ ] `sqlite3` (stdlib)
- [ ] `platformdirs`
- [ ] `anthropic` SDK
- [ ] `pydantic`, `pydantic-settings`
- [ ] `loguru` (or stdlib `logging`)
- [ ] `prompt_toolkit`
- [ ] `hatchling` (build backend)
- [ ] `pytest`, `pytest-cov`, `pytest-mock`

### Optional (selected via extras / Strategy)

- [ ] `[remote-embedder]` extra → `httpx` + `tenacity`
- [ ] `NumpyBruteForceStore` fallback (auto-activated when `enable_load_extension` is missing, or via explicit opt-in)
- [ ] Semantic chunker (Strategy alternative to default fixed-size)

### Explicitly not used

- ❌ Docker / docker compose
- ❌ `psycopg` / `asyncpg` (we use SQLite)
- ❌ `pytest-asyncio`, ruff `ASYNC` rules (sync app)
- ❌ `sentence-transformers` (PyTorch dependency)
- ❌ `python-dotenv` (pydantic-settings reads `.env`)
- ❌ `numpy` direct import (transitive via fastembed)
- ❌ `rich`, `typer` (REPL is the product; no pretty-printing in v1)
- ❌ `pgvector` (replaced by sqlite-vec)
- ❌ `openai` SDK (`httpx` against OpenAI-compatible endpoints is enough)

---

## 14. How the choices map to the README's design patterns

| Pattern | Tool / decision that makes it easy to honor |
|---|---|
| **Command** | `prompt_toolkit` REPL + plain `dict[str, Command]` registry; `/learn`, `/help`, `/clear`, `/exit` are the first four. |
| **Facade** | `pydantic` models + `pydantic-settings` give `KnowledgeService.learn/recall` stable, validated signatures. |
| **Strategy** (chunker / embedder / store / remote-embedder) | `fastembed` (embedder), `sqlite-vec` (store), `NumpyBruteForceStore` (fallback), remote embedder via `httpx` — each behind a `Protocol`. |
| **Decorator** (timeout around the retriever) | `TimeoutRetriever` wraps the base retriever and uses `future.result(timeout=…)` from the `ThreadPoolExecutor`. Caching is deferred behind the same pattern. **Not** tenacity — retries on a local SQLite lookup make no sense. |
| **Adapter** (Anthropic SDK) | Internal `LLMClient` interface; the SDK is the only adapter implementation. Built-in `max_retries` handles network retries — no extra library. |

Any tool that would *leak* into the application layer (e.g., a vendor
SDK type appearing in a Facade signature) violates the architecture and
should be rejected.