# DO-05 workflow

## Subagent delegation

**One subagent.** Two chunker implementations + a Protocol + a domain model are tightly coupled; splitting risks drift in `Chunk` schema.

### Context passed to the subagent

- `agent-development/README.md`.
- The four files in this folder.
- `docs/development-tools.md` §5 only (chunking rationale).
- Nothing else.

## Web-search verification

Not required. The chunker is project-owned code; no new deps.

## Steps

1. **Pre-flight.** `git status` clean.

2. **Write the test files** from `tests.md` first. Confirm they fail.

3. **Write `src/simple_cli_coder_with_rag/domain/chunk.py`** with `Chunk`. Use `pydantic.BaseModel` with `frozen=False` (chunks are mutable in tests). Use `Field(default_factory=lambda: str(uuid.uuid4()))` for `id`.

4. **Write `src/simple_cli_coder_with_rag/domain/chunker.py`** with the `Chunker` Protocol.

5. **Write `src/simple_cli_coder_with_rag/application/chunkers/__init__.py`** exporting `FixedSizeChunker` and `SemanticChunker`.

6. **Write `src/simple_cli_coder_with_rag/application/chunkers/fixed_size.py`** with `FixedSizeChunker`. Implementation:
   - Build a list of `(source, text)` records by iterating `compacted.summary` (one record), each error (`f"Error: {e.signature}\\n{e.message}"`), each decision (`f"Decision: {d.summary}\\n{d.rationale}"`).
   - Concatenate records with `\n\n`.
   - Slide a `max_chars` window with `overlap` overlap, breaking on the nearest preceding space (or hard-cut if no space is found).
   - Each chunk's `text` is the window content; `metadata = {"source": <of the first record whose text begins this chunk>, "index": i}`.
   - If a window spans multiple records, the source is the **first** record's source (documented in the module docstring).

7. **Write `src/simple_cli_coder_with_rag/application/chunkers/semantic.py`** with `SemanticChunker`. One chunk per record, simple.

8. **Update `Settings`** in `infrastructure/settings.py`:
   ```python
   chunker_strategy: Literal["fixed", "semantic"] = "fixed"
   ```

9. **Update `AppState`** to add `chunker: Chunker | None = None`.

10. **Update `KnowledgeService.learn`** signature: returns `int` (chunk count). Internally, after `compact`, call `self.chunker.chunk(compacted)`, store the chunks on `self.last_chunks` (used by DO-06), return `len(chunks)`.

11. **Update composition root** in `cli.py`:
    - If `settings.chunker_strategy == "fixed"`, instantiate `FixedSizeChunker()`; else `SemanticChunker()`.
    - Pass to `KnowledgeService` (constructor takes `chunker` too now).

12. **Update `LearnCommand`** to read the count from the result of `learn`.

13. **Run the gate.** All exit 0.

14. **Commit (suggested template — adapt to actual changes):**
    ```bash
    git add src/simple_cli_coder_with_rag/domain/chunk.py \
            src/simple_cli_coder_with_rag/domain/chunker.py \
            src/simple_cli_coder_with_rag/application/chunkers \
            src/simple_cli_coder_with_rag/application/knowledge_service.py \
            src/simple_cli_coder_with_rag/infrastructure/settings.py \
            src/simple_cli_coder_with_rag/presentation/commands/__init__.py \
            src/simple_cli_coder_with_rag/cli.py \
            tests/domain/test_chunk.py \
            tests/application/chunkers \
            tests/application/test_knowledge_service_chunking.py \
            tests/infrastructure/test_settings_chunker_strategy.py
    git status
    git commit -m "feat(rag): Chunker Protocol + FixedSizeChunker (default) + SemanticChunker

    - domain/chunk.py: Chunk (id UUIDv4, text, metadata, session_id).
    - domain/chunker.py: Chunker Protocol (chunk(compacted) -> list[Chunk]).
    - application/chunkers/fixed_size.py: sliding window with overlap, validates
      0 <= overlap < max_chars.
    - application/chunkers/semantic.py: one chunk per logical record.
    - Settings.chunker_strategy: Literal['fixed','semantic'], default 'fixed'.
    - KnowledgeService.learn returns the chunk count; LearnCommand message reflects it.

    Foundation for DO-06 (embedder) and DO-07 (vector store)."
    ```
    **Note:** The above message is a template. If `Chunk` fields changed, if the chunking algorithm was adjusted, if a different default strategy was chosen, or if `KnowledgeService.learn` signature differs — update the commit body to reflect reality.

15. **Post-flight.** `git status` clean.

## Failure modes

- **`FixedSizeChunker` returns chunks with overlapping source metadata:** the metadata records the source of the **first** record the window covers. Document this; if a future test demands "majority source", change it then.
- **`KnowledgeService` constructor changed but `cli.py` not updated:** tests in DO-03 will fail loudly when re-run because `AppState.knowledge` won't initialize.
