# DO-13 workflow

## Subagent delegation

**Three subagents.** The work splits along the Strategy seams
introduced by this deliverable:

| # | Owns | Why split out |
|---|---|---|
| **A** | `domain/document_loader.py` (Protocol) + `domain/document_metadata.py` (Pydantic) + `infrastructure/document_loaders/extension_dispatch.py` (loader) + `application/chunkers/fixed_size.py` `chunk_text` method (extension) + `domain/chunk.py` schema patch (`source` / `chunk_index` defaults). | Pure data layer; one new dependency (`pypdf`). Tightly self-contained — no Supabase, no LLM. |
| **B** | `infrastructure/vector_stores/supabase_store.py` (new adapter) + `infrastructure/vector_stores/supabase_schema.sql` (SQL bootstrap) + `scripts/bootstrap_supabase.py` (one-time maintainer setup) + `infrastructure/defaults.py` (`Defaults` + `load_defaults`) + `config/defaults.toml` (committed) + the pyproject.toml `supabase` dependency bump + the new `Settings.vector_store_strategy` field. | Distribution via Supabase; one new SDK. No presentation, no document loader. |
| **C** | `application/knowledge_service.py` `set_vector_store` method (extension) + `application/prompts.py` LLM-decides system-prompt patch (extension) + `presentation/commands/learn.py` `<path>` argument (extension) + `presentation/commands/vector_store.py` (new command) + `cli._bootstrap_app_state` rewrite + `cli._build_vector_store` extension (defaults comes from TOML) + `AppState` field additions + `data/documents/` sample files + `scripts/build_sample_pdf.py` + `README.md` + `docs/rag.md` + `docs/providers.md` patch + `.env.example`. | Presentation / role + composition + docs. Depends on A and B. |

Order: **A → (B and C cannot parallelise: C consumes the loader and
chunk_text from A, plus the defaults file from B; it can start once A
finishes, B can run in parallel with A)**.

Practically: **A and B can run in parallel** (they touch disjoint
files: A touches document_loader / document_loaders / chunkers / chunk;
B touches vector_stores / defaults / config / scripts / settings).
**C runs after A and B finish** — it uses the loader, the chunker
extension, the new vector store, the defaults file, and the Settings
field.

### Context passed to each subagent

**Subagent A** — Document loader + new chunk_text + Chunk schema:
- `agent-development/README.md` (master).
- The four files in this folder.
- `docs/development-tools.md` §5 (embedder), §6 (Pydantic).
- `domain/chunk.py`, `domain/chunker.py`,
  `application/chunkers/fixed_size.py` (A extends the existing
  `FixedSizeChunker`).
- `application/compactor.py` (to confirm the existing
  `chunk(compacted: CompactedSession)` method signature A must not
  regress).
- Nothing else.

**Subagent B** — Supabase adapter + SQL bootstrap + defaults:
- `agent-development/README.md` (master).
- The four files in this folder.
- `docs/development-tools.md` §6, §8.
- `domain/vector_store.py` (the Protocol B implements).
- `infrastructure/vector_stores/sqlite_vec_store.py` (the sibling
  adapter B mirrors).
- `pyproject.toml` (add `supabase>=2.0,<3`).
- `tests/fixtures/api-reference.pdf` (a small test PDF, already
  committed by A; B verifies the SDK loads it).
- Nothing else (do **not** re-read the document loader — B
  only knows the `VectorStore` Protocol).

**Subagent C** — Commands + composition + docs:
- `agent-development/README.md` (master).
- The four files in this folder.
- `docs/development-tools.md` §6, §7, §8.
- `application/knowledge_service.py` (C adds `set_vector_store`).
- `application/prompts.py` (C extends `build_chat_messages`).
- `presentation/commands/learn.py` (C adds the `<path>`
  argument).
- `presentation/commands/__init__.py` (`AppState`).
- `presentation/repl.py` (no change expected — but C reads it
  to confirm).
