# DO-05 — Chunker strategy

## Goal

A `Chunker` Protocol with a default `FixedSizeChunker` and a `SemanticChunker` alternative. Chunking operates on the compacted JSON's `summary` + `errors` + `decisions` and produces `Chunk` objects ready for embedding.

## Source of truth

- `OBJECTIVES.md` — Strategy pattern (chunker).
- `docs/development-tools.md` §5 (RAG quality mostly tuning — Strategy gives cheap experimentation).

## Acceptance criteria

- [ ] `src/simple_cli_coder_with_rag/domain/chunk.py` defines `class Chunk(BaseModel)`:
  - `id: str` — UUIDv4.
  - `text: str`
  - `metadata: dict[str, Any]`
  - `session_id: str`
- [ ] `src/simple_cli_coder_with_rag/domain/chunker.py` defines:
  ```python
  class Chunker(Protocol):
      def chunk(self, compacted: CompactedSession) -> list[Chunk]: ...
  ```
- [ ] `src/simple_cli_coder_with_rag/application/chunkers/fixed_size.py` defines `class FixedSizeChunker`:
  - Constructor `(self, *, max_chars: int = 512, overlap: int = 64)`.
  - Joins `summary` + each error signature/message and each decision summary/rationale into one text, then splits on word boundaries with `max_chars` windows and `overlap` overlap.
  - Metadata per chunk: `{"source": "summary" | "error" | "decision", "index": int}`.
- [ ] `src/simple_cli_coder_with_rag/application/chunkers/semantic.py` defines `class SemanticChunker`:
  - Constructor `(self, *, max_chars: int = 1024)`.
  - One chunk per logical record (one for `summary`, one per error, one per decision).
  - Metadata per chunk: `{"source": "summary" | "error" | "decision", "index": int}`.
- [ ] `src/simple_cli_coder_with_rag/application/chunkers/__init__.py` exports both. The composition root in `cli.py` selects the default (`FixedSizeChunker`) but reads `CHUNKER_STRATEGY=fixed|semantic` from `Settings` (env var). Default `fixed`.
- [ ] `AppState` gains `chunker: Chunker | None = None`.
- [ ] `Settings` gains `chunker_strategy: Literal["fixed", "semantic"] = "fixed"`.
- [ ] `KnowledgeService.learn` is updated: after `compact`, it calls `self.chunker.chunk(compacted)` and (for now) just counts them; DO-06 embeds them, DO-07 stores them.
- [ ] `LearnCommand` returns `"learned N chunks"` with the actual count.
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

- Embedding the chunks (DO-06).
- Storing the chunks (DO-07).
- Sliding-window with sentence-aware boundaries (acceptable as a future enhancement).

## Depends on

- DO-04.

## Blocks

- DO-06, DO-07, DO-08, DO-09.
