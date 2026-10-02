# DO-13 contracts

## Architectural

- [ ] `DocumentLoader` Protocol lives in
      `domain/document_loader.py`. It has exactly one method,
      `load(path) -> tuple[str, DocumentMetadata]`. The Protocol
      imports only `DocumentMetadata` from `domain/`. No IO,
      no Pydantic beyond the imported model, no vendor imports.
- [ ] `DocumentMetadata` lives in `domain/document_metadata.py`
      and is a Pydantic `BaseModel` with
      `source: str`, `file_type: Literal["pdf", "md", "txt"]`,
      `page_count: int | None = None`, `byte_size: int`.
- [ ] `ExtensionDispatchLoader` lives in
      `infrastructure/document_loaders/extension_dispatch.py`.
      No file outside this module and the composition root
      (`cli.py`) imports it directly. The application layer
      reaches for the Protocol.
- [ ] `import-linter` gains two new contracts:
      - `forbidden_modules` for
        `infrastructure.document_loaders` from `domain`
        (mirrors the DO-12 `infrastructure.token_counters` rule).
      - `forbidden_modules` for `supabase` from
        `application`, `domain`, `presentation`. The
        `supabase` Python SDK is heavy and pins a
        `gotrue` / `realtime` / `postgrest` stack; only
        `infrastructure/vector_stores/supabase_store.py`
        may import it. Indirect imports through the store
        are tolerated (composition root builds the
        `SupabaseVectorStore`).
- [ ] `SupabaseVectorStore` lives in
      `infrastructure/vector_stores/supabase_store.py` and
      implements the existing `VectorStore` Protocol
      (`upsert(chunks, vectors)` and
      `query(vector, top_k) -> list[ScoredChunk]`). Same shape
      as the existing `SqliteVecStore` so the rest of the
      codebase is unaware of the backend.
- [ ] `KnowledgeService.set_vector_store(self, vector_store:
      VectorStore, retriever: BaseRetriever) -> None` mirrors
      the DO-11 `set_llm(...)` pattern. It rebuilds the
      `RecallCoordinator` against the new retriever. The
      chat-time `recall(...)` flow uses the new store on the
      next turn.
- [ ] `Defaults` and `load_defaults(...)` live in
      `infrastructure/defaults.py`. `Defaults` is a Pydantic
      model; `load_defaults` uses `tomllib` (Python 3.11+
      stdlib) to read `config/defaults.toml`. The composition
      root calls `load_defaults()` once at startup. No file
      outside `infrastructure/defaults.py` and `cli.py` reads
      the TOML file directly.
- [ ] No changes to `RecallCoordinator`, `BaseRetriever`,
      `TimeoutRetriever`, or `RetrievalExecutor`. The
      document-chunks pipeline flows through the existing
      chat-time retrieval machinery, with `Chunk.source` /
      `chunk_index` now populated.

## Behavioral

### `DocumentLoader` Protocol and `DocumentMetadata`

- [ ] `DocumentMetadata.model_dump_json()` round-trips through
      `model_validate(...)`. The `file_type` literal rejects
      unknown values.

### `ExtensionDispatchLoader`

- [ ] `load(Path("foo.md"))` returns
      `("<file contents>", DocumentMetadata(source=
      "<absolute>/foo.md", file_type="md",
      page_count=None, byte_size=<n>))`.
- [ ] `load(Path("foo.markdown"))` returns the same shape
      with `file_type="md"` (markdown aliases).
- [ ] `load(Path("foo.txt"))` returns
      `("<file contents>", DocumentMetadata(...,
      file_type="txt", page_count=None, byte_size=<n>))`.
- [ ] `load(Path("foo.pdf"))` returns the concatenated
      per-page text (pages joined with `"\f"`) and
      `DocumentMetadata(..., file_type="pdf",
      page_count=<int>, byte_size=<n>)`.
- [ ] Unknown extension raises `UnsupportedDocumentError`
      with the friendly message
      `"unsupported file type: '.<ext>'. Supported: pdf, md,
      markdown, txt."`.
- [ ] Missing file raises `FileNotFoundError` (propagated
      from the underlying open). The `LearnCommand` translates
      it into a friendly REPL message.
- [ ] Encoding errors in Markdown / text are tolerated via
      `errors="replace"` — a malformed byte becomes a `U+FFFD`
      (replacement glyph). The chunk is still produced.
- [ ] PDF with zero pages returns `("", DocumentMetadata
      (...page_count=0, byte_size=<n>))`. The caller
      (`LearnCommand`) treats this as a friendly error
      ("PDF has no extractable text").

### `FixedSizeChunker.chunk_text`

- [ ] `chunk_text("hello world", source="foo.md",
  chunk_size=800, overlap=120)` returns `[Chunk(text=
  "hello world", source="foo.md", chunk_index=0)]`.
