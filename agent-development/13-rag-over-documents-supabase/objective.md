# DO-13 — RAG over local documents, Supabase + pgvector, LLM-decides retrieval

## Goal

Extend the existing chat-time RAG with a **document ingestion pipeline** that
reads PDF, Markdown, and text files from disk, chunks them with overlap, embeds
them, and stores them in a vector database with source metadata. The chat loop
injects the retrieved chunks (with sources) as a `SystemMessage` and lets the
**LLM decide** how to use them — preferring context for document-specific
questions, falling back to general knowledge for general questions, and refusing
when the question requires context that was not retrieved.

The default vector store is **Supabase + pgvector**, deployed and reachable by
URL (TL acceptance criterion #8: "every project service it consumes must be
deployed and reachable through a documented URL"). The Supabase project URL and
public anon key live in a committed `config/defaults.toml` so the
clone-install-execute flow works out of the box. The anon key is, by design, a
public value — committing it to the repo is the same exposure model as putting
it in a front-end bundle.

SQLite-vec stays as a switchable local backend (a new `/vector-store <name>`
slash command flips between them). The chat-time retrieval pipeline
(`RecallCoordinator`, `BaseRetriever`, `TimeoutRetriever`) is unchanged — the
new chunks flow through the same path, with `source` / `chunk_index` metadata
propagated through `Chunk` to the LLM context.

`LearnCommand` grows a `<path>` argument. Without arguments it keeps the
existing "compact current session into RAG JSON" behaviour. With an argument it
loads the file, chunks it with 800-token / 15%-overlap windows, embeds, and
upserts to the active vector store.

Satisfies TL acceptance criterion #4 ("RAG returns relevant chunks with
source metadata and the chatbot does not invent unsupported answers") and
TL acceptance criterion #8 (a deployed vector store, documented by URL).

## Source of truth

- `OBJECTIVES.md` — Strategy pattern (`DocumentLoader` Protocol dispatch,
  `VectorStore` Strategy, `Chunker` Strategy), Facade pattern
  (`KnowledgeService` orchestrates the document pipeline), Command pattern
  (`/learn <path>`, `/vector-store`).
- `NEW_REQUIREMENTS.md` §4 *RAG over local documents* and §8 *Deployed services*.
- `docs/development-tools.md` §5 (embedder), §6 (Supabase SDK), §8 (no
  extra retry libraries).
- DO-09 — `RecallCoordinator`, `BaseRetriever`, `TimeoutRetriever`,
  `RecallCoordinator`'s trivial-prompt gate and similarity threshold.
- DO-11 — `LLMClient` Protocol, `ProviderRegistry`,
  `KnowledgeService.set_llm(...)` (mirrored by
  `KnowledgeService.set_vector_store(...)` here).
- DO-12 — `AppState`, the four `SessionManager` Settings fields, the
  `chunk.source` / `chunk.chunk_index` fields added in DO-12 schema.
- `supabase.com/docs` + `github.com/pgvector/pgvector` — web-search step
  in `workflow.md`.

## Acceptance criteria

### Document ingestion

- [ ] `src/simple_cli_coder_with_rag/domain/document_loader.py` defines
      `class DocumentLoader(Protocol)` with
      `def load(self, path: Path) -> tuple[str, DocumentMetadata]`.
      `DocumentMetadata` is a Pydantic `BaseModel` with
      `source: str` (absolute file path), `file_type: Literal["pdf",
      "md", "txt"]`, `page_count: int | None = None`,
      `byte_size: int`.
- [ ] `src/simple_cli_coder_with_rag/infrastructure/document_loaders/__init__.py`
      re-exports `ExtensionDispatchLoader`.
- [ ] `src/simple_cli_coder_with_rag/infrastructure/document_loaders/extension_dispatch.py`
      defines `class ExtensionDispatchLoader` implementing
      `DocumentLoader`:
      - Dispatches by file extension: `.pdf` → inline PDF loader,
        `.md` / `.markdown` → inline Markdown loader, `.txt` → inline
        text loader. One class with three private methods — YAGNI on
        a Loader Registry for v1.
      - Markdown / text load the file verbatim (UTF-8, `errors="replace"`
        so a malformed byte does not crash the pipeline).
      - PDF loads via `pypdf.PdfReader(path).pages` and joins
        per-page text with a form-feed (`\f`) separator so the
        chunker can later break on page boundaries if needed.
        `page_count` is the page count; `byte_size` is the file size.
- [ ] `pyproject.toml` adds `"pypdf>=5.0,<6"` to `dependencies`.
- [ ] `src/simple_cli_coder_with_rag/application/chunkers/fixed_size.py`
      `FixedSizeChunker` gains a new method `chunk_text(self, text:
      str, *, source: str, chunk_size: int = 800, overlap: int = 120)
      -> list[Chunk]`. Existing `chunk(compacted: CompactedSession)`
      stays unchanged so all DO-05/DO-09 tests pass without change.
      Overlap default `120` is `chunk_size * 0.15` (the 10-20% range
      from TL).
- [ ] `src/simple_cli_coder_with_rag/domain/chunk.py` `Chunk` gains
      `source: str = ""` and `chunk_index: int = 0` fields (default
      empty so session-compacted chunks from DO-04 still round-trip
      with no source). Existing tests for session chunks pass
      unchanged.

### Vector store: Supabase + pgvector (default)

- [ ] `pyproject.toml` adds `"supabase>=2.0,<3"` to `dependencies`.
- [ ] `src/simple_cli_coder_with_rag/infrastructure/vector_stores/supabase_store.py`
      defines `class SupabaseVectorStore` implementing the existing
      `VectorStore` Protocol:
      - `__init__(self, *, url: str, key: str, table_name: str =
        "chunks") -> None`. `client = supabase.create_client(url,
        key)`. Connection is verified lazily on the first call
        (`upsert` or `query`) — `__init__` does not network.
      - `upsert(self, chunks: list[Chunk], vectors: list[list[float]])
        -> None` — inserts each row via `client.table(self._table)
        .insert({"source": c.source, "chunk_index": c.chunk_index,
        "content": c.text, "embedding": vec})`. Idempotent at the
        SQL level via `ON CONFLICT (source, chunk_index) DO UPDATE
        SET content = EXCLUDED.content, embedding = EXCLUDED
        .embedding, created_at = now()` (the
        `supabase_schema.sql` primary key is `(source,
        chunk_index)`).
      - `query(self, vector: list[float], *, top_k: int) ->
        list[ScoredChunk]` — executes `client.rpc("match_chunks",
        {"query_embedding": vector, "match_count": top_k})`. The
        PL/pgSQL function `match_chunks` returns rows of
        `(source, chunk_index, content, score)` where `score` is
        `1 - (embedding <=> query_embedding)`. The
        `VectorStoreBackendUnavailable` exception is mapped from
        the `requests`/`supabase` errors that indicate network /
        schema failures so the existing graceful-fallback chain in
        `cli._build_vector_store` still works.
- [ ] `src/simple_cli_coder_with_rag/infrastructure/vector_stores/__init__.py`
      adds `SupabaseVectorStore` to the exports.
- [ ] `cli._build_vector_store(settings, defaults)` builds
      `SupabaseVectorStore` from `defaults.vector_store.supabase`
      when `settings.vector_store_strategy == "supabase"` (the
      new default). When `settings.vector_store_strategy ==
      "sqlite"` (or set via `/vector-store sqlite`), builds
      `SqliteVecStore` (with the existing fallback to
      `NumpyBruteForceStore`). Logs the active backend at INFO via
      `loguru`.

### Supabase schema bootstrap

- [ ] `src/simple_cli_coder_with_rag/infrastructure/vector_stores/supabase_schema.sql`
      is a single SQL script committed to the repo with:
      - `CREATE EXTENSION IF NOT EXISTS vector;`
      - `CREATE TABLE IF NOT EXISTS chunks (
          source text NOT NULL,
          chunk_index int NOT NULL,
          content text NOT NULL,
          embedding vector(384) NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (source, chunk_index)
        );`
      - `CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks
        USING ivfflat (embedding vector_cosine_ops) WITH (lists =
        100);` (HNSW is also acceptable — verified in `workflow.md`
        web-search step; default to IVFFlat for the small-data
        shape this CLI produces).
      - `CREATE OR REPLACE FUNCTION match_chunks(query_embedding
        vector, match_count int) RETURNS TABLE(source text,
        chunk_index int, content text, score double precision) AS
        $$
        BEGIN
          RETURN QUERY
          SELECT c.source, c.chunk_index, c.content,
                 1 - (c.embedding <=> query_embedding) AS score
          FROM chunks c
          ORDER BY c.embedding <=> query_embedding
          LIMIT match_count;
        END;
        $$ LANGUAGE plpgsql;`
      - `GRANT EXECUTE ON FUNCTION match_chunks TO anon;`
      - `GRANT INSERT, SELECT ON chunks TO anon;`
- [ ] `scripts/bootstrap_supabase.py` (new) — an idempotent
      setup script the maintainer runs once to apply
      `supabase_schema.sql` against a Supabase project (reads
      `SUPABASE_DB_URL` from env, executes via `psycopg2` or
      `supabase-py`'s SQL helper). **Not** invoked by `uv run
      coder` — the maintainer does it once during project
      bootstrap. The committed anon key already grants the anon
      role the access it needs on the already-bootstrapped
      instance.
- [ ] `README.md` documents the one-time maintainer setup:
      "Run `python scripts/bootstrap_supabase.py` once against
      your Supabase project. The script is idempotent — it can
      be re-run safely. The anon key in `config/defaults.toml`
      is committed for the demo instance only; replace it with
      your own project's anon key."

### Defaults file (TOML)

- [ ] `config/defaults.toml` (new, committed) holds public,
      non-secret defaults:
      ```toml
      # Public, non-secret defaults. Override path via
      # CODER_DEFAULTS_PATH. To rotate the Supabase anon key for
      # your own Supabase project, edit this file (or point
      # CODER_DEFAULTS_PATH at your own copy).

      [vector_store]
      default = "supabase"   # one of: supabase | sqlite

      [vector_store.supabase]
      url = "https://<project-ref>.supabase.co"
      key = "<public-anon-key>"
      table_name = "chunks"

      [vector_store.sqlite]
      # local sqlite-vec, no URL needed

      [embedding]
      model = "BAAI/bge-small-en-v1.5"
      ```
- [ ] `src/simple_cli_coder_with_rag/infrastructure/defaults.py`
      defines `class Defaults(BaseModel)` (Pydantic) and
      `def load_defaults(path: Path | None = None) -> Defaults`.
      Uses `tomllib` (Python 3.11+ stdlib) to load
      `config/defaults.toml`. Env var `CODER_DEFAULTS_PATH`
      overrides the path. Default path resolution:
      `<cwd>/config/defaults.toml` first, then
      `<package>/config/defaults.toml` (the file is committed
      alongside the package).
- [ ] `.gitignore` does **not** ignore `config/defaults.toml`
      (committed).

### Slash commands

- [ ] `src/simple_cli_coder_with_rag/presentation/commands/learn.py`
      `LearnCommand` accepts an optional `<path>` argument:
      - `/learn` (no args) — existing behaviour (compact current
        session into RAG JSON via `KnowledgeService.learn`).
      - `/learn <path>` — `expanduser()`, validates the path
        exists and is a regular file, calls
        `ExtensionDispatchLoader().load(Path(path))`, chunks
        via `chunker.chunk_text(text, source=meta.source)`,
        warms the embedder (block up to 60s on cold cache),
        embeds via `Embedder.embed_passages(...)`, upserts via
        `vector_store.upsert(chunks, vectors)`. Returns
        `CommandResult(message="learned <n> chunks from <path>
        (<file_type>, <byte_size> bytes, page_count=<p|csv>).")`.
      - Non-existent / non-regular paths → friendly message, no
        crash.
      - Multiple paths / glob patterns are **out of scope v1**.
- [ ] `src/simple_cli_coder_with_rag/presentation/commands/vector_store.py`
      defines `class VectorStoreCommand`:
      - Name `vector-store`, summary "Switch the active vector
        store (supabase | sqlite)".
      - `/vector-store` — print `active vector store:
        <active>` and `available: supabase, sqlite`.
      - `/vector-store supabase` — build
        `SupabaseVectorStore` from `defaults.vector_store
        .supabase`, rebuild the retriever chain (`BaseRetriever`
        wrapped in `TimeoutRetriever`), call
        `KnowledgeService.set_vector_store(new_store,
        new_retriever)`, set
        `app_state.active_vector_store = "supabase"`. Print
        `active vector store: supabase`.
      - `/vector-store sqlite` — same flow with
        `SqliteVecStore` (or `NumpyBruteForceStore` fallback).
      - Invalid name → friendly message; no crash.
      - Persistence: the active choice lives in
        `app_state.active_vector_store` for the session;
        `config/defaults.toml` `[vector_store] default` is
        read on every startup so the choice survives an app
        restart.

### LLM-decides retrieval (system prompt)

- [ ] `src/simple_cli_coder_with_rag/application/prompts.py` extends
      `build_chat_messages` to format retrieved chunks with source
      metadata and the LLM-decides instructions. The new
      `_RECALL_HEADER`:
      ```python
      _RECALL_HEADER = (
          "You have access to the following context from the user's "
          "loaded documents and previous sessions.\n\n"
          "Decision rules:\n"
          "  - Use the context when the question references or "
          "requires specific information from the user's documents "
          "or previous sessions.\n"
          "  - If the question can be answered without the context, "
          "answer from your general knowledge.\n"
          "  - If the question requires specific document content "
          "that was NOT retrieved, say you don't have enough "
          "information rather than guessing.\n"
          "  - When you use the context, mention which source(s) "
          "you drew from.\n\n"
          "Context:\n\n"
      )
      _RECALL_CHUNK_FORMAT = (
          "[Source: {source}, chunk #{chunk_index}]\n{content}"
          )
      _RECALL_SEPARATOR = "\n\n---\n\n"
      ```
      Each retrieved chunk is formatted as
      `_RECALL_CHUNK_FORMAT.format(source=c.source,
      chunk_index=c.chunk_index, content=c.text)`. Chunks are
      joined with `_RECALL_SEPARATOR`. The whole block is
      prepended as a single `SystemMessage`.
- [ ] `RecallCoordinator` (DO-09) passes through the new
      `Chunk.source` / `Chunk.chunk_index` to `build_chat_messages`
      — no behavioural change to the coordinator itself; only the
      shape of what it returns.
- [ ] The "don't invent" rule is enforced by the LLM following
      the system-prompt rules — **no** Python branch that forbids
      generation. This matches the user's design decision ("let
      the LLM decide").

### Sample documents

- [ ] `data/documents/architecture.md` — committed sample
      Markdown describing a fictional cache-layer architecture.
      ~500 words. Source: hand-written.
- [ ] `data/documents/style-guide.txt` — committed plain-text
      style guide with naming conventions. ~200 words. Source:
      hand-written.
- [ ] `data/documents/api-reference.pdf` — committed sample
      PDF (~50 KB) generated from a text file via
      `scripts/build_sample_pdf.py` (one-time generator; the
      PDF output is committed so the test suite and README
      walkthrough have a stable binary to load).
- [ ] These three documents satisfy TL "ingest at least 3
      local documents such as PDF, Markdown or text files".

### Wire-up

- [ ] `AppState` gains two fields:
      `vector_store: VectorStore | None = None`,
      `active_vector_store: str = "supabase"` (default from
      `defaults.toml`).
- [ ] `KnowledgeService.__init__` gains a `set_vector_store(
      self, vector_store: VectorStore, retriever:
      BaseRetriever) -> None` method (mirrors `set_llm` from
      DO-11). Rebuilds the `RecallCoordinator` against the new
      retriever. The chat-time `recall(...)` flow uses the new
      store on the next turn.
- [ ] `_bootstrap_app_state` reads
      `defaults.vector_store.default`, constructs the matching
      adapter, and wires it into `AppState.vector_store`. When
      `active_vector_store == "supabase"` and the Supabase
      init fails (`VectorStoreBackendUnavailable`), the cli
      logs an INFO line and falls back to `sqlite` for this
      session; the user can re-run with
      `CODER_VECTOR_STORE_STRATEGY=sqlite` to make it sticky.
- [ ] `Settings` gains `vector_store_strategy: Literal["supabase",
      "sqlite"] = "supabase"` — env `CODER_VECTOR_STORE_STRATEGY`.
      This is the **only** new env var in this DO.
- [ ] `_resolve_db_path` stays unchanged (used by sqlite
      alternative).
- [ ] `.env.example` gains `CODER_VECTOR_STORE_STRATEGY=`
      and `CODER_DEFAULTS_PATH=` (both optional, with
      documented defaults in the comment).

### Documentation

- [ ] `docs/rag.md` (new) covers:
      - Document ingestion: loader → chunker-with-overlap →
        embedder → vector store pipeline diagram (text
        format).
      - LLM-decides retrieval: the system-prompt rules verbatim
        + a worked example for each outcome (use context,
        general knowledge, refuse).
      - The `config/defaults.toml` shape + how to point at
        your own Supabase project (replace the URL + anon
        key).
      - The `scripts/bootstrap_supabase.py` one-time
        maintainer setup.
      - The `/vector-store` switch command semantics.
      - Sample documents locations under `data/documents/`.
- [ ] `docs/providers.md` (DO-11) gains a "Supabase" entry
      linking to `docs/rag.md`.
- [ ] `README.md` updates:
      - "Slash commands" table gains `/learn <path>` (with the
        existing `/learn` behaviour preserved) and
        `/vector-store` rows.
      - "RAG over documents" section links to `docs/rag.md`.
      - "Testing the RAG flow" section walks through five
        example turns:
        1. `uv run coder`
        2. `/learn data/documents/architecture.md` — expect
           "learned N chunks from …"
        3. `What does the cache layer look like?` — expect
           the LLM to cite `architecture.md` and quote a
           chunk.
        4. `What is the capital of France?` — expect a
           general-knowledge answer without citing a source.
        5. `According to docs/secret-doc.md, what is X?` —
           expect "I don't have enough information —
           docs/secret-doc.md was not loaded." (no source
           cited, no made-up answer).
      - "Deployed services" table gains: `Supabase (pgvector)`
        URL `https://<project-ref>.supabase.co`, env var
        `CODER_DEFAULTS_PATH` to override the defaults file.
      - The legacy "RAG flow over local documents" gap is
        closed by the new section.
- [ ] `.env.example` updated as above.

### Gate

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

- Document Loader Registry (a Strategy seam for the per-format
  loaders). `ExtensionDispatchLoader` is a single class with
  three private methods; if a fourth format lands (DOCX, HTML,
  …), a future DO can split it.
- Auto-loading from `data/documents/` at startup. The user
  explicitly ingests with `/learn <path>` v1.
- Glob patterns (`/learn --glob "docs/*.md"`). Single-path v1.
- Source management (`/forget <source>`, `/sources` to list
  ingested sources). A future DO can add these once the use
  case is defined.
- Streaming ingestion for large documents (PDF > 100 pages,
  etc.). A future DO can add it.
- Per-document custom chunk size. Fixed `chunk_size=800` /
  `overlap=120`; configurable later.
- Supabase `service_role` key rotation / per-user secrets.
  The anon key is committed; a future DO can add a `secrets`
  field to `providers.json` if higher-privilege operations are
  needed (e.g. admin-level SQL).
- Replacing the existing `RecallCoordinator` /
  `BaseRetriever` / `TimeoutRetriever` chain. They are unchanged
  in this deliverable — only their backing `VectorStore`
  changes when `/vector-store` is run.

## Depends on

- DO-09 — `RecallCoordinator`, `BaseRetriever`,
  `TimeoutRetriever`, the chat-time retrieval path.
- DO-11 — `LLMClient` Protocol, `KnowledgeService.set_llm`
  pattern (mirrored by `KnowledgeService.set_vector_store`).
- DO-12 — `AppState` fields, the four Settings fields
  (`keep_last_n_messages` etc., unchanged), the
  `Chunk.source` / `Chunk.chunk_index` schema fields added in
  DO-12 schema patch.

## Blocks

- TL acceptance criterion #4 (RAG over docs with source
  metadata, no invented answers).
- TL acceptance criterion #8 (a deployed service for the
  vector store).
- DO-14 (skills) and DO-15 (coding-assistance trace) do not
  depend on this deliverable and can be implemented in parallel
  after v1 ships.