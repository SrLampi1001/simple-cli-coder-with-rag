# DO-08 — Retriever + timeout decorator

## Goal

A `Retriever` Protocol with `BaseRetriever` (calls `Embedder.embed_query` + `VectorStore.query`) wrapped by `TimeoutRetriever` (Decorator pattern) that bounds latency via a `ThreadPoolExecutor`. This deliverable does **not** wire retrieval into the chat — that is DO-09. The retriever is exposed and tested in isolation.

## Source of truth

- `README.md` — Decorator pattern (`Retriever → CachedRetriever → TimeoutRetriever`). Cache is deferred (dev-tools.md §12); only timeout is implemented now.
- `docs/development-tools.md` §9 (concurrency model: `ThreadPoolExecutor(max_workers=2)`; daemon warm-up; shutdown with `cancel_futures=True`).

## Acceptance criteria

- [ ] `src/simple_cli_coder_with_rag/domain/retriever.py` defines:
  ```python
  class RetrievedChunk(NamedTuple):
      chunk: Chunk
      similarity: float

  class Retriever(Protocol):
      def retrieve(self, query: str, *, top_k: int) -> list[RetrievedChunk]: ...
  ```
- [ ] `src/simple_cli_coder_with_rag/application/retrievers/base_retriever.py` defines `class BaseRetriever`:
  - `__init__(self, embedder: Embedder, vector_store: VectorStore)`.
  - `retrieve(self, query, *, top_k)`: calls `embedder.embed_query(query)`, then `vector_store.query(vector, top_k=top_k)`, maps each `(chunk, similarity)` to `RetrievedChunk(chunk, similarity)`.
  - Raises `EmbedderNotReady` if `embedder.is_ready()` is `False` at call time (caller's responsibility to gate; the retriever itself does not wait).
- [ ] `src/simple_cli_coder_with_rag/infrastructure/retrievers/timeout_retriever.py` defines `class TimeoutRetriever`:
  - `__init__(self, inner: Retriever, *, timeout_seconds: float, executor: ThreadPoolExecutor)`.
  - `retrieve(self, query, *, top_k)`: submits `inner.retrieve(query, top_k=top_k)` to the executor; calls `future.result(timeout=timeout_seconds)`. On `TimeoutError`, returns `[]` and logs at DEBUG.
- [ ] `src/simple_cli_coder_with_rag/infrastructure/retrievers/executor.py` defines `RetrievalExecutor` (a thin wrapper around `ThreadPoolExecutor(max_workers=2)`):
  - `__init__(self, max_workers: int = 2)`.
  - `submit(fn, /, *args, **kwargs) -> Future`.
  - `shutdown(self) -> None` — calls `self._executor.shutdown(wait=False, cancel_futures=True)`.
- [ ] `Settings` gains `retrieval_timeout_seconds: float = 1.5`.
- [ ] `KnowledgeService.recall(query, *, top_k) -> list[str]` is implemented as `retriever.retrieve(query, top_k=top_k)` returning `[r.chunk.text for r in results]`. Still called from DO-09.
- [ ] The full gate exits 0.

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

- Wiring retrieval into the chat path (DO-09).
- The trivial-request gate (DO-09).
- CachedRetriever (deferred per dev-tools.md §12).
- `CachedRetriever` is a future Decorator wrapper, not in this deliverable.

## Depends on

- DO-06, DO-07.

## Blocks

- DO-09.