- `cli.py` (C rewires `_build_vector_store` and
  `_bootstrap_app_state`).
- `infrastructure/defaults.py` (from B).
- `infrastructure/vector_stores/supabase_store.py` (from B).
- `infrastructure/document_loaders/extension_dispatch.py` (from A).
- `application/chunkers/fixed_size.py` (from A).
- `domain/chunk.py` (from A).
- `README.md` and `.env.example` and `docs/providers.md` and
  `docs/rag.md` (C owns / edits).

## Web-search verification (before pinning)

1. **Supabase Python SDK current version** — `pypi.org/project/supabase`.
   Pin to `>=2.0,<3` as in the contracts; verify the
   `client.rpc("match_chunks", {...})` pattern is the v2 idiomatic
   way to call PL/pgSQL functions (alternative patterns:
   `client.postgrest.rpc(...)` was the v1 name; v2 uses
   `client.rpc(...)`).

2. **`pgvector` index choice for small data** — the
   bootstrap SQL pins `ivfflat (lists = 100)`. Verify in the
   pgvector README that this is the recommended default for
   < 1M rows (it is). Note that the index is created with
   `lists = 100` — a heuristic for ~1M rows. The chunks we
   store per document are < 1000 in practice, so the index
   shape is appropriate. HNSW is also acceptable but
   requires a `WITH (m = 16, ef_construction = 64)` clause;
   stick with IVFFlat for v1.

3. **`pypdf` current version** — `pypi.org/project/pypdf`.
   Pin to `>=5.0,<6`; verify `PdfReader(path).pages` returns
   a list with `.extract_text()` per page.

Include a `provider-research:` block in the commit body:

```
provider-research:
  supabase: NEW  sdk=supabase>=2.0,<3  schema=PL/pgSQL match_chunks
             pgvector=ivfflat (lists=100)  storage=tbl chunks(source, chunk_index)
  pypdf:    NEW  pypi>=5.0,<6  extraction=PdfReader(path).pages[*].text()
strategy:  ExtensionDispatchLoader for document loaders;
           SupabaseVectorStore + sqlite-vec as alternative
           (switchable via /vector-store).
```

## Steps

1. **Pre-flight.** `git status` clean.
2. **Web-search** the three research items above. Reconcile
   the `provider-research:` block.
3. **Read** `docs/development-tools.md` §5, §6, §7, §8.
4. **Write the test files** from `tests.md` first. Confirm
   they fail (`uv run pytest -q` shows collection errors).
   Split:
   - A writes
     `tests/domain/test_document_metadata.py`,
     `tests/domain/test_chunk_with_source.py`,
     `tests/infrastructure/document_loaders/test_extension_dispatch.py`,
     and
     `tests/application/chunkers/test_fixed_size_text.py`.
     A also commits the three test fixtures under
     `tests/fixtures/` (run `scripts/build_sample_pdf.py`
     once to materialise the PDF).
   - B writes
     `tests/infrastructure/vector_stores/test_supabase_store.py`,
     `tests/infrastructure/test_defaults.py`.
   - C writes
     `tests/application/test_learn_document.py`,
     `tests/application/test_knowledge_service_set_vector_store.py`,
     `tests/application/test_prompts_source_format.py`,
     `tests/presentation/commands/test_learn_path.py`,
     `tests/presentation/commands/test_vector_store.py`.
5. **Subagent A** (Document loader + chunk_text + Chunk
   schema patch):
   - Add `"pypdf>=5.0,<6"` to `pyproject.toml`. Run
     `uv lock`.
   - Create `domain/document_metadata.py`.
   - Create `domain/document_loader.py` (Protocol).
   - Create `infrastructure/document_loaders/__init__.py`
     and `infrastructure/document_loaders/extension_dispatch.py`.
   - Extend `application/chunkers/fixed_size.py` with
     `chunk_text(text, source, chunk_size=800,
     overlap=120)`.
   - Patch `domain/chunk.py` to add `source: str = ""` and
     `chunk_index: int = 0` to the `Chunk` model.
   - Commit the three `tests/fixtures/` files.
6. **Subagent B** (Supabase + SQL bootstrap + defaults):
   - Add `"supabase>=2.0,<3"` to `pyproject.toml`. Run
     `uv lock`.
   - Create
     `infrastructure/vector_stores/supabase_store.py`.
   - Create
     `infrastructure/vector_stores/supabase_schema.sql`
     (committed).
   - Create `scripts/bootstrap_supabase.py` (one-time
     maintainer script).
   - Create `infrastructure/defaults.py` (`Defaults` +
     `load_defaults`).
   - Create `config/defaults.toml` (committed) with the
     committed public URL + anon key for the demo Supabase
     project.
   - Extend `infrastructure/settings.py` with the new
     `vector_store_strategy` field.
   - Extend `infrastructure/vector_stores/__init__.py` to
     export `SupabaseVectorStore`.
   - Add the `import-linter` `forbidden_modules` contract
     for `supabase`.
7. **Subagent C** (Commands + composition + docs): runs after
   A and B finish.
   - Create `data/documents/architecture.md`,
     `data/documents/style-guide.txt`, and run
     `scripts/build_sample_pdf.py` to materialise
     `data/documents/api-reference.pdf`.
   - Extend `application/knowledge_service.py` with the
     `set_vector_store(...)` method.
   - Extend `application/prompts.py` with the new
     `_RECALL_HEADER`, `_RECALL_CHUNK_FORMAT`, and update
     `build_chat_messages` to format chunks with source
     metadata.
   - Update `application/recall_coordinator.py` to pass
     through `Chunk.source` / `Chunk.chunk_index` (the
     `Chunk` fields are now populated; the coordinator
     already passes the chunk text through; extend the
     call sites to also pass source + chunk_index).
   - Extend `presentation/commands/learn.py` to handle the
     `<path>` argument.
   - Create `presentation/commands/vector_store.py`.
   - Extend `presentation/commands/__init__.py`
     (`AppState`) with `vector_store` and
     `active_vector_store`.
   - Update `cli._build_vector_store` to take `defaults`
     and choose between `SupabaseVectorStore` and
     `SqliteVecStore` (with the existing
     `NumpyBruteForceStore` fallback).
   - Update `cli._bootstrap_app_state` to call
     `load_defaults()` and pass the resolved strategy to
     `_build_vector_store`.
   - Create `docs/rag.md` (one page + worked examples).
   - Patch `docs/providers.md` with a Supabase section.
   - Update `README.md`: Slash commands table gains
     `/vector-store` and `/learn <path>`; new "RAG over
     documents" section; new "Testing the RAG flow"
     section (5-step walkthrough).
   - Update `.env.example` with `CODER_DEFAULTS_PATH=` and
     `CODER_VECTOR_STORE_STRATEGY=`.
8. **Run the gate.** All exit 0.
9. **Verify behaviour:**
   - `uv run coder` starts against the demo Supabase
     instance (the committed `config/defaults.toml` URL
     + key).
   - `/learn data/documents/architecture.md` → expect
     "learned N chunks from data/documents/architecture.md
     (md, <n> bytes, page_count=csv)." plus an actual
     upsert visible in the Supabase dashboard (or via
     `supabase-py` CLI).
   - Chat "What does the cache layer look like?" — the
     LLM response cites `architecture.md` (search the
     transcript for `architecture.md`).
   - Chat "What is the capital of France?" — the LLM
     responds from general knowledge (no source cited).
   - Chat "According to docs/secret-doc.md, what is X?"
     — the LLM refuses with "I don't have enough
     information".
   - `/vector-store sqlite` → expect "active vector
     store: sqlite". Chat "What does the cache layer look
     like?" — no recall (no chunks in sqlite; the sqlite
     store is empty). `/vector-store supabase` → chat
     again; recall returns.
10. **Commit (suggested template — adapt to actual changes):**
    three commits, one per subagent.
    - A: `feat(rag): DocumentLoader + ExtensionDispatchLoader (md/txt/pdf) + FixedSizeChunker.chunk_text + Chunk.source/chunk_index`
    - B: `feat(rag): SupabaseVectorStore + pgvector schema + Defaults (TOML loader)`
    - C: `feat(cli): /learn <path> + /vector-store + LLM-decides system prompt + sample docs`
    - Each commit body carries the relevant slice of the
      `provider-research:` block.
11. **Documentation consolidation (FINAL STEP — the next DO cannot
    start until this commit lands).** Subagent C already touches
    docs inline (README + `.env.example` + creates `docs/rag.md` +
    patches `docs/providers.md`). This step is a **final sweep**: it
    catches anything the subagents missed, removes stale mentions
    of the old "chunk-on-compacted-session-only" behaviour, and
    commits the docs as **one** `docs(do-13):` commit — the
    **last** commit of this DO, separate from the three subagent
    commits above. Scope by file:
    - **README.md** —
        - Add the two new slash-command surface changes to the
          slash-commands table: `/learn <path>` (ingest a local
          document into the active vector store) and `/vector-store`
          (switch the active vector store between Supabase and
          sqlite).
        - Replace **every** leftover mention of "the RAG system
          triggers on each request… autopopulates from a command
          `/learn` [that] compacts the session file" with the new
          behaviour: `/learn <path>` ingests a local PDF / Markdown
          / text document, the LLM-decides system prompt injects
          relevant chunks (with source metadata) into the context,
          and the bot refuses to invent when retrieval returns no
          supporting chunks.
        - Add a new top-level *RAG over documents* section that
          covers: how to drop files into `data/documents/` (or pass
          `/learn <path>` for any external path), the three sample
          files (`api-reference.pdf`, `architecture.md`,
          `style-guide.txt`), the 500–800 token chunk size with 10–20%
          overlap, the two vector-store strategies (Supabase /
          sqlite) and how to switch them at runtime via
          `/vector-store`, and the "no information" refusal
          contract.
        - Add a new *Testing the RAG flow* subsection with a
          5-step walkthrough (start REPL → `/learn
          data/documents/architecture.md` → chat "What does the
          cache layer look like?" → chat "According to
          docs/secret-doc.md, what is X?" to verify the "no info"
          refusal → swap vector store via `/vector-store` and chat
          again to see recall disappear).
        - Update the *Deployed service URLs* section to add the
          Supabase project URL (from the committed
          `config/defaults.toml`), the `match_chunks` PL/pgSQL
          function name, and the one-time
          `python scripts/bootstrap_supabase.py` setup step. No
          anon/service keys exposed.
    - **`.env.example`** —
        - Add the two new env vars introduced by Subagent B/C:
          `CODER_DEFAULTS_PATH=` (defaults to
          `config/defaults.toml`) and
          `CODER_VECTOR_STORE_STRATEGY=` (one of `supabase`,
          `sqlite_vec`, `brute_force`).
        - Leave the per-provider env vars untouched (DO-11 owns
          those) and the session-memory env vars untouched (DO-12
          owns those).
    - **`docs/rag.md`** —
        - Confirm the file exists (created by Subagent C) and
          documents the document loader dispatch
          (`ExtensionDispatchLoader` for `.md`, `.txt`, `.pdf`),
          the chunking strategy (size, overlap, deterministic chunk
          numbering), the Supabase schema (`chunks` table +
          `match_chunks` PL/pgSQL function), the sample documents
          under `data/documents/`, the vector-store runtime
          switch, and the "no information" refusal contract.
        - Patch any drift between what Subagent C wrote and what
          the code does.
    - **`docs/providers.md`** —
        - Confirm the Supabase section was added (Subagent C's
          patch) and that it lists the deployed Supabase project
          URL, the bootstrap script, and the default-anon-key
          policy.
    - **`data/documents/`** —
        - Confirm the three sample files are committed
          (`architecture.md`, `style-guide.txt`,
          `api-reference.pdf`).
    - **`coding-assistance/`** — **out of scope for DO-13**. If
      the folder exists already, skip silently. Created and
      maintained by DO-14.
    - The sweep produces **one** commit at the very end of
      DO-13:
        - `docs(do-13): consolidate README + .env.example + docs/rag.md + docs/providers.md for RAG over documents + Supabase`
        - The commit body lists every file touched and a
          one-line summary of the change in each (e.g.
          `- README.md: /learn <path> + /vector-store added; /learn wording replaced; RAG section + Testing-the-RAG-flow walkthrough added`).
