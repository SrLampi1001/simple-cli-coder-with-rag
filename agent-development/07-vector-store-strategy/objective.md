# DO-07 — Vector store strategy (sqlite-vec + numpy fallback)

## Goal

A `VectorStore` Protocol with two implementations: `SqliteVecStore` (default, uses `sqlite-vec`) and `NumpyBruteForceStore` (fallback, used when `enable_load_extension` is unavailable). The store takes chunks + vectors, persists them, and supports cosine-similarity top-k queries. The `/learn` pipeline now ends at the store. This completes the fourth README bullet: *"The JSON file is stored into a vectorial database."*

## Source of truth

- `README.md` — "The JSON file is stored into a vectorial database" + Strategy pattern (vector store).
- `docs/development-tools.md` §4 (sqlite-vec schema, cosine metric, `+text` aux column, idempotent upsert, startup check, thread safety, fallback).

## Acceptance criteria

- [ ] `src/simple_cli_coder_with_rag/domain/vector_store.py` defines:
  ```python
  class VectorStore(Protocol):
      def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None: ...
      def query(self, vector: list[float], top_k: int) -> list[tuple[Chunk, float]]: ...
  ```
- [ ] `src/simple_cli_coder_with_rag/infrastructure/vector_stores/sqlite_vec_store.py` defines `class SqliteVecStore`:
  - Schema exactly as dev-tools.md §4: `CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING vec0(embedding float[384] distance_metric=cosine, +text TEXT, session_id TEXT, created_at INTEGER)`.
  - `__init__(self, db_path: Path) -> None` runs the startup check (see step 4). On failure, raises a `VectorStoreBackendUnavailable` (defined in `domain/vector_store.py`) with the message from dev-tools.md §4.
  - `upsert` is **delete-then-insert by `session_id`** (idempotency, per dev-tools.md §4).
  - Each `query` opens a fresh connection (per dev-tools.md §4 "open the connection inside the worker").
  - Returns `list[tuple[Chunk, float]]` where the float is the cosine **similarity** (1 − distance), so larger is better.
- [ ] `src/simple_cli_coder_with_rag/infrastructure/vector_stores/numpy_brute_force_store.py` defines `class NumpyBruteForceStore`:
  - In-memory list of `(vector, chunk)` tuples. `query` does cosine similarity in numpy. Activated only when `SqliteVecStore` raises `VectorStoreBackendUnavailable` or when `Settings.vector_store == "brute_force"`. `upsert` is **delete-then-insert by `session_id`** (same idempotency contract as `SqliteVecStore`), and `query` skips zero-norm rows to avoid division-by-zero (`NaN` similarities).
- [ ] `Settings` gains:
  - `vector_store: Literal["sqlite_vec", "brute_force"] = "sqlite_vec"`
  - `db_path: Path | None = None` (default `None` → `LocalPaths.data_dir() / "db.sqlite"` from DO-01).
- [ ] The composition root tries `SqliteVecStore(db_path)`; on `VectorStoreBackendUnavailable`, falls back to `NumpyBruteForceStore()` and logs at INFO. The `Settings.vector_store == "brute_force"` short-circuits the fallback decision.
- [ ] `KnowledgeService.learn` is updated to call `self.vector_store.upsert(chunks, vectors)`.
- [ ] The full gate exits 0. Tests patch `sqlite_vec` to avoid loading a real extension.

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

- The retriever (DO-08).
- Recall in chat (DO-09).
- Long-session chunking (dev-tools.md §4 — handled later by re-`/learn`).

## Depends on

- DO-04, DO-05, DO-06.

## Blocks

- DO-08, DO-09.
