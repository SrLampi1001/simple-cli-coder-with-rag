# RAG over local documents

The CLI can ingest local PDF, Markdown, and plain-text documents into
the active vector store with `/learn <path>`, and the chat-time
prompt uses an LLM-decides retrieval contract that cites the source
of every recalled chunk.

## Document ingestion pipeline

```
/learn <path>
    │
    ▼
DocumentLoader          ← ExtensionDispatchLoader (md / txt / pdf)
    │
    ▼
text + DocumentMetadata
    │
    ▼
FixedSizeChunker.chunk_text   ← 800-char windows, 15% overlap
    │
    ▼
list[Chunk] with source / chunk_index
    │
    ▼
Embedder.embed_passages       ← BAAI/bge-small-en-v1.5 (384-dim)
    │
    ▼
VectorStore.upsert            ← SqliteVecStore (default) or NumpyBruteForceStore
```

`ExtensionDispatchLoader` reads the file:

* `.md` / `.markdown` → UTF-8 with `errors="replace"` (a malformed byte
  becomes a `U+FFFD` replacement glyph rather than crashing the
  pipeline).
* `.txt` → same UTF-8 path.
* `.pdf` → `pypdf.PdfReader` per-page text, joined with a form-feed
  (`\f`) separator. `DocumentMetadata.page_count` carries the page
  count so the chat-time prompt can report it.

A 2000-character input with the default `chunk_size=800, overlap=120`
produces three chunks (800 + 800 + 640 chars), each tagged with the
file's absolute path (`source`) and a zero-based `chunk_index`. The
first 120 chars of chunk N+1 are the last 120 chars of chunk N —
the documented overlap window.

`/learn <path>` runs on a background thread; the user can keep
chatting while the load + chunk + embed + upsert finishes. The
worker prints one of:

* `learn: done — learned N chunks from <path> (<file_type>,
  <byte_size> bytes, page_count=<p|csv>).` — success.
* `learn failed: PDF has no extractable text.` — PDF returned no
  extractable text (scanned image PDF, for example).
* `learn failed: unsupported file type: '.<ext>'. Supported: pdf, md,
  markdown, txt.` — unrecognised extension.
* `learn failed: <path> does not exist.` — non-existent path.
* `learn failed: <exception>` — any other failure, propagated from
  the loader or the embedder / vector store.

## LLM-decides retrieval

Every chat turn that has recalled context prepends a single
`SystemMessage` carrying the four decision rules and the formatted
chunks. The header is verbatim:

```
You have access to the following context from the user's
loaded documents and previous sessions.

Decision rules:
  - Use the context when the question references or requires
    specific information from the user's documents or previous sessions.
  - If the question can be answered without the context, answer
    from your general knowledge.
  - If the question requires specific document content that was
    NOT retrieved, say you don't have enough information rather than
    guessing.
  - When you use the context, mention which source(s) you drew from.

Context:

[Source: docs/foo.md, chunk #0]
<chunk text>

---

[Source: docs/foo.md, chunk #1]
<chunk text>
```

Each chunk is formatted as `[Source: <source>, chunk #<chunk_index>]\n<content>`
and consecutive chunks are joined with `\n\n---\n\n`. The LLM is
expected to follow the four rules — there is no Python branch that
forbids generation when retrieval returns no chunks (the
"don't invent" rule is enforced by the system prompt, not by code).

### Worked example: "use the context"

```
>>> /learn data/documents/architecture.md
learn: done — learned 1 chunks from data/documents/architecture.md
(md, 1829 bytes, page_count=csv).
>>> What does the cache layer look like?
[LLM reply citing data/documents/architecture.md, quoting a chunk]
```

The LLM response is shaped by the retrieved chunk; the chunk's
`source` lets the LLM attribute the answer.

### Worked example: "general knowledge"

```
>>> What is the capital of France?
[LLM answer: Paris, no source cited]
```

The recall pipeline returns no chunks (or returns chunks below the
similarity threshold), so the `SystemMessage` is omitted and the LLM
falls back to its general knowledge.

### Worked example: "no information"

```
>>> According to docs/secret-doc.md, what is X?
[LLM reply: I don't have enough information — docs/secret-doc.md was
not loaded.]
```

The LLM follows the third decision rule rather than guessing.

## Vector store strategy

The vector store is the **swappable Strategy** seam. The active
backend is selected by:

1. `Settings.vector_store_strategy` — the family pick. `sqlite` is
   the only currently-wired value.
2. `Settings.vector_store` — the sub-pick inside the family:
   `sqlite_vec` (default, persistent) or `brute_force` (in-memory
   fallback, opt-in via `VECTOR_STORE=brute_force`).

The composition root reaches the backend through
`build_vector_store(settings)` in
`infrastructure/vector_stores/factory.py` — the single composition
point that knows how to build any registered backend. Adding a new
backend is a matter of writing a new class implementing the
`VectorStore` Protocol and adding a branch to the factory.

`/vector-store` swaps the backend at runtime. It accepts:

* `/vector-store` (no args) — print `active vector store: <name>`
  and the available list.
* `/vector-store sqlite_vec` — rebuild the chain around
  `SqliteVecStore` (or fall back to `NumpyBruteForceStore` on
  `VectorStoreBackendUnavailable`).
* `/vector-store brute_force` — rebuild around the in-memory
  numpy store.
* `/vector-store supabase` — print the forthcoming message. The
  Supabase + pgvector adapter is a follow-up DO; the architecture
  seam is in place so adding it is a clean drop-in (new class +
  factory entry).
* `/vector-store bogus` — print the unknown-name friendly message.

The `/vector-store` command also reaches the live
`RetrievalExecutor` so the rebuilt chain shares the composition
root's executor (no double-wrapping).

## Sample documents

The committed samples under `data/documents/` are three real files
the user can ingest as a smoke test:

* `data/documents/architecture.md` — a fictional cache-layer
  architecture (~500 words). Mentions the cache layer in the first
  H2 so the LLM can cite it.
* `data/documents/style-guide.txt` — a plain-text style guide
  (~200 words). Naming conventions, imports, type hints,
  docstrings.
* `data/documents/api-reference.pdf` — a two-page PDF describing
  a fictional cache API. Generated by a one-shot pypdf script and
  committed so the test suite and the README walkthrough have a
  stable binary to load.

The PDF is generated by the same one-shot script that is not
shipped in the repo (the PDF is committed directly; running the
generator overwrites the file).

## TL criterion mapping

* **TL #4** — "RAG returns relevant chunks with source metadata and
  the chatbot does not invent unsupported answers." The
  `Chunk.source` field, the LLM-decides system prompt, and the
  chat-time prompt's chunk formatting are the three pieces of this
  contract.
* **TL #8** — "every project service it consumes must be deployed
  and reachable through a documented URL." The vector store is a
  local file in v1 (the current DO). The Supabase + pgvector
  follow-up will add a deployed vector store at a documented URL.

## Deferred to a Supabase follow-up DO

* `SupabaseVectorStore` — the Supabase + pgvector adapter. The
  `Settings.vector_store_strategy` literal already lists
  `"supabase"`; the factory's `"supabase"` branch returns
  `VectorStoreBackendUnavailable` with a friendly forthcoming
  message. The actual adapter is a class + a PL/pgSQL schema +
  a one-time `scripts/bootstrap_supabase.py` to run against a
  Supabase project.
* `config/defaults.toml` + `infrastructure/defaults.py` — a
  committed TOML defaults file (URL + anon key) plus the
  Pydantic `Defaults` model that loads it. The current DO uses
  `Settings` for everything; the TOML is needed once Supabase
  credentials live in the repo.
* `scripts/build_sample_pdf.py` — a one-shot generator for the
  sample PDF. The current DO ships the PDF directly; the
  generator is a follow-up so the test suite can regenerate the
  fixture on demand.
