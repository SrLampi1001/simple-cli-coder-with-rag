# Chunker Strategy

The `/learn` pipeline ends with **chunking**: turning the compacted
JSON (`CompactedSession`) into a list of `Chunk` records ready for
embedding (DO-06) and storage in the vector database (DO-07). The
chunker is the first **Strategy** seam in the RAG pipeline — there is
one interface and several possible implementations, picked at
composition time.

This document explains:

1. **Where** the configuration lives (env var, settings, code).
2. **What** the two shipped implementations do.
3. **How** to pick one — and how to add a third.
4. **Why** the per-record source attribution matters for retrieval.

The rest of the RAG pipeline (embedder, vector store, retriever) talks
to the chunker only through the `Chunker` Protocol in
`src/simple_cli_coder_with_rag/domain/chunker.py`. Replacing the
implementation does not require touching the embedder, the store, the
retriever, the REPL, or any other layer.

---

## Where to change the configuration

There are **three** knobs, ordered from least invasive to most invasive.

### 1. Pick a Strategy via `CHUNKER_STRATEGY` (recommended)

In `.env` (or the environment):

```bash
# Default — sliding-window chunker.
CHUNKER_STRATEGY=fixed

# Alternative — one chunk per logical record.
CHUNKER_STRATEGY=semantic
```

The setting is read by `Settings.chunker_strategy` in
`src/simple_cli_coder_with_rag/infrastructure/settings.py`. The
composition root in `src/simple_cli_coder_with_rag/cli.py` resolves
the strategy to a concrete chunker via
`build_chunker(strategy)` (defined in
`src/simple_cli_coder_with_rag/application/knowledge_service.py`).
Any other value is rejected at `Settings()` construction time with a
`pydantic.ValidationError`.

This is the right knob to turn for **most experiments** — flipping
between `fixed` and `semantic` is one env-var change and a process
restart, no code edits.

### 2. Tune the chosen chunker in code

If you want to keep the **Strategy** but change its parameters (window
size, overlap, etc.), edit the construction site in
`src/simple_cli_coder_with_rag/cli.py`:

```python
# cli.py — _bootstrap_app_state()
chunker = build_chunker(settings.chunker_strategy)
```

Today `build_chunker` ignores all parameters and instantiates
`FixedSizeChunker()` / `SemanticChunker()` with their defaults. To
customise the window, change one of these two lines:

```python
# Larger window, no overlap — good for very long error messages.
return FixedSizeChunker(max_chars=1024, overlap=0)

# Smaller window, more overlap — more chunks, finer recall.
return FixedSizeChunker(max_chars=256, overlap=64)

# SemanticChunker takes max_chars too — informational, not enforced.
return SemanticChunker(max_chars=512)
```

Validation lives in `FixedSizeChunker.__init__`:

```python
FixedSizeChunker(max_chars=10, overlap=10)  # ValueError: overlap must satisfy 0 <= overlap < max_chars
FixedSizeChunker(max_chars=0, overlap=0)    # ValueError: max_chars must be > 0
```

So no matter how you construct it, an invalid configuration fails
loudly at startup — never silently produces degenerate chunks.

### 3. Add a new Strategy (advanced)

If neither fixed-size nor semantic chunking fits your corpus
(e.g. sentence-aware splitter, code-aware splitter, recursive
character splitter), add a third option:

1. Create `src/simple_cli_coder_with_rag/application/chunkers/<name>.py`
   with a class that satisfies the `Chunker` Protocol:

   ```python
   from simple_cli_coder_with_rag.domain.chunk import Chunk
   from simple_cli_coder_with_rag.domain.compacted import CompactedSession

   class SentenceChunker:
       def chunk(self, compacted: CompactedSession) -> list[Chunk]:
           ...
   ```

2. Add the literal value to `Settings.chunker_strategy`:

   ```python
   chunker_strategy: Literal["fixed", "semantic", "sentence"] = "fixed"
   ```

3. Extend `build_chunker` in `application/knowledge_service.py`:

   ```python
   if strategy == "sentence":
       return SentenceChunker()
   ```

4. Add tests in `tests/application/chunkers/test_sentence.py` mirroring
   the patterns in `test_fixed_size.py` and `test_semantic.py`.

That's the whole surface area. The embedder, vector store, retriever,
and REPL stay untouched because they only know about the `Chunk`
model and the `Chunker` Protocol — they do not import any concrete
chunker.

---

## What the two shipped implementations do

### `FixedSizeChunker` (default)

`src/simple_cli_coder_with_rag/application/chunkers/fixed_size.py`

* **Strategy.** Sliding window over each record of the compacted
  session. Records are built in this order — `summary`, then each
  `ErrorRecord` rendered as `"Error: {signature}\n{message}"`, then
  each `DecisionRecord` rendered as `"Decision: {summary}\n{rationale}"`.
* **Window.** `max_chars` wide, with `overlap` characters of overlap.
  Defaults: `max_chars=512`, `overlap=64`.
* **Word boundaries.** Each window snaps back to the nearest preceding
  space unless backing off would leave a window shorter than 16
  characters (the `_MIN_WINDOW_CHARS` guard in
  `fixed_size.py`). This avoids degenerate single-character windows
  on the first iteration.
* **Per-record sliding.** Each record is windowed **independently**,
  not as one global sliding window across the concatenated string.
  Why: a single global window can start mid-record, which leaves the
  chunk's `metadata["source"]` ambiguous (the algorithm can only
  attribute by the first record in the window, which is whichever
  record the window *started* in). Per-record sliding guarantees that
  every chunk's `source` is the record it came from.
* **Empty input.** Returns `[]` (not `[Chunk(text="")]`), so the
  embedder never sees a zero-length input.

Trade-offs:

* ✅ Predictable chunk sizes → predictable embedding cost.
* ✅ Strong on long error messages that need to be split for the
  embedder's token budget.
* ✅ Source attribution is deterministic.
* ❌ Loses record boundaries — a window may cut a sentence in half.
* ❌ Short records (e.g. `summary="ok"`) produce one chunk regardless
  of `max_chars`; very long records produce many.

### `SemanticChunker` (alternative)

`src/simple_cli_coder_with_rag/application/chunkers/semantic.py`

* **Strategy.** One chunk per logical record. No splitting.
* **Records emitted.** One for the `summary` (when non-empty), one
  per `errors[]` entry, one per `decisions[]` entry.
* **Empty input.** Returns `[]`.
* **`max_chars` parameter.** Accepted (default `1024`) for parity with
  `FixedSizeChunker`, but **not enforced** — a single record is the
  largest possible chunk, so no split ever happens. If a single error
  message exceeds your embedder's token budget, `FixedSizeChunker` is
  the right choice instead.

Trade-offs:

* ✅ Preserves record boundaries — each chunk is a self-contained unit.
* ✅ Smaller chunk count → smaller vector store → cheaper retrieval.
* ✅ Strong when the compacted records are short and well-formed.
* ❌ Chunk sizes can swing wildly. A 5000-character error message
  becomes a single 5000-character chunk that may exceed the embedder's
  max input.
* ❌ Hits the embedder's `max_length` if any record is too long.

---

## How to pick one

| Situation | Use |
|---|---|
| Default. Long error messages you don't want to truncate. | `fixed` (the default) |
| Records are short and well-formed; you want minimum chunks. | `semantic` |
| You need predictable chunk sizes for cost / latency budgeting. | `fixed` |
| You want one chunk per error / decision so the retriever can pinpoint them. | `semantic` |
| You're tuning retrieval quality and want to compare cheaply. | Try both — same code path downstream. |

The two chunkers are interchangeable: same `Chunk` schema on the
output, same `session_id` propagated, same source metadata. Retrieval
quality is the only difference, and it depends on your data. The
strategy choice is a knob, not a one-way door.

---

## Why per-record source attribution matters

Every chunk carries:

```python
metadata = {
    "source": "summary" | "error" | "decision",
    "index": <int, zero-based>,
}
```

The retriever (DO-08 / DO-09) reads `source` to explain hits back to
the user ("this came from the error section", "this came from the
summary"). It also reads it as a filter — DO-07 may store it as a
plain column on the sqlite-vec table so the retriever can restrict a
query to "only errors" or "only decisions".

The `index` field counts from zero in chunk order. It is the
tiebreaker when two chunks have the same `source` (e.g. two errors):
`metadata["index"]` lets the retriever sort them back into the order
they appeared in the compacted session.

`Chunk.session_id` is a top-level field (not in `metadata`) because
**every** chunk we ever produce belongs to one session, and the
retriever / store filter by it constantly. Keeping it as a dedicated
column avoids the cost of re-parsing `metadata` on every query.

---

## Verification

Both chunkers are exercised by the test suite:

```bash
uv run pytest tests/application/chunkers -v
```

The fixed-size suite (`test_fixed_size.py`) covers:

* Constructor validation (`overlap >= max_chars`, `max_chars <= 0`).
* Short-text (single-chunk) and long-text (many-chunk) inputs.
* Source attribution for summary / error / decision records.
* `session_id` propagation.
* Empty compacted session → `[]`.
* `Chunk` instance identity (not a plain `dict`).

The semantic suite (`test_semantic.py`) covers:

* One chunk per record (summary + 2 errors + 1 decision → 4 chunks).
* Source attribution per record type.
* `session_id` propagation.
* Empty compacted session → `[]`.
* Sequential `metadata["index"]`.

The integration suite
(`tests/application/test_knowledge_service_chunking.py`) covers:

* `KnowledgeService.learn(session_id) -> int` returns a real count.
* `LearnCommand.execute` returns `"learned N chunks"` with the count.
* `LearnCommand` calls `knowledge.learn(session_id)` with **only**
  one positional argument (no message list — DO-05's contract
  hardens the signature against the DO-04 deviation where
  `learn(session_id, messages)` was used).
