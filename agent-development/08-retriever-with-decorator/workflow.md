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

**Contract to satisfy:** schema for `RetrievedChunk`, `Retriever`, `BaseRetriever` in `contracts.md`.

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
3. After both return, runs the gate.
4. Single commit at the end.

## Web-search verification

Not required. `concurrent.futures.ThreadPoolExecutor` is stdlib-stable; no new deps.

## Steps

1. **Pre-flight.** `git status` clean.

2. **Spawn subagents A and B in parallel.**

3. **After both return, run the gate.** All exit 0.

4. **Commit:**
   ```bash
   git add src/simple_cli_coder_with_rag/domain/retriever.py \
           src/simple_cli_coder_with_rag/application/retrievers \
           src/simple_cli_coder_with_rag/infrastructure/retrievers \
           src/simple_cli_coder_with_rag/infrastructure/settings.py \
           src/simple_cli_coder_with_rag/application/knowledge_service.py \
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
    - KnowledgeService.recall now delegates to the retriever and returns chunk texts.

    Foundation for DO-09. CachedRetriever is deferred per dev-tools.md §12."
   ```

5. **Post-flight.** `git status` clean.

## Failure modes

- **Subagent A and B disagree on `Retriever` Protocol shape:** subagent A owns the Protocol. Subagent B imports it. If they diverge, the orchestrator catches it on the merge step.
- **`TimeoutRetriever` blocks forever despite a timeout:** usually means `future.result(timeout=...)` was called with `timeout=None`, or the inner retriever raised **before** the future was created (the inner call must be submitted to the executor).
- **`cancel_futures=True` is not available in Python <3.9:** we require 3.11, so this is safe. The startup check from DO-00 already enforces the version.
