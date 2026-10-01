# DO-07 workflow

## Subagent delegation

**One subagent.** The Protocol, two implementations, settings fields, and composition-root fallback are tightly coupled. Splitting risks divergence between the schema and the implementation.

### Context passed to the subagent

- `agent-development/README.md`.
- The four files in this folder.
- `docs/development-tools.md` §4 in full.
- Nothing else.

## Web-search verification

Before pinning `sqlite-vec`:

1. `websearch "sqlite-vec pypi latest version 2026"` — confirm dev-tools.md §1.
2. `websearch "sqlite-vec cosine distance_metric 2026"` — confirm `distance_metric=cosine` is still the supported syntax (it has been stable across the 0.1.x series; a breaking change would be flagged here).

If the version has moved within the same minor, update `pyproject.toml` and add a `bump:` line to the commit body. If it has moved across a major, stop and ask the user.

## Steps

1. **Pre-flight.** `git status` clean.

2. **Write the test files** from `tests.md` first. Confirm they fail.

3. **Write `src/simple_cli_coder_with_rag/domain/vector_store.py`** with `VectorStore` Protocol and `VectorStoreBackendUnavailable`.

4. **Write `src/simple_cli_coder_with_rag/infrastructure/vector_stores/__init__.py`** (empty).

5. **Write `src/simple_cli_coder_with_rag/infrastructure/vector_stores/sqlite_vec_store.py`** with `SqliteVecStore`. Implementation notes:
   - `__init__`: try `conn.enable_load_extension(True); conn.load_extension("vec0")`. Catch `AttributeError`, `sqlite3.NotSupportedError`, `sqlite3.OperationalError` and raise `VectorStoreBackendUnavailable` with the dev-tools.md §4 message (mentioning `VECTOR_STORE=brute_force` as the workaround).
   - On success, run the `CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING vec0(...)` schema exactly as dev-tools.md §4.
   - `upsert(chunks, vectors)`: open a fresh connection, run `DELETE FROM chunks WHERE session_id = ?` for the unique `session_id`s in the input, then `executemany` the inserts. `commit()`. Close.
   - `query(vector, top_k)`: open a fresh connection, run `SELECT embedding, text, session_id, created_at FROM chunks WHERE embedding MATCH ? ORDER BY distance LIMIT ?`. For each row, compute cosine similarity as `1 - row[0]` (sqlite-vec returns L2 by default; with `distance_metric=cosine`, the returned distance is `1 - cosine_similarity`, so similarity is `1 - distance`). Hydrate a `Chunk` from the row. Return `[(chunk, similarity)]`.

6. **Write `src/simple_cli_coder_with_rag/infrastructure/vector_stores/numpy_brute_force_store.py`** with `NumpyBruteForceStore`. Implementation:
   - Store `self._items: list[tuple[np.ndarray, Chunk]]`.
   - `upsert`: extend the list.
   - `query`: stack vectors into a `np.ndarray` (compute lazily), cosine similarity = `dot(v, V) / (||v|| * ||V||)`. Sort descending, take top `k`. Return `[(chunk, float(sim)) for ...]`.
   - Do not import numpy at module level — import inside the methods. (Avoids dragging numpy into the cold-start path of the sqlite-vec default.)

7. **Add `forbidden_imports` contract** to `pyproject.toml`:
   ```toml
   [[tool.importlinter.contracts]]
   type = "forbidden_imports"
   source_modules = ["simple_cli_coder_with_rag.application", "simple_cli_coder_with_rag.domain", "simple_cli_coder_with_rag.presentation"]
   forbidden_modules = ["sqlite_vec"]
   ```

8. **Update `Settings`** in `infrastructure/settings.py`:
   ```python
   vector_store: Literal["sqlite_vec", "brute_force"] = "sqlite_vec"
   db_path: Path | None = None
   ```
   Resolution helper: if `db_path is None`, set `db_path = Path(user_data_dir("simple-cli-coder-with-rag")) / "db.sqlite"`. Use a module-level `resolve_db_path(settings)` function.

9. **Update `KnowledgeService`** constructor:
   ```python
   def __init__(self, llm, embedder, chunker, vector_store, session_store):
       ...
   ```

10. **Update `KnowledgeService.learn`**:
    - After `compact`, chunk.
    - `vectors = self.embedder.embed_passages([c.text for c in chunks])`.
    - `self.vector_store.upsert(chunks, vectors)`.
    - Return chunk count.

11. **Update composition root** in `cli.py`:
    ```python
    if settings.vector_store == "sqlite_vec":
        try:
            vs: VectorStore = SqliteVecStore(db_path=resolve_db_path(settings))
        except VectorStoreBackendUnavailable as exc:
            logger.info("sqlite-vec unavailable, falling back to numpy: {}", exc)
            vs = NumpyBruteForceStore()
    else:
        vs = NumpyBruteForceStore()
    ```

12. **Run the gate.** All exit 0.

13. **Commit:**
    ```bash
    git add src/simple_cli_coder_with_rag/domain/vector_store.py \
            src/simple_cli_coder_with_rag/infrastructure/vector_stores \
            src/simple_cli_coder_with_rag/infrastructure/settings.py \
            src/simple_cli_coder_with_rag/application/knowledge_service.py \
            src/simple_cli_coder_with_rag/cli.py \
            pyproject.toml uv.lock \
            tests/domain/test_vector_store.py \
            tests/infrastructure/vector_stores \
            tests/application/test_knowledge_service_learn_stores_vectors.py
    git status
    git commit -m "feat(rag): VectorStore Protocol + SqliteVecStore + NumpyBruteForceStore fallback

    - domain/vector_store.py: VectorStore Protocol (upsert, query) + VectorStoreBackendUnavailable.
    - infrastructure/vector_stores/sqlite_vec_store.py: schema per dev-tools.md §4
      (vec0, float[384], distance_metric=cosine, +text aux), startup check for
      enable_load_extension, delete-then-insert upsert by session_id (idempotent),
      fresh connection per query.
    - infrastructure/vector_stores/numpy_brute_force_store.py: in-memory cosine
      similarity; numpy imported inside methods to keep cold-start slim.
    - Settings.vector_store: Literal['sqlite_vec','brute_force']; Settings.db_path
      resolved via platformdirs user_data_dir.
    - composition root falls back to numpy when SqliteVecStore init raises.
    - KnowledgeService.learn: chunks -> embed -> upsert.

    Satisfies README bullet 4: 'The JSON file is stored into a vectorial database'."
    ```

14. **Post-flight.** `git status` clean.

## Failure modes

- **`sqlite_vec` API drift:** if `load_extension("vec0")` no longer works, the `web-search` step will have caught it. Otherwise, the schema check (dev-tools.md §4) is stable across the 0.1.x series.
- **Cosine similarity off by a sign:** sqlite-vec with `distance_metric=cosine` returns `1 - similarity`. Returning the raw distance (smaller is better) breaks DO-08's `top_k`. The protocol normalizes to similarity (larger is better); this is pinned by the `test_query_returns_similarity_in_minus_one_one` test.
- **Numpy fallback activates silently on a misconfigured system:** the INFO log line is the only signal. If the user reports slow retrieval, check this log first.
