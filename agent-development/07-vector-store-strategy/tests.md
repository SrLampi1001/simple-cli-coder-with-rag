# DO-07 tests

These tests must be written **before** any code in this deliverable.

## Test files

```
tests/domain/
└── test_vector_store.py

tests/infrastructure/vector_stores/
├── __init__.py
├── test_sqlite_vec_store.py
└── test_numpy_brute_force_store.py
```

`sqlite_vec` is patched via `pytest-mock` so tests do not require a real extension.

## Test functions and assertions

### `tests/domain/test_vector_store.py`

- `test_protocol_has_required_methods` — Protocol declares both methods with correct signatures.
- `test_backend_unavailable_is_runtime_error` — `VectorStoreBackendUnavailable` is a `RuntimeError` subclass with the dev-tools.md §4 message format.

### `tests/infrastructure/vector_stores/test_sqlite_vec_store.py`

- `test_init_raises_when_enable_load_extension_is_none` — patch `sqlite3.connect` to return a stub connection with `enable_load_extension = None`. `SqliteVecStore(...)` raises `VectorStoreBackendUnavailable`.
- `test_init_raises_when_enable_load_extension_raises` — same for `NotSupportedError` / `OperationalError`.
- `test_init_creates_schema` — patched connection captures `execute` calls; one of them is the `CREATE VIRTUAL TABLE chunks USING vec0(...)` with `distance_metric=cosine`, `+text TEXT`, `session_id TEXT`, `created_at INTEGER`.
- `test_upsert_writes_rows` — captured `executemany` payload matches `(vector, text, session_id, created_at)` tuples.
- `test_upsert_is_idempotent_by_session` — two `upsert` calls for the same `session_id` produce exactly one set of rows in the captured `executemany` after the `DELETE`.
- `test_query_returns_top_k_by_cosine_similarity` — fixture: 5 chunks with vectors `[[1,0,0,...], [0,1,0,...], ...]`. Query with `[1,0,0,...]`, `top_k=2`. Result: the first two chunks, in the order of cosine similarity descending. Cosine is `1.0` for the first and `< 1.0` for the rest.
- `test_query_returns_similarity_in_minus_one_one` — for any returned float, `-1.0 <= s <= 1.0`.
- `test_query_opens_fresh_connection` — patched `sqlite3.connect` is called inside `query` (counted before/after).

### `tests/infrastructure/vector_stores/test_numpy_brute_force_store.py`

- `test_upsert_then_query_returns_chunks` — upsert 3 chunks, query with the vector of the second; result contains the second chunk with similarity `1.0`.
- `test_query_cosine_similarity_known_vectors` — upsert `[1,0]`, `[0,1]`. Query `[1,1]`. Cosine to first is `1/sqrt(2) ≈ 0.707`; to second is the same. Both chunks returned; similarity is `0.7071 ± 1e-3`.
- `test_query_respects_top_k` — upsert 5 chunks, `top_k=2` returns 2.
- `test_query_empty_store_returns_empty` — no `upsert`, `query` returns `[]`.
- `test_upsert_is_idempotent_by_session` — two `upsert` calls for the same `session_id` leave exactly one stored copy (mirrors `SqliteVecStore`).
- `test_query_skips_zero_norm_rows` — upsert a chunk with the zero vector; query returns no `NaN` similarity and excludes that row. (Prevents division-by-zero in the cosine denominator.)

### `tests/application/test_knowledge_service_learn_stores_vectors.py`

`Embedder` is a `FakeEmbedder` (returns deterministic 384-dim vectors from a hash of the text). `VectorStore` is an in-memory recording fake.

- `test_learn_calls_embedder_for_each_chunk` — after `learn`, the embedder was called once per chunk with the chunk's text.
- `test_learn_calls_vector_store_upsert_with_chunks_and_vectors` — captured args match `(chunks, vectors)` from the previous step.

## Why these tests

- The `enable_load_extension` failure tests pin the dev-tools.md §4 startup check, which is the most common cross-platform failure mode.
- The `+text` aux column test pins the schema, including the easy-to-forget `+` prefix.
- The idempotency test prevents DO-09 from re-storing the same session repeatedly (cosine distances inflate otherwise); both stores share this contract.
- The cosine-similarity-known-vectors test is a regression guard against an off-by-one bug in the numpy fallback.
- The zero-norm-skip test guards against `NaN` similarities if a malformed vector is stored (the cosine denominator is zero).