- [ ] `chunk_text("a" * 2000, source="x", chunk_size=800,
  overlap=120)` returns three chunks:
      - `Chunk(text="a"*680, source="x", chunk_index=0)`,
      - `Chunk(text="a"*680, source="x", chunk_index=1)`,
      - `Chunk(text="a"*640, source="x", chunk_index=2)`,
      where each chunk advances by `chunk_size - overlap =
      680` chars, and the last chunk holds the tail.
- [ ] Empty text returns `[]`.
- [ ] The existing `chunk(compacted: CompactedSession)`
      method still passes every DO-05 / DO-09 test with **zero**
      change (this DO does not touch the session-chunking path).

### `Chunk.source` / `Chunk.chunk_index`

- [ ] `Chunk(text="x", chunk_index=2, source="valid_kwarg")`
      constructs without error.
- [ ] `Chunk.model_validate({"text": "x", "chunk_index": 2,
      "source": "foo"})` succeeds.
- [ ] `Chunk.model_validate({"text": "x"})` still succeeds
      (default `source=""`, `chunk_index=0`).

### `SupabaseVectorStore`

- [ ] `__init__` does **not** network. The `supabase`
      client is constructed but no RPC is sent. The first
      network call happens in `upsert` or `query`.
- [ ] `upsert(chunks, vectors)` succeeds against a mocked
      `supabase.create_client(url, key).table(name).insert(
      {...}).execute()` chain. The insert payload includes
      `source`, `chunk_index`, `content`, `embedding` for
      each row. The schema's `ON CONFLICT (source,
      chunk_index) DO UPDATE` is exercised at the SQL level
      (verified via the bootstrap script + integration test).
- [ ] `query(vector, top_k)` returns `list[ScoredChunk]`
      where each `ScoredChunk` has `source`,
      `chunk_index`, `content`, `score` populated from the
      `match_chunks` PL/pgSQL function response.
- [ ] Network / schema failures map to
      `VectorStoreBackendUnavailable` so
      `cli._build_vector_store`'s existing fallback chain
      still works (Supabase fail → sqlite → brute force).
- [ ] The `key` parameter never appears in
      `repr(...)` or `str(...)` output (mirror of the
      ProviderConfig `SecretStr` discipline).

### `Defaults` and `load_defaults`

- [ ] `load_defaults(path=tmp_path / "custom.toml")` reads
      the specified file.
- [ ] `load_defaults()` (no path) reads
      `<cwd>/config/defaults.toml` if it exists; otherwise
      reads `<package>/config/defaults.toml` (the
      committed copy).
- [ ] Missing TOML file raises `FileNotFoundError` with
      the resolved path in the message.
- [ ] `CODER_DEFAULTS_PATH` env var overrides the path
      resolution.
- [ ] Malformed TOML raises `tomllib.TOMLDecodeError` —
      not wrapped.

### `LearnCommand` — `/learn <path>` argument

- [ ] `/learn` (no args) — existing behaviour (compacts
      current session).
- [ ] `/learn <path>` — calls
      `ExtensionDispatchLoader().load(Path(path))`,
      `chunker.chunk_text(text, source=meta.source)`,
      warms the embedder (block up to 60s), embeds, upserts.
      Returns `CommandResult(message="learned <n> chunks
      from <path> (<file_type>, <byte_size> bytes,
      page_count=<p|csv>).")`.
- [ ] Non-existent path →
      `CommandResult(message="<path> does not exist.",
      action="continue")`. No exception raised.
- [ ] Unsupported file type → `CommandResult(message=
      <UnsupportedDocumentError message>)`. No exception
      raised.
- [ ] Empty text from PDF → `CommandResult(message=
      "PDF has no extractable text.")` (no upsert).
- [ ] The /learn chat-time RAG index is unchanged —
      session-compacted chunks still flow into the same
      `VectorStore.upsert` with empty `source=""` and
      `chunk_index=0`.

### `VectorStoreCommand`

- [ ] `name == "vector-store"`, `summary == "Switch the
      active vector store (supabase | sqlite)"`.
- [ ] `/vector-store` (no args) →
      `CommandResult(message="active vector store:
      supabase\navailable: supabase, sqlite")` (or the
      current active).
- [ ] `/vector-store supabase` — rebuilds the vector
      store, retriever, and `RecallCoordinator`; calls
      `KnowledgeService.set_vector_store(...)`; sets
      `app_state.active_vector_store = "supabase"`; prints
      `active vector store: supabase`.
- [ ] `/vector-store sqlite` — same flow with
      `SqliteVecStore` (or `NumpyBruteForceStore`
      fallback).
- [ ] `/vector-store bogus` →
      `CommandResult(message="unknown vector store
      'bogus'. Available: supabase, sqlite")`. No
      exception raised.
- [ ] `/vector-store supabase` against a missing
      `config/defaults.toml` →
      `CommandResult(message="no defaults file found.
      Set CODER_DEFAULTS_PATH or create
      config/defaults.toml.")`.

### LLM-decides retrieval (system prompt)

- [ ] `build_chat_messages(user_message, history,
      recalled=[(source, chunk_index, text), ...])`
      (recalled is now a list of tuples, not just strings —
      see verified below) returns:
      - `SystemMessage(content=<header + chunks>` when
        `recalled` is non-empty.
      - `[*history, UserMessage(user_message)]` when
        `recalled` is empty.
- [ ] The header includes the four decision rules
      ("Use the context when …", "If the question can
      be answered without the context …", "If the
      question requires specific document content that
      was NOT retrieved …", "When you use the context,
      mention the source(s) you drew from.").
- [ ] Each chunk is formatted as
      `"[Source: <source>, chunk #<chunk_index>]\n<content>"`.
- [ ] `build_chat_messages` does **not** raise when
      `source` or `chunk_index` is empty (the
      backward-compatible path for chunks without source
      metadata — they format as
      `"[Source: , chunk #0]\n<text>"` which the LLM
      treats as "anonymous chunk").

### Sample documents

- [ ] `data/documents/architecture.md` exists in the
      repo. Contains a section titled "Cache layer".
- [ ] `data/documents/style-guide.txt` exists in the
      repo. Contains "Naming conventions" or similar.
- [ ] `data/documents/api-reference.pdf` exists in the
      repo and is a valid PDF (verified by
      `pypdf.PdfReader(...)` succeeding with `pages`
      non-empty in the smoke test).
- [ ] The PDF is generated by
      `scripts/build_sample_pdf.py` (the generator is
      committed; the output PDF is committed; running
      the generator overwrites the output).

## Schema

### `DocumentMetadata` (DO-13) — new Pydantic model

- [ ] `domain/document_metadata.py`:
      ```python
      class DocumentMetadata(BaseModel):
          source: str
          file_type: Literal["pdf", "md", "txt"]
          page_count: int | None = None
          byte_size: int
      ```

### `Chunk` (DO-13) — schema patch

- [ ] `domain/chunk.py` gains:
      ```python
      source: str = ""
      chunk_index: int = 0
      ```
      Default empty so DO-04 / DO-09 / DO-12 tests pass
      without change.

### `Defaults` (DO-13) — new Pydantic model

- [ ] `infrastructure/defaults.py`:
      ```python
      class VectorStoreDefaults(BaseModel):
          url: str
          key: str
          table_name: str = "chunks"

      class VectorStoreConfig(BaseModel):
          default: Literal["supabase", "sqlite"] = "supabase"
          supabase: VectorStoreDefaults
          sqlite: dict[str, str] = Field(default_factory=dict)

      class EmbeddingDefaults(BaseModel):
          model: str = "BAAI/bge-small-en-v1.5"

      class Defaults(BaseModel):
          vector_store: VectorStoreConfig
          embedding: EmbeddingDefaults = EmbeddingDefaults()
      ```

### `AppState` (DO-13) — field additions

- [ ] `presentation/commands/__init__.py` `AppState`
      gains `vector_store: VectorStore | None = None` and
      `active_vector_store: str = "supabase"`. Existing
      fields are unchanged.

### `Settings` (DO-13) — one new field

- [ ] `infrastructure/settings.py` gains
      `vector_store_strategy: Literal["supabase", "sqlite"] =
      "supabase"` (env `CODER_VECTOR_STORE_STRATEGY`).
- [ ] The legacy `vector_store: "sqlite_vec" | "brute_force"`
      field stays — it now reads as the **sqlite-side** choice
      (when `VECTOR_STORE_STRATEGY=sqlite`,
      `VECTOR_STORE=sqlite_vec` picks sqlite-vec,
      `VECTOR_STORE=brute_force` picks in-memory numpy).
      Migration: a pydantic validator coerces
      `vector_store_strategy="supabase"` into the new
      behaviour; the old `VECTOR_STORE=sqlite_vec` still
      passes validation but is now interpreted as "sqlite-vec
      backend when sqlite strategy is active".

### `KnowledgeService.set_vector_store` — new method

- [ ] `application/knowledge_service.py`:
      ```python
      def set_vector_store(
          self, vector_store: VectorStore,
          retriever: BaseRetriever,
      ) -> None:
          self._vector_store = vector_store
          self._coordinator = RecallCoordinator(
              retriever=retriever,
              gate=self._coordinator._gate,
              top_k=self._coordinator._top_k,
              similarity_threshold=
                  self._coordinator._similarity_threshold,
          )
      ```
      (Mirrors the DO-11 `set_llm` pattern. Keeps the
      gate / top-k / threshold the same — the user only
      swapped the backend.)