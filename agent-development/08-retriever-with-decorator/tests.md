# DO-08 tests

These tests must be written **before** any code in this deliverable.

## Test files

```
tests/domain/
└── test_retriever.py

tests/application/retrievers/
├── __init__.py
└── test_base_retriever.py

tests/infrastructure/retrievers/
├── __init__.py
├── test_timeout_retriever.py
└── test_executor.py

tests/application/
└── test_knowledge_service_recall.py
```

## Test functions and assertions

### `tests/domain/test_retriever.py`

- `test_protocol_declares_retrieve` — `Retriever.retrieve(self, query: str, *, top_k: int)`.
- `test_runtime_checkable` — `isinstance(some_retriever, Retriever)` returns True for any class with the right method.
- `test_retrieved_chunk_is_named_tuple` — `RetrievedChunk(chunk, similarity)` is unpackable into `(chunk, similarity)`.

### `tests/application/retrievers/test_base_retriever.py`

Embedder and VectorStore are recording fakes.

- `test_retrieve_embeds_then_queries` — `embedder.embed_query` called once with `query`; `vector_store.query` called with the embedded vector and `top_k`.
- `test_retrieve_returns_retrieved_chunks_sorted` — VectorStore returns `[(c1, 0.9), (c2, 0.5)]`; `BaseRetriever.retrieve` returns `[RetrievedChunk(c1, 0.9), RetrievedChunk(c2, 0.5)]`.
- `test_retrieve_respects_top_k` — VectorStore returns 5 chunks; `retrieve(..., top_k=2)` returns 2.
- `test_retrieve_raises_when_embedder_not_ready` — `embedder.is_ready()` is False; `retrieve` raises `EmbedderNotReady`.
- `test_retrieve_passes_through_when_ready` — `embedder.is_ready()` is True; `retrieve` returns the chunks.

### `tests/infrastructure/retrievers/test_timeout_retriever.py`

`Inner` is a controllable fake.

- `test_inner_completes_returns_its_results` — `inner.retrieve` returns `[a, b]`; result is `[a, b]`.
- `test_inner_times_out_returns_empty` — `inner.retrieve` blocks 1 s; `timeout_seconds=0.05`; result is `[]` and the call returns within ~100 ms.
- `test_timeout_logs_at_debug` — patched `loguru.logger.debug` is called at least once with a message mentioning "retrieval timeout" or similar.
- `test_timeout_does_not_cancel_running_task_but_does_not_wait` — `inner.retrieve` blocks 5 s; the test asserts the call returns within ~100 ms but the executor still has a pending future (verified by `executor._executor._threads` or by patching and inspecting the future's `done()`).

### `tests/infrastructure/retrievers/test_executor.py`

- `test_executor_default_two_workers` — patching `ThreadPoolExecutor` and inspecting `max_workers` argument.
- `test_executor_submit_returns_future` — `executor.submit(lambda x: x + 1, 1).result() == 2`.
- `test_executor_shutdown_calls_with_cancel_futures_true` — patched `ThreadPoolExecutor.shutdown` is called with `wait=False, cancel_futures=True`.

### `tests/application/test_knowledge_service_recall.py`

- `test_recall_returns_chunk_texts` — Retriever returns `[RetrievedChunk(Chunk(text="a"), 0.9), RetrievedChunk(Chunk(text="b"), 0.5)]`; `recall("q")` returns `["a", "b"]`.
- `test_recall_returns_empty_on_embedder_not_ready` — Retriever raises `EmbedderNotReady`; `recall` returns `[]`.
- `test_recall_returns_empty_on_timeout` — Retriever is wrapped in `TimeoutRetriever(timeout=0.05)` against a blocking inner; `recall` returns `[]` within ~100 ms.

### `tests/presentation/test_repl_exit_shuts_down_executor.py`

- `test_repl_eof_calls_executor_shutdown` — `Repl.run()` is fed an empty stream (immediate EOF); after it returns, `RetrievalExecutor.shutdown()` has been called. Patch `RetrievalExecutor.shutdown` and assert it was invoked exactly once. Pins the composition-root exit hook so Ctrl-D does not hang.

## Why these tests

- `test_retrieve_embeds_then_queries` pins the orchestration order — the most common mistake is calling `query` before `embed`.
- The timeout tests pin the Decorator's value proposition (bounded latency) and document that `future.result(timeout=)` does not cancel the underlying work (per dev-tools.md §9).
- The executor-shutdown test prevents the `wait=True` footgun that delays Ctrl-D exit.
- The REPL-exit test pins that the shutdown actually runs (not just that `shutdown()` is well-behaved in isolation).
