# DO-14 — Custom skills (knowledge-base-lookup, summarization)

## Goal

Introduce **two reusable custom skills** that wrap a chunk of the existing
pipeline behind a documented, named interface:

1. **`knowledge-base-lookup`** — takes a free-text query and returns the
   most relevant chunks from the active vector store, with source
   metadata attached. Auto-invoked by the chat path (the same flow
   `RecallCoordinator.recall` powers in DO-09 / DO-13). Also invocable
   directly as `/kb-lookup <query>`.
2. **`summarization`** — takes a long text (or a chat transcript) and
   returns a concise summary produced by the active LLM. Auto-invoked
   by `/compact` (DO-12) for the session-summary path. Also invocable
   directly as `/summarize <text>`.

Both are implemented as Strategies behind a single `Skill` Protocol and
live under `application/skills/`. They reuse the existing
`LLMClient` (DO-11), `RecallCoordinator` (DO-09) and `Compactor`
(DO-12) primitives — the skill is the named, documented, reusable
interface, not a re-implementation. The DO-12 `Compactor.summarize`
contract and the DO-09 `RecallCoordinator.recall` contract are
preserved verbatim; the slash commands that used to call them now go
through the skills instead.

Satisfies TL acceptance criterion #5: *"At least 2 custom skills are
implemented and can be invoked in a working demo."*

> **Numbering note.** DO-11's out-of-scope list called this deliverable
> "DO-15" and `coding-assistance/ trace` "DO-14". This plan follows the
> user's instruction to produce the skills deliverable next, so it is
> numbered **DO-14**. If `coding-assistance/` is to ship first, swap the
> two folders and update the references in DO-11's out-of-scope list
> and the `agent-development/README.md` order-of-execution table.

## Source of truth

- `OBJECTIVES.md` — Strategy pattern (each skill is a Strategy behind a
  Protocol), Command pattern (`/kb-lookup` and `/summarize` are first-class
  slash commands), Facade pattern (the Skills facade sits beside
  `KnowledgeService`), Adapter pattern (the `LLMClient` Protocol already
  isolates the vendor SDK).
- `NEW_REQUIREMENTS.md` §6 *Custom skills* — at least 2 reusable skills,
  each documenting purpose / expected input / expected output / invocation;
  both usable in a working demonstration.
- `docs/development-tools.md` §5 (embedder), §6 (LLM SDKs), §8 (pydantic).
- DO-09 contracts — `RecallCoordinator`, `TrivialGate`.
- DO-11 contracts — `LLMClient` Protocol, `ProviderRegistry`.
- DO-12 contracts — `Compactor.summarize`, `SessionManager.maybe_compact`,
  `AppState.session_id` / `session_store`.
- DO-13 contracts — `RecallCoordinator.recall`, the chat path that injects
  recalled chunks as a `SystemMessage`.

## Acceptance criteria

### Domain — `Skill` interface

- [ ] `src/simple_cli_coder_with_rag/domain/skill.py` defines:

  ```python
  class SkillResult(BaseModel):
      """Structured output of a skill invocation."""
      skill: str                       # the skill name (echoed back)
      output: str                      # primary text result
      metadata: dict[str, Any] = Field(default_factory=dict)

  class Skill(Protocol):
      """Reusable, named unit of behaviour invoked by the REPL or by other skills."""

      name: str
      description: str

      def invoke(self, *, input: str, context: SkillContext) -> SkillResult: ...
  ```

  `SkillContext` is a small Pydantic model:

  ```python
  class SkillContext(BaseModel):
      """Per-invocation context handed to a skill."""
      llm: LLMClient | None = None
      recall_coordinator: RecallCoordinator | None = None
      model: str = ""
  ```

  The context is **passed by the caller** — skills do not reach into the
  REPL globals. This keeps them testable with a plain dict.

### Application — the two skills

- [ ] `src/simple_cli_coder_with_rag/application/skills/__init__.py`
      re-exports `KnowledgeBaseLookupSkill`, `SummarizationSkill`,
      `Skill` and `SkillResult`.
