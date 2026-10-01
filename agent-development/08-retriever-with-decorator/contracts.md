# DO-08 contracts

## Architectural

- [ ] New modules:
  - `simple_cli_coder_with_rag.domain.retriever` (Protocol + NamedTuple)
  - `simple_cli_coder_with_rag.application.retrievers.base_retriever`
  - `simple_cli_coder_with_rag.infrastructure.retrievers.timeout_retriever`
  - `simple_cli_coder_with_rag.infrastructure.retrievers.executor`
- [ ] `import-linter` reports zero violations.
- [ ] The Decorator wraps a `Retriever`; both `BaseRetriever` and `TimeoutRetriever` satisfy the same `Retriever` Protocol (verifiable by `isinstance` under `runtime_checkable`).
- [ ] `ThreadPoolExecutor` is imported only in `infrastructure/retrievers/executor.py`.
- [ ] **`RetrievalExecutor` is scoped to retrieval only.** It is **not** reused for LLM SDK calls or any other I/O. If future work needs to overlap the LLM SDK call with retrieval, that work must introduce a separate executor (e.g. `LLMCallExecutor(max_workers=1)`) in a layer of its own — never `RetrievalExecutor`. Mixing the two couples their cancellation and timeout policies and would defeat `TimeoutRetriever`'s bounded-latency guarantee.

## Behavioral

- [ ] `BaseRetriever.retrieve("q", top_k=3)` calls `embedder.embed_query("q")` once, then `vector_store.query(vector, top_k=3)`.
- [ ] `BaseRetriever.retrieve` raises `EmbedderNotReady` if `embedder.is_ready()` is False.
- [ ] `BaseRetriever.retrieve` returns a list of `RetrievedChunk` with `similarity` in `[-1.0, 1.0]`, sorted descending by `similarity`, length ≤ `top_k`.
- [ ] `TimeoutRetriever(inner, timeout_seconds=0.05, executor=...)` against an `inner` that sleeps 1 s returns `[]` within 50 ms and does **not** raise.
- [ ] `TimeoutRetriever` against an `inner` that completes in 10 ms returns the inner's results verbatim.
- [ ] `TimeoutRetriever` logs at DEBUG (via `loguru`) when a timeout fires.
- [ ] `RetrievalExecutor.shutdown()` calls `executor.shutdown(wait=False, cancel_futures=True)`. Verified by patching `concurrent.futures.ThreadPoolExecutor`.
- [ ] The composition root registers `RetrievalExecutor.shutdown()` on REPL exit (e.g. via `try/finally` in `cli.py` or an `on_exit` hook on `Repl`) so Ctrl-D does not hang waiting for the executor's threads. Pinned by an integration test that runs the REPL to EOF and asserts `shutdown(wait=False, cancel_futures=True)` was called.
- [ ] `KnowledgeService.recall` returns a `list[str]` of the chunk texts from the retriever (or `[]` on timeout or `EmbedderNotReady`).

## Schema

- [ ] `class RetrievedChunk(NamedTuple)`:
  - `chunk: Chunk`
  - `similarity: float`
- [ ] `class Retriever(Protocol)`:
  - `retrieve(self, query: str, *, top_k: int) -> list[RetrievedChunk]`
  - Annotated `@runtime_checkable`.
- [ ] `class BaseRetriever`:
  - `__init__(self, embedder: Embedder, vector_store: VectorStore) -> None`
  - `retrieve(self, query: str, *, top_k: int) -> list[RetrievedChunk]`
- [ ] `class TimeoutRetriever`:
  - `__init__(self, inner: Retriever, *, timeout_seconds: float, executor: RetrievalExecutor) -> None`
  - `retrieve(self, query: str, *, top_k: int) -> list[RetrievedChunk]`
- [ ] `class RetrievalExecutor`:
  - `__init__(self, max_workers: int = 2) -> None`
  - `submit(self, fn: Callable[..., T], /, *args, **kwargs) -> Future[T]`
  - `shutdown(self) -> None`
- [ ] `Settings.retrieval_timeout_seconds: float = 1.5`.
- [ ] `KnowledgeService.recall(self, query: str, *, top_k: int = 3) -> list[str]`.
