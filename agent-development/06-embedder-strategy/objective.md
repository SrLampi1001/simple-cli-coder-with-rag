# DO-06 — Embedder strategy (local fastembed)

## Goal

An `Embedder` Protocol with a `FastembedEmbedder` implementation that loads `BAAI/bge-small-en-v1.5` (384-dim), caches it under `platformdirs.user_cache_dir`, supports `embed_query` (with the BGE instruction prefix via `fastembed`'s `query_embed`) and `embed_passages`, and warm-starts on a daemon thread so the first chat is not blocked. This completes the third README bullet: *"The embedding model works."*

## Source of truth

- `README.md` — "The embedding model works" + Strategy pattern (embedder).
- `docs/development-tools.md` §5 (fastembed, BGE model, cache dir, two-method interface, warm-up, first-run UX, known limitation: English-only).

## Acceptance criteria

- [ ] `src/simple_cli_coder_with_rag/domain/embedder.py` defines:
  ```python
  class Embedder(Protocol):
      def embed_query(self, text: str) -> list[float]: ...
      def embed_passages(self, texts: list[str]) -> list[list[float]]: ...
      def warmup(self) -> None: ...
      def is_ready(self) -> bool: ...
  ```
- [ ] `src/simple_cli_coder_with_rag/infrastructure/embedders/fastembed_embedder.py` defines `class FastembedEmbedder`:
  - `__init__(self, *, model_name: str = "BAAI/bge-small-en-v1.5", cache_dir: Path | None = None, local_files_only: bool = True)`.
  - On init: schedule `self._load()` on a `threading.Thread(daemon=True)`; sets `_ready = False`.
  - `warmup()` blocks until `_ready` is True (or raises a timeout if `timeout` is given).
  - `is_ready()` returns `_ready`.
  - `embed_query` returns a 384-dim `list[float]`; calls `fastembed.TextEmbedding.query_embed`.
  - `embed_passages` returns `list[list[float]]` of length `len(texts)`, each 384-dim; calls `fastembed.TextEmbedding.passage_embed`.
  - If `is_ready()` is False and `embed_query` / `embed_passages` is called, raise `EmbedderNotReady` (defined in `domain/embedder.py`).
- [ ] `src/simple_cli_coder_with_rag/infrastructure/embedders/__init__.py` exports `FastembedEmbedder`.
- [ ] `Settings` gains:
  - `embedding_model: str = "BAAI/bge-small-en-v1.5"`
  - `embedding_local_files_only: bool = True`
- [ ] `AppState` gains `embedder: Embedder | None = None`.
- [ ] The composition root builds the `FastembedEmbedder` with `cache_dir = Path(user_cache_dir("simple-cli-coder-with-rag")) / "models"` and starts the warm-up thread.
- [ ] First-run UX: the embedder prints `downloading embedding model (one time only)…` to **stderr** (this is the one allowed stderr write; it happens **before** the REPL starts) when the model file is missing on disk.
- [ ] The full gate exits 0. The `embedder` tests use `pytest-mock` to patch `fastembed.TextEmbedding`; they do not download a real model.

## Gate

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

- Remote embedder (`[remote-embedder]` extra). The Strategy makes it a one-line swap later.
- Storing embeddings (DO-07).
- Retrieval (DO-08).
- Multilingual models (English-only is the accepted v1 limitation).

## Depends on

- DO-00, DO-05.

## Blocks

- DO-07, DO-08, DO-09.