- [ ] `src/simple_cli_coder_with_rag/application/skills/knowledge_base_lookup.py`
      defines `class KnowledgeBaseLookupSkill`:
  - `name == "knowledge-base-lookup"`.
  - `description == "Search the active vector store for the top-k chunks most
    relevant to the input; includes file source and similarity score."`.
  - `invoke(*, input: str, context: SkillContext) -> SkillResult`:
    - Returns `SkillResult(skill="knowledge-base-lookup", output="", metadata={})`
      when `context.recall_coordinator is None` (graceful no-op for tests
      that wire no retrieval — same shape the DO-09 recall path returns).
    - Calls `context.recall_coordinator.recall(input)` to obtain
      `list[str]` of chunk texts.
    - **Surface source metadata**: the recall coordinator's `.results()`
      accessor (added in DO-13 to expose `Chunk.source` / `chunk_index` /
      `similarity`) is used to build per-hit metadata entries. The
      `SkillResult.output` is the joined chunk texts (same shape as
      today's recall). The `SkillResult.metadata["hits"]` is a list of
      `{"source": str, "chunk_index": int, "similarity": float}` dicts,
      in the order returned by the coordinator. When the coordinator
      exposes no `results()` (legacy DO-09 wiring), `metadata["hits"]`
      is `[]` and the field is still present — never missing.
- [ ] `src/simple_cli_coder_with_rag/application/skills/summarization.py`
      defines `class SummarizationSkill`:
  - `name == "summarization"`.
  - `description == "Produce a 150-300 word summary of the input text using
    the active LLM. Surfaces the LLMError verbatim."`.
  - `invoke(*, input: str, context: SkillContext) -> SkillResult`:
    - Empty `input` (after `.strip()`) short-circuits to
      `SkillResult(skill="summarization", output="(empty input)", metadata={"chars": 0})`.
    - Non-empty `input` is sent through a two-message prompt mirroring
      DO-12's `Compactor.summarize`:
      - `SystemMessage(content="Summarise the following text in 150-300 prose
        words: errors, decisions, key facts, current state.")`
      - `UserMessage(content=input)`.
      - The model is `context.model or the active LLM's
        `default_model` (the coordinator passes the latter; if neither is
        set, the skill raises `SkillError("no model configured")`).
    - Returns `SkillResult(skill="summarization", output=<reply stripped of
      leading/trailing whitespace>, metadata={"chars": len(input),
      "summary_chars": len(output)})`.
    - On `LLMError`, propagates verbatim (no wrapping — the REPL catches it
      in the existing DO-12 path).

### Refactor of the DO-11 → DO-13 callers (non-breaking)

- [ ] `src/simple_cli_coder_with_rag/application/compactor.py` —
      `Compactor.summarize` is **preserved verbatim** (DO-12 contract
      unchanged). A new private helper
      `Compactor._summarize_via_skill(messages)` calls
      `SummarizationSkill().invoke(input=transcript, context=...)`; this
      helper is **not** exposed and is not used by `Compactor.summarize`
      in DO-14. Future deliverables can opt in.
- [ ] `src/simple_cli_coder_with_rag/application/session_manager.py` —
      `SessionManager.maybe_compact` is updated so that when the
      transcript is long enough to trigger compaction, it calls
      `SummarizationSkill().invoke(input=transcript_text,
      context=SkillContext(llm=self._compactor.llm,
      model=self._compactor._compactor_model))` instead of
      `self._compactor.summarize(messages)`. The summary is then
      wrapped in a `SystemMessage` and the compacted chunk
      `SessionStore.write_session_summary` is called as before. The DO-12
      test `test_compactor_summarize_*` continues to pass because
      `Compactor.summarize` itself is unchanged.
- [ ] `src/simple_cli_coder_with_rag/presentation/repl.py` — the chat
      path (`Repl._handle_chat`) is updated to instantiate
      `KnowledgeBaseLookupSkill()` and call
      `skill.invoke(input=line, context=SkillContext(
        llm=self._app_state.llm,
        recall_coordinator=self._app_state.knowledge._coordinator,
        model=self._app_state.knowledge._chat_model,
      ))` instead of `self._app_state.knowledge.recall(line)`. The
      returned `output` (chunk texts) is forwarded to
      `build_chat_messages` exactly as DO-09 does today; the
      `metadata["hits"]` is captured on `AppState.last_retrieval_hits`
      for the `/memory` command (DO-12) to display. DO-09's
      `test_coordinator_*` tests continue to pass because the
      `RecallCoordinator` API is unchanged.

### Presentation — slash commands

- [ ] `src/simple_cli_coder_with_rag/presentation/commands/kb_lookup.py`
      defines `class KbLookupCommand`:
  - `/kb-lookup <query>` — instantiates `KnowledgeBaseLookupSkill()`,
    invokes it with the query, prints the joined chunk text (the
    `output` field), followed by a one-line `hits: N (sources:
    file1.md#3, file2.md#1, ...)` summary. On `SkillError`, prints a
    one-line error and returns.
  - `/kb-lookup` with no query prints `usage: /kb-lookup <query>`.
- [ ] `src/simple_cli_coder_with_rag/presentation/commands/summarize.py`
      defines `class SummarizeCommand`:
  - `/summarize <text...>` — instantiates `SummarizationSkill()`,
    invokes with the trailing text. Prints `summary: <output>` on one
    line, then `chars: N -> summary_chars: M` (from
    `metadata["chars"]` / `metadata["summary_chars"]`). On `LLMError`,
    prints the error and returns. **Note:** this command is a real
    network call; it shares the DO-11 `/connect` key-validation message
    style — readable error, never a crash.
  - `/summarize` with no text prints `usage: /summarize <text>`.
- [ ] Both commands are registered in `cli._build_registry()` after
      the DO-12 commands. `/help` lists both rows.

### Skill documentation (TL acceptance criterion: "document its purpose,
input, output and how it is invoked")

- [ ] `/skills/README.md` (new, repo-root) is the skills index: one
      paragraph per skill, plus an "Auto-invocation" section listing
      which DO-11 → DO-13 commands call each skill.
- [ ] `/skills/knowledge-base-lookup/README.md` documents the skill:
  - **Purpose** — surface relevant chunks from the active vector store
    with source metadata.
  - **Expected input** — a free-text query string.
  - **Expected output** — `SkillResult` with `output=<joined chunk
    texts>` and `metadata.hits=<list of {source, chunk_index,
    similarity} dicts>`.
  - **Invocation** — three paragraphs: (1) auto by the chat path on
    every non-slash prompt; (2) manually as `/kb-lookup <query>`; (3)
    programmatically via `KnowledgeBaseLookupSkill().invoke(...)` with
    a `SkillContext`.
  - **Working demo** — a copy-pasteable transcript: `uv run coder` →
    `/learn data/documents/notes.md` (after `/learn <path>` is wired
    in DO-13) → `/kb-lookup <a phrase from notes>` → expect `hits: N
    (sources: notes.md#3)`. The README is tested manually (the
    `test_readme_mentions_auto_invocation` test greps for the
    substring `Auto-invoked` to fail if the README loses the
    auto-invocation paragraph).
- [ ] `/skills/summarization/README.md` documents the skill in the
      same five-section shape: Purpose, Expected input, Expected output,
      Invocation (auto by `/compact`, programmatic via
      `SummarizationSkill().invoke(...)`, manual via `/summarize`),
      Working demo (`/summarize <paste a paragraph>` →
      `summary: ...\nchars: 412 -> summary_chars: 198`).

### Composition root and tests

- [ ] `src/simple_cli_coder_with_rag/cli.py` is unchanged: skills are
      constructed at the slash-command call site (one-line objects; no DI).
      `ApplicationState` gains `last_retrieval_hits: list[dict[str, Any]]
      = field(default_factory=list)` so `/memory` (DO-12) can display
      the last retrieval's source metadata without re-querying.
- [ ] `tests/application/skills/test_knowledge_base_lookup_skill.py`,
      `tests/application/skills/test_summarization_skill.py`,
      `tests/presentation/commands/test_kb_lookup_command.py`,
      `tests/presentation/commands/test_summarize_command.py` are
      written before any code (see `tests.md`).
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

- Third skill (knowledge-base-lookup, summarization are sufficient for TL).
- Async / streaming skill invocation (skills are sync; the chat path
  wraps them in the REPL's existing prompt loop).
- A `/skills` slash command that lists skills — the existing `/help`
  already covers it (DO-12 added the commands there).
- Skill composition (one skill invoking another); the
  `KnowledgeBaseLookupSkill` does not call `SummarizationSkill` and
  vice versa. Out of scope until TL-005 grows.
- Skill Caching inside `SkillContext`; the existing `TimeoutRetriever`
  Decorator on the recall coordinator already provides a cache layer
  for `knowledge-base-lookup`.

## Depends on

- DO-09 (`RecallCoordinator`, `TrivialGate`, recall metadata model).
- DO-11 (`LLMClient` Protocol, `ProviderRegistry`).
- DO-12 (`AppState`, `SessionManager`, `Compactor.summarize`,
  `/memory` command, the `metadata` model on recalled chunks).
- DO-13 (`RecallCoordinator.results()` exposes source metadata;
  `/learn <path>` populates the vector store with `source` +
  `chunk_index`).

## Blocks

- TL acceptance criterion #5 directly depends on this deliverable.
- Nothing in the agent-development plan (this is the terminal
  deliverable for the v1 ship).