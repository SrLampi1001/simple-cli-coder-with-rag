# DO-13 tests

These tests must be written **before** any code in this deliverable.
They MUST fail on the DO-12 state (no `domain/document_loader.py`,
no `infrastructure/document_loaders/`, no
`infrastructure/vector_stores/supabase_store.py`,
`Chunk` does not yet have `source` / `chunk_index` fields,
`LearnCommand` does not yet accept a `<path>` argument, no
`/vector-store` command, no `config/defaults.toml`,
`build_chat_messages` does not yet include source metadata) and MUST
pass before DO-13 is marked done.

## Test files

```
tests/
├── domain/
│   ├── test_document_metadata.py          # NEW — Pydantic model
│   └── test_chunk_with_source.py          # NEW — schema patch
├── infrastructure/
│   ├── document_loaders/
│   │   ├── __init__.py
│   │   └── test_extension_dispatch.py     # NEW — three format paths
│   ├── vector_stores/
│   │   └── test_supabase_store.py         # NEW — adapter via SDK
│   └── test_defaults.py                   # NEW — TOML loader
├── application/
│   ├── chunkers/
│   │   └── test_fixed_size_text.py        # NEW — chunk_text method
│   ├── test_learn_document.py             # NEW — /learn <path> integration
│   ├── test_knowledge_service_set_vector_store.py  # NEW
│   └── test_prompts_source_format.py     # NEW — system-prompt formatting
└── presentation/
    └── commands/
        ├── test_learn_path.py             # NEW — LearnCommand <path>
        └── test_vector_store.py           # NEW — switch command
```

`supplementary` (data fixtures committed alongside the tests):

- `tests/fixtures/architecture.md`, `tests/fixtures/style-guide.txt`,
  `tests/fixtures/api-reference.pdf` — minimal test fixtures (one
  per format). Generated from the `data/documents/` sample files
  during test setup; the fixtures are committed so the test suite
  is hermetic.

## Test functions and assertions

### `tests/domain/test_document_metadata.py`

- `test_document_metadata_required_source` — constructing
  `DocumentMetadata(source="foo.md", file_type="md",
  byte_size=10)` succeeds.
- `test_document_metadata_pdf_includes_page_count` —
  `DocumentMetadata(..., file_type="pdf", page_count=3,
  byte_size=1024)` round-trips.
- `test_document_metadata_rejects_unknown_file_type` —
  `file_type="docx"` raises `ValidationError`.
- `test_document_metadata_default_page_count_is_none` —
  omitting `page_count` gives `None` (default).

### `tests/domain/test_chunk_with_source.py`

- `test_chunk_default_source_empty` —
  `Chunk(text="x")` has `source == ""` and `chunk_index == 0`.
- `test_chunk_with_source_round_trips` —
  `Chunk(text="x", source="foo.md", chunk_index=2)`
  validates and dumps both fields.
- `test_chunk_validate_omitted_source` —
  `Chunk.model_validate({"text": "x", "chunk_index": 3})`
  succeeds with `source == ""` (default).

### `tests/infrastructure/document_loaders/test_extension_dispatch.py`

Uses `tmp_path` for the test files. No mocks (PDF/text files are
trivial to write).

- `test_load_markdown_returns_text` — write a `.md` file with
  three lines; `load(path)` returns the text + `DocumentMetadata
  (file_type="md", byte_size=<n>, page_count=None)`.
- `test_load_markdown_alias_markdown_extension` — same with
  `.markdown` extension; `file_type="md"`.
- `test_load_text_returns_text` — same with `.txt`.
- `test_load_pdf_returns_text_with_page_count` — write a
  one-page PDF (use the fixture `tests/fixtures/
  api-reference.pdf`); `load(path)` returns concatenated text
  + `DocumentMetadata(file_type="pdf", page_count=1,
  byte_size=<n>)`.
- `test_load_unsupported_extension` — `.docx` raises
  `UnsupportedDocumentError` with the message naming the
  unsupported extension and listing the supported ones.
- `test_load_missing_file_raises_filenotfound` —
  `load(Path("nope.md"))` raises `FileNotFoundError`.
- `test_load_text_replaces_invalid_utf8` — write a file
  containing invalid UTF-8 bytes; `load` returns the text
  containing `U+FFFD` replacement characters (no crash).
- `test_load_pdf_zero_pages_returns_empty_text` — write a
  blank PDF; `load` returns `("", DocumentMetadata(..., 
  page_count=0, byte_size=<n>))`.

### `tests/infrastructure/vector_stores/test_supabase_store.py`

Uses `mocker` to patch `supabase.create_client`. No real network.

- `test_init_does_not_network` — constructing
  `SupabaseVectorStore(url=..., key=...,
  table_name="chunks")` does **not** call `supabase
  .create_client` until `upsert` or `query` is invoked (the
  client is built lazily inside `upsert` / `query`, OR is
  built in `__init__` but with no RPC sent — pin by pin).
- `test_upsert_calls_table_insert_with_expected_payload` —
  given a stub client whose
  `client.table("chunks").insert(rows).execute()` chain
  returns a successful response, `upsert([Chunk(text="a",
  source="x", chunk_index=0)], [[0.1, 0.2, 0.3]])` invokes
  the insert with `rows == [{"source": "x",
  "chunk_index": 0, "content": "a", "embedding":
  [0.1, 0.2, 0.3]}]`.
- `test_query_calls_match_chunks_rpc` — stub
  `client.rpc("match_chunks", {...}).execute()` returns a
  list of dicts. `query([0.1, 0.2, 0.3], top_k=3)` invokes
  `match_chunks` with `{"query_embedding": [0.1, 0.2, 0.3],
  "match_count": 3}` and returns `list[ScoredChunk]`
  unpacked from the response.
- `test_query_maps_supabase_error_to_backend_unavailable` —
  the stub `client.rpc(...)` raising
  `requests.exceptions.ConnectionError`. The adapter raises
  `VectorStoreBackendUnavailable`.
- `test_repr_does_not_leak_key` — `repr(SupabaseVectorStore
  (url=..., key="supersecret-xyz", table_name="chunks"))`
  does **not** contain `"supersecret-xyz"`.

### `tests/infrastructure/test_defaults.py`

Uses `tmp_path` for custom TOML files. The committed
`config/defaults.toml` is loaded by one happy-path test.

- `test_load_defaults_from_tmp_file` — write a custom TOML
  file; `load_defaults(path=tmp_path/"x.toml")` returns a
  `Defaults` with the expected fields populated.
- `test_load_defaults_missing_file_raises_filenotfound` —
  `load_defaults(path=tmp_path/"nope.toml")` raises
  `FileNotFoundError` with the path in the message.
- `test_load_defaults_rejects_unknown_strategy` —
  TOML with `default = "chroma"`; `load_defaults` raises
  `ValidationError` (the `Literal["supabase", "sqlite"]`
  constraint).
- `test_load_defaults_supabase_url_required` — TOML
  omitting `[vector_store.supabase]` URL raises
  `ValidationError`.
- `test_coder_defaults_path_env_overrides` — set
  `CODER_DEFAULTS_PATH` to a custom file; `load_defaults()`
  reads it (no path arg). Reset env var at the end via
  `monkeypatch.delenv`.

### `tests/application/chunkers/test_fixed_size_text.py`

Pure-stdlib. No mocks.

- `test_chunk_text_short_returns_single_chunk` —
  `chunk_text("hello world", source="foo.md")` returns
  one chunk with the full text.
- `test_chunk_text_long_uses_overlap` — input
  `"a" * 2000`, `chunk_size=800`, `overlap=120` →
  three chunks: `("a"*680, #0)`, `("a"*680, #1)`,
  `("a"*640, #2)`. Verify the overlap windows share
  the expected character range.
- `test_chunk_text_empty_returns_empty_list` — empty
  input → `[]`.
- `test_chunk_text_source_propagates_to_all_chunks` —
  every chunk in the output has `source == "foo.md"`.
- `test_chunk_text_chunk_index_increments` — chunk
  indices are `0, 1, 2, ...` in order.
- `test_existing_chunk_compacted_session_unchanged` —
  smoke-test the existing `chunk(compacted: 
  CompactedSession)` method to confirm this DO has not
  regressed it (one assertion: returns `[]` for empty
  compacted; another: returns one chunk for a populated
  compacted with `keep_last_n_messages=2` semantics
  unchanged).

### `tests/application/test_learn_document.py`

Integration-level. Uses `mocker` for the LLM and
`ExtensionDispatchLoader`.

- `test_learn_document_loads_chunks_embeds_upserts` —
  stub `ExtensionDispatchLoader().load(path)` returning
  `("text", DocumentMetadata(...))`. Stub
  `FixedSizeChunker.chunk_text(...)` returning two
  chunks. Stub `Embedder.embed_passages(["t1", "t2"])`
  returning two vectors. Stub `VectorStore.upsert(
  chunks, vectors)` capturing the call. The test
  asserts the loader was called once with the path,
  the chunker was called once with the text + source,
  the embedder was called with the chunk texts, and
  the vector store was called with the chunks +
  vectors (in that order).

### `tests/application/test_knowledge_service_set_vector_store.py`

Uses `mocker` for `RecallCoordinator` and `BaseRetriever`.

- `test_set_vector_store_swaps_store_and_retriever` —
  build a `KnowledgeService` with an initial
  `vector_store` and `coordinator`. Call
  `set_vector_store(new_store, new_retriever)`. Assert
  `service._vector_store == new_store` and the new
  retriever was used to construct the new coordinator.
- `test_set_vector_store_preserves_other_dependencies`
  — after `set_vector_store`, the gate / top_k /
  threshold from the OLD coordinator are preserved on the
  NEW coordinator (the user only swapped the backend,
  not the retrieval tuning).

### `tests/application/test_prompts_source_format.py`

Pure-stdlib. No mocks.

- `test_build_chat_messages_includes_decision_rules` —
  when `recalled` is non-empty, the resulting
  SystemMessage contains the four pinned phrases:
  "Use the context when", "If the question can be
  answered without the context", "If the question
  requires specific document content", "When you use
  the context, mention".
- `test_build_chat_messages_formats_chunks_with_source` —
  given `recalled=[("foo.md", 2, "the chunk text")]`,
  the SystemMessage contains
  `"[Source: foo.md, chunk #2]\nthe chunk text"`.
- `test_build_chat_messages_chunks_separated_by_rule` —
  two chunks are joined with `"\n\n---\n\n"`.
- `test_build_chat_messages_empty_chunks_returns_no_header`
  — empty `recalled` returns the original
  `[...history, UserMessage(user_message)]` (no
  SystemMessage prepended). Backward compat with DO-09.
- `test_build_chat_messages_recalled_signature_change` —
  `recalled` is now `list[tuple[str, int, str]]`
  (source, chunk_index, text), not `list[str]`. The
  type signature is enforced; old `list[str]` calls
  raise `TypeError` (the coordinator is updated in
  the same commit).

### `tests/presentation/commands/test_learn_path.py`

- `test_learn_with_path_argument_ingests_file` — write a
  `.md` to `tmp_path`. Stub the loader, chunker,
  embedder, vector store. Run
  `LearnCommand().execute(CommandContext(repl=m,
    app_state=opaque, args=["<path>"]))`. Assert the
  vector store received the upsert call and the
  returned `CommandResult.message` contains
  `"learned <n> chunks"` and the file type.
- `test_learn_with_nonexistent_path_returns_friendly` —
  `args=["/nope/foo.md"]` → `CommandResult(message=
  "/nope/foo.md does not exist.")`. No exception.
- `test_learn_with_unsupported_extension_returns_friendly`
  — `args=["foo.docx"]` →
  `CommandResult(message="unsupported file type: '.docx'.
  Supported: pdf, md, markdown, txt.")`.
- `test_learn_with_no_args_uses_session_path` —
  `args=[]` → the existing session-compaction path
  runs (verify via mocker on `knowledge_service
  .learn` — same behaviour as DO-04).

### `tests/presentation/commands/test_vector_store.py`

Uses `mocker` for `KnowledgeService` and `cli._build_*`.

- `test_vector_store_no_args_prints_table` —
  `args=[]` →
  `CommandResult(message="active vector store:
  supabase\navailable: supabase, sqlite")`.
- `test_vector_store_supabase_rebuilds_chain` —
  `args=["supabase"]` →
  `KnowledgeService.set_vector_store` is called
  with the new `SupabaseVectorStore`. The active
  field becomes `"supabase"`.
- `test_vector_store_sqlite_rebuilds_chain` —
  `args=["sqlite"]` →
  `KnowledgeService.set_vector_store` is called
  with `SqliteVecStore`.
- `test_vector_store_unknown_returns_friendly` —
  `args=["bogus"]` →
  `CommandResult(message="unknown vector store
  'bogus'. Available: supabase, sqlite")`.
- `test_vector_store_supabase_missing_defaults_returns_friendly`
  — `args=["supabase"]` against a non-resolved
  `config/defaults.toml` (monkeypatch `CODER_DEFAULTS_PATH`
  to `/tmp/nope.toml`) →
  `CommandResult(message="no defaults file found.
  Set CODER_DEFAULTS_PATH or create
  config/defaults.toml.")`.

## Why these tests

- `test_document_metadata_*` and `test_chunk_with_source_*`
  pin the schema additions at the Pydantic level. The
  defaults (`source=""`, `chunk_index=0`) keep every
  prior test passing — the only assertion on the
  existing DO-04 / DO-12 tests is "no change".
- `test_extension_dispatch_*` pins the three-format
  coverage + the encoding / zero-pages / unsupported
  edge cases. The PDF test uses a committed fixture so
  the test suite is hermetic.
- `test_supabase_store_*` pins the SDK contract: lazy
  init, table-insert payload shape, RPC call shape,
  error mapping, secret repr masking. The lazy-init
  test catches accidental eager RPC in `__init__`.
- `test_defaults_*` pins the TOML shape + the env-var
  override + validation rejections.
- `test_fixed_size_text_*` pins the new chunker method
  + the regression guard for the existing
  `chunk(compacted)` path.
- `test_learn_document_*` pins the integration order
  (loader → chunker → embedder → vector store).
- `test_knowledge_service_set_vector_store_*` pins
  the new facade method.
- `test_prompts_source_format_*` pins the
  LLM-decides retrieval system prompt + the chunk
  formatting. The empty-recalled case pins the
  backward-compatible path.
- `test_learn_path_*` and `test_vector_store_*` pin
  the user-facing Command contracts.