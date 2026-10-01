# DO-09 — Recall in chat (semantic search before prompt)

## Goal

Recall runs automatically before every chat prompt (excluding slash commands). The trivial-request gate skips retrieval for short prompts. Retrieval is bounded by the `TimeoutRetriever` decorator (which uses the shared `RetrievalExecutor`), so it never blocks the prompt for long; true overlap with prompt preparation is **not** implemented in v1 (recall is awaited before chat) and is deferred. Top-k is 3; a similarity threshold filters out weak matches. This completes the fifth README bullet: *"A prompt triggers semantic search and retrieves the important context."*

## Source of truth

- `README.md` — "A prompt triggers semantic search and retrieves the important context" + latency tips: skip trivial requests, top-k=3, threshold, concurrent retrieval.
- `docs/development-tools.md` §9 (concurrency), §5 (concurrency, threshold, top-k).

## Acceptance criteria

- [ ] `src/simple_cli_coder_with_rag/application/trivial_gate.py` defines `class TrivialGate`:
  - `__init__(self, *, max_chars: int = 20, max_words: int = 4)`.
  - `is_trivial(self, prompt: str) -> bool` — True iff `len(prompt) <= max_chars` **and** `len(prompt.split()) <= max_words`. (Both bounds must hold; with `or`, a single long word would be misclassified as trivial.)
- [ ] `Settings` gains:
  - `recall_top_k: int = 3`
  - `recall_similarity_threshold: float = 0.5`
  - `trivial_gate_max_chars: int = 20`
  - `trivial_gate_max_words: int = 4`
- [ ] `src/simple_cli_coder_with_rag/application/recall_coordinator.py` defines `class RecallCoordinator`:
  - `__init__(self, retriever: Retriever, gate: TrivialGate, *, top_k: int, similarity_threshold: float)`. `retriever` is the `TimeoutRetriever`-wrapped `Retriever` built by the composition root; the coordinator does not own an executor.
  - `recall(self, prompt: str) -> list[str]`:
    - If `gate.is_trivial(prompt)`: return `[]`, log at DEBUG.
    - Else: call `retriever.retrieve(prompt, top_k=top_k)`; on success, filter by `similarity >= threshold`; return `[r.chunk.text for r in results]`.
    - On `EmbedderNotReady` or a raised `TimeoutError`: return `[]`, log at DEBUG. (A `TimeoutRetriever` returns `[]` rather than raising; the `TimeoutError` catch is defensive.)
- [ ] `KnowledgeService.recall` is updated to delegate to `RecallCoordinator`.
- [ ] `application/prompts.py:build_chat_messages` is updated to accept the recalled texts and inject them into the **system** message as a `SystemMessage(content=...)` placed at the start of the messages list. Format: `"The following context may be relevant:\n\n" + "\n\n---\n\n".join(recalled)`.
- [ ] The REPL chat path (DO-03) is updated: before calling `knowledge.chat(...)`, it calls `knowledge.recall(input)` and passes the result to `build_chat_messages`. If `embedder.is_ready()` is False, retrieval is skipped and no message is logged at INFO (only DEBUG).
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

- CachedRetriever (deferred per dev-tools.md §12).
- Re-ranking (the README says "No reranking needed").

## Depends on

- DO-03, DO-06, DO-07, DO-08.

## Blocks

- Nothing (last major RAG deliverable; DO-10 is independent).
