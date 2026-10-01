# DO-05 tests

These tests must be written **before** any code in this deliverable.

## Test files

```
tests/domain/
└── test_chunk.py

tests/application/chunkers/
├── __init__.py
├── test_fixed_size.py
└── test_semantic.py

tests/application/
└── test_knowledge_service_chunking.py  (extends the DO-04 test)

tests/infrastructure/
└── test_settings_chunker_strategy.py  (extends the DO-02 test)
```

## Test functions and assertions

### `tests/domain/test_chunk.py`

- `test_chunk_id_is_uuid_v4` — `Chunk(text="x", session_id="s", metadata={}).id` matches the UUIDv4 regex.
- `test_chunk_round_trip` — `Chunk(...).model_dump_json()` round-trips.
- `test_chunk_rejects_empty_text` — `Chunk(text="", ...)` raises `ValidationError`.

### `tests/application/chunkers/test_fixed_size.py`

- `test_fixed_size_rejects_overlap_ge_max_chars` — `FixedSizeChunker(max_chars=10, overlap=10)` raises `ValueError`; `overlap=11` raises; `overlap=-1` raises.
- `test_fixed_size_short_text_single_chunk` — `summary="hi"` → exactly one chunk with `text="hi"`.
- `test_fixed_size_long_text_multiple_chunks` — `summary="x" * 5000` with `max_chars=512, overlap=64` → many chunks; `chunks[i].text` and `chunks[i+1].text` overlap by ~64 chars.
- `test_fixed_size_metadata_source` — chunk from `summary` has `metadata["source"] == "summary"`; chunk from `error` has `source == "error"`; same for `decision`.
- `test_fixed_size_session_id_propagates` — every chunk's `session_id` equals the input's.
- `test_fixed_size_empty_compacted_returns_empty` — empty input → `[]`.

### `tests/application/chunkers/test_semantic.py`

- `test_semantic_one_chunk_per_record` — input with summary + 2 errors + 1 decision → exactly 4 chunks.
- `test_semantic_metadata` — same as fixed.
- `test_semantic_session_id_propagates` — same as fixed.
- `test_semantic_empty_compacted_returns_empty` — same as fixed.

### `tests/application/test_knowledge_service_chunking.py`

Reuses the DO-04 fixture pattern; `Chunker` is the real `FixedSizeChunker`, `Compactor` is mocked.

- `test_learn_returns_chunk_count` — `learn(session_id)` returns an `int` ≥ 1.
- `test_learn_command_message_includes_count` — `LearnCommand.execute` returns a message matching `r"learned \d+ chunks"`.

### `tests/infrastructure/test_settings_chunker_strategy.py`

- `test_settings_default_chunker_strategy` — default is `"fixed"`.
- `test_settings_accepts_semantic` — `Settings(..., chunker_strategy="semantic")` works.
- `test_settings_rejects_unknown_strategy` — `Settings(..., chunker_strategy="foo")` raises `ValidationError`.

## Why these tests

- The `overlap >= max_chars` test prevents a class of off-by-one bugs that would silently break retrieval.
- The empty-compacted test prevents both chunkers from producing a single empty chunk that would later be embedded as a zero vector.
- The chunk-count round-trip test ensures DO-06 and DO-07 will have a real number to read.
