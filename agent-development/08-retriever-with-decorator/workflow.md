# DO-08 workflow

## Subagent delegation — SPLIT INTO TWO

The base retriever (in `application/`) and the timeout decorator + executor (in `infrastructure/`) are on opposite sides of a layer boundary. They can be developed in parallel.

### Subagent A — base retriever + Protocol + recall wiring

**Owns:**
- `src/simple_cli_coder_with_rag/domain/retriever.py`
- `src/simple_cli_coder_with_rag/application/retrievers/base_retriever.py`
- Edits to `src/simple_cli_coder_with_rag/application/knowledge_service.py` (replace `recall` stub)
- `tests/domain/test_retriever.py`
- `tests/application/retrievers/test_base_retriever.py`
- `tests/application/test_knowledge_service_recall.py`

**Contract to satisfy:** schema for `RetrievedChunk`, `Retriever`, `BaseRetriever` in `contracts.md`. `KnowledgeService.recall(query, *, top_k=3)` calls the injected `Retriever.retrieve`, maps `RetrievedChunk.chunk.text`, and **catches `EmbedderNotReady` returning `[]`** (the retriever raises; the service degrades gracefully). The `Retriever` it receives is already `TimeoutRetriever`-wrapped by the composition root, so a timeout surfaces as `[]` from the retriever — no second timeout wrapper is added here.

### Subagent B — timeout decorator + executor

**Owns:**
- `src/simple_cli_coder_with_rag/infrastructure/retrievers/timeout_retriever.py`
- `src/simple_cli_coder_with_rag/infrastructure/retrievers/executor.py`
- Edits to `src/simple_cli_coder_with_rag/infrastructure/settings.py` (add `retrieval_timeout_seconds`)
- `tests/infrastructure/retrievers/test_timeout_retriever.py`
- `tests/infrastructure/retrievers/test_executor.py`

**Contract to satisfy:** schema for `TimeoutRetriever`, `RetrievalExecutor` in `contracts.md`.

### Orchestrator

1. Runs pre-flight.
2. Spawns A and B in parallel.
3. Wires the composition root: build `retrieval_executor = RetrievalExecutor(max_workers=2)`, then `retriever = TimeoutRetriever(BaseRetriever(embedder, vector_store), timeout_seconds=settings.retrieval_timeout_seconds, executor=retrieval_executor)`. Assign the wrapped `retriever` where `KnowledgeService` expects it.
4. Registers `retrieval_executor.shutdown()` on REPL exit (e.g. `Repl` calls an optional `on_exit` callback, or `cli.py` runs `repl.run()` inside `try/finally`). dev-tools.md §9 requires `shutdown(wait=False, cancel_futures=True)` so Ctrl-D does not hang.
5. After both subagents return, runs the full gate.
6. Single commit at the end.

## Web-search verification

Not required. `concurrent.futures.ThreadPoolExecutor` is stdlib-stable; no new deps.

## Steps

1. **Pre-flight.** `git status` clean.

2. **Spawn subagents A and B in parallel.**

3. **Wire the composition root and the exit hook** (orchestrator, after both return): wrap `BaseRetriever` in `TimeoutRetriever` sharing the single `RetrievalExecutor`, and ensure `RetrievalExecutor.shutdown()` runs on REPL exit. Confirm `KnowledgeService` receives the **wrapped** retriever, not the bare `BaseRetriever`.

4. **Run the gate.** All exit 0.

5. **Commit (suggested template — adapt to actual changes):**
   ```bash
   git add src/simple_cli_coder_with_rag/domain/retriever.py \
           src/simple_cli_coder_with_rag/application/retrievers \
           src/simple_cli_coder_with_rag/infrastructure/retrievers \
           src/simple_cli_coder_with_rag/infrastructure/settings.py \
           src/simple_cli_coder_with_rag/application/knowledge_service.py \
           src/simple_cli_coder_with_rag/infrastructure/settings.py \
           src/simple_cli_coder_with_rag/presentation/repl.py \
           src/simple_cli_coder_with_rag/cli.py \
           tests/domain/test_retriever.py \
           tests/application/retrievers \
           tests/application/test_knowledge_service_recall.py \
           tests/infrastructure/retrievers
   git status
   git commit -m "feat(rag): Retriever Protocol + BaseRetriever + TimeoutRetriever Decorator

    - domain/retriever.py: Retriever Protocol (@runtime_checkable) and RetrievedChunk NamedTuple.
    - application/retrievers/base_retriever.py: BaseRetriever(embedder, vector_store)
      orchestrates embed_query -> vector_store.query -> list[RetrievedChunk].
      Raises EmbedderNotReady when embedder.is_ready() is False (caller's gate).
    - infrastructure/retrievers/timeout_retriever.py: TimeoutRetriever(inner,
      timeout_seconds, executor) Decorator wrapping the Protocol; on timeout returns []
      and logs at DEBUG. Note: future.result(timeout=...) does not cancel the work.
    - infrastructure/retrievers/executor.py: RetrievalExecutor wraps
      ThreadPoolExecutor(max_workers=2); shutdown(wait=False, cancel_futures=True).
    - Settings.retrieval_timeout_seconds: float = 1.5.
    - KnowledgeService.recall delegates to the (wrapped) retriever, catches
      EmbedderNotReady, and returns chunk texts.
    - composition root wraps BaseRetriever in TimeoutRetriever sharing one executor;
      executor shutdown is wired to REPL exit.

    Foundation for DO-09. CachedRetriever is deferred per dev-tools.md §12."
   ```
   **Note:** The above message is a template. The single commit merges two subagents' work. If the `Retriever` Protocol shape changed, if `RetrievedChunk` is not a `NamedTuple`, if the executor was configured differently, or if `KnowledgeService.recall` returns a different type — update the commit body to reflect reality.

6. **Post-flight.** `git status` clean.

## Failure modes

- **Subagent A and B disagree on `Retriever` Protocol shape:** subagent A owns the Protocol. Subagent B imports it. If they diverge, the orchestrator catches it on the merge step.
- **`TimeoutRetriever` blocks forever despite a timeout:** usually means `future.result(timeout=...)` was called with `timeout=None`, or the inner retriever raised **before** the future was created (the inner call must be submitted to the executor).
- **`cancel_futures=True` is not available in Python <3.9:** we require 3.11, so this is safe. The startup check from DO-00 already enforces the version.