12. **Post-flight.** `git status` clean.

## Failure modes

- **Committed anon key is rotated by the project lead.** The
  on-call maintainer updates `config/defaults.toml`. The
  next clone picks up the new key on `uv sync`. No action
  for downstream users.
- **`supabase.create_client(url, key)` fails at import time**
  (e.g., the anon key is malformed). `cli._build_vector_store`
  catches the failure, falls back to `SqliteVecStore` (or
  `NumpyBruteForceStore`), logs at INFO. The REPL prints a
  one-liner so the user knows the screenshot went to local
  storage.
- **PDF has zero extractable text** (e.g., scanned image
  PDF). `ExtensionDispatchLoader` returns
  `("", DocumentMetadata(...page_count=<n>))`. The
  `LearnCommand` translates to "PDF has no extractable
  text." Future DO can add OCR via `pytesseract` + `pdf2image`
  — out of scope v1.
- **`Match_chunks` PL/pgSQL function does not exist** on a
  fresh Supabase project (the maintainer skipped the
  bootstrap script). `SupabaseVectorStore.query` raises
  `VectorStoreBackendUnavailable` (mapped from the
  `PGRST202` / `PostgresError`). The REPL falls back to
  sqlite. README documents the one-time setup clearly.
- **`config/defaults.toml` has malformed TOML.** `load_defaults`
  raises `tomllib.TOMLDecodeError`. `cli._bootstrap_app_state`
  catches it and prints a one-liner with the file path. The
  REPL still starts but uses sqlite.
- **Auto-cookie pypdf version bump.** `pypdf>=5.0,<6` is the
  pin. If the version moves to 6.x, the pin is updated in
  pyproject.toml; record the bump in the commit body.
- **`/learn <path>` ingests a binary file with a `.md`
  extension** (a user renames an executable to `.md`).
  `ExtensionDispatchLoader` reads it as UTF-8 text, gets
  replacement glyphs (`U+FFFD`), and the chunks contain
  noise. A future DO can add a magic-byte sniff (PDF starts
  with `%PDF-`, etc.). Out of scope v1.
- **Re-ingesting the same document creates duplicate
  chunks** — the bootstrap SQL uses `ON CONFLICT (source,
  chunk_index) DO UPDATE`, so re-ingesting the same source
  overwrites. Different `chunk_index` values within the same
  source would conflict — the loader / chunker produce
  deterministic indices for the same input, so this is
  not a real issue.
- **The committed `config/defaults.toml` URL points at a
  demo Supabase project that gets rate-limited or taken
  down.** The README documents the workaround: replace
  the URL + key with your own Supabase project's values
  (or run `python scripts/bootstrap_supabase.py` against
  your project first).

## Failure modes deferred to DO-15 (v1 follow-up)

- A `DocumentLoaderRegistry` Strategy (one loader per
  format; chosen at runtime).
- Auto-loading from `data/documents/` at startup.
- Glob patterns (`/learn --glob "docs/*.md"`).
- Source management (`/forget <source>`,
  `/sources` to list ingested sources).
- Streaming ingestion for large documents (PDF > 100
  pages).
- Per-document custom chunk size.
- OCR for image-only PDFs.
- The `service_role` key for higher-privilege Supabase
  operations.
- A `vector_store` subcommand family for managing
  sources (list, forget, inspect).