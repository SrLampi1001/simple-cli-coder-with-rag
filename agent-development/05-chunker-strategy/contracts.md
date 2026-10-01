# DO-05 contracts

## Architectural

- [ ] New modules:
  - `simple_cli_coder_with_rag.domain.chunk`
  - `simple_cli_coder_with_rag.domain.chunker`
  - `simple_cli_coder_with_rag.application.chunkers.fixed_size`
  - `simple_cli_coder_with_rag.application.chunkers.semantic`
- [ ] `Chunker` Protocol lives in `domain/`; implementations live in `application/chunkers/`.
- [ ] `import-linter` reports zero violations.
- [ ] No chunker implementation imports from `infrastructure` or vendor SDKs.

## Behavioral

- [ ] Given a `CompactedSession` with summary `"hello"`, one error, one decision:
  - `FixedSizeChunker().chunk(c)` returns at least one chunk; total chunk text length is ≤ `max_chars + overlap` per chunk (when the input is long enough to produce >1 chunk).
  - `SemanticChunker().chunk(c)` returns exactly 3 chunks (summary, error, decision).
- [ ] Each chunk's `id` is a fresh UUIDv4 (no two chunks share an id).
- [ ] Each chunk's `metadata["source"]` is one of `"summary"`, `"error"`, `"decision"`.
- [ ] Each chunk's `session_id` equals the compacted session's `session_id`.
- [ ] Empty `CompactedSession` (no summary, no errors, no decisions) returns `[]` from both chunkers (not `[Chunk(text="")]`).
- [ ] `Settings(chunker_strategy="semantic").chunker_strategy == "semantic"`; `"fixed"` is the default.
- [ ] `KnowledgeService.learn` returns the chunk count, and `LearnCommand`'s message reflects it.

## Schema

- [ ] `class Chunk(BaseModel)`:
  - `id: str` — UUIDv4 string.
  - `text: str` — non-empty.
  - `metadata: dict[str, Any]`
  - `session_id: str`
- [ ] `class Chunker(Protocol)`:
  - `chunk(self, compacted: CompactedSession) -> list[Chunk]`
- [ ] `class FixedSizeChunker`:
  - `__init__(self, *, max_chars: int = 512, overlap: int = 64) -> None`
  - `chunk(self, compacted: CompactedSession) -> list[Chunk]`
  - validates `0 <= overlap < max_chars` in `__init__`; raises `ValueError` otherwise.
- [ ] `class SemanticChunker`:
  - `__init__(self, *, max_chars: int = 1024) -> None`
  - `chunk(self, compacted: CompactedSession) -> list[Chunk]`
- [ ] `Settings.chunker_strategy: Literal["fixed", "semantic"] = "fixed"`.
- [ ] `AppState.chunker: Chunker | None = None`.
- [ ] `KnowledgeService.learn` signature is unchanged: `learn(self, session_id: str) -> int` (returns the chunk count; was `None`).
