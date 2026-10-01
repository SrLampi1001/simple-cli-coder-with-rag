# DO-07 contracts

## Architectural

- [ ] New modules:
  - `simple_cli_coder_with_rag.domain.vector_store` (Protocol + exception)
  - `simple_cli_coder_with_rag.infrastructure.vector_stores.sqlite_vec_store`
  - `simple_cli_coder_with_rag.infrastructure.vector_stores.numpy_brute_force_store`
- [ ] `import-linter` reports zero violations.
- [ ] `sqlite_vec` is imported **only** in `infrastructure/vector_stores/sqlite_vec_store.py`. (Add the same `forbidden_imports` contract as in DO-06.)
- [ ] No application-layer module imports from `infrastructure.vector_stores.*`.

## Behavioral

- [ ] `SqliteVecStore(db_path)` raises `VectorStoreBackendUnavailable` with the dev-tools.md §4 message when `enable_load_extension` is `None` or raises on call.
- [ ] After a successful init, `upsert(chunks, vectors)` writes rows; `query(v, top_k)` returns up to `top_k` chunks sorted by cosine similarity descending.
- [ ] `upsert` is idempotent by `session_id`: calling it twice for the same session leaves exactly one set of rows for that session.
- [ ] The cosine similarity returned by `query` is in `[-1.0, 1.0]` (clamped on floating-point error).
- [ ] `NumpyBruteForceStore` returns the same chunks/vectors that were `upsert`ed; cosine similarity is computed correctly (verified by a known-vector fixture).
- [ ] `NumpyBruteForceStore.upsert` is idempotent by `session_id` (same contract as `SqliteVecStore`).
- [ ] `NumpyBruteForceStore.query` skips rows whose stored vector has zero norm and never returns a `NaN` similarity (zero-norm would otherwise yield `NaN` from `dot / (||a|| * ||b||)`).
- [ ] The composition root's fallback path activates when `SqliteVecStore(...)` raises; a single INFO log line is written; the app continues with `NumpyBruteForceStore`.

## Schema

- [ ] `class VectorStore(Protocol)`:
  - `upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None`
  - `query(self, vector: list[float], top_k: int) -> list[tuple[Chunk, float]]`
- [ ] `class VectorStoreBackendUnavailable(RuntimeError)` in `domain/vector_store.py`.
- [ ] `class SqliteVecStore`:
  - `__init__(self, db_path: Path) -> None`
  - `upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None`
  - `query(self, vector: list[float], top_k: int) -> list[tuple[Chunk, float]]`
- [ ] `class NumpyBruteForceStore`:
  - `__init__(self) -> None`
  - `upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None`
  - `query(self, vector: list[float], top_k: int) -> list[tuple[Chunk, float]]`
- [ ] `Settings.vector_store: Literal["sqlite_vec", "brute_force"] = "sqlite_vec"`.
- [ ] `Settings.db_path: Path | None = None`; resolution: `LocalPaths.data_dir() / "db.sqlite"` (the helper from DO-01, which delegates to `platformdirs.user_data_dir("simple-cli-coder-with-rag")`). The vector store module does **not** hard-code the path.
- [ ] `KnowledgeService.learn` ends with `vector_store.upsert(chunks, vectors)`.
- [ ] `KnowledgeService` constructor takes `embedder: Embedder` and `vector_store: VectorStore`.
