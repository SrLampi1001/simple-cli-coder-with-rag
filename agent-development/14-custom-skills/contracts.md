# DO-14 contracts

## Architectural

- [ ] New modules:
  - `simple_cli_coder_with_rag.domain.skill` — `Skill` Protocol,
    `SkillResult` Pydantic model, `SkillContext` Pydantic model,
    `SkillError` exception.
  - `simple_cli_coder_with_rag.application.skills.knowledge_base_lookup`
    — `KnowledgeBaseLookupSkill`.
  - `simple_cli_coder_with_rag.application.skills.summarization` —
    `SummarizationSkill`.
  - `simple_cli_coder_with_rag.presentation.commands.kb_lookup` —
    `KbLookupCommand`.
  - `simple_cli_coder_with_rag.presentation.commands.summarize` —
    `SummarizeCommand`.
- [ ] `import-linter` reports zero violations.
- [ ] `Skill`, `SkillResult`, `SkillError` live in `domain/` and are
      importable from any layer above.
- [ ] No application-layer module imports `openai`, `anthropic`,
      `supabase`, `sqlite_vec`, `fastembed`, or reads
      `providers.json` directly (regression guard — DO-11 already added
      the `openai` rule, DO-13 added the `supabase` rule; this
      deliverable adds no new vendor types).
- [ ] No presentation-layer module imports from `application/skills`
      directly except through the `Skill` Protocol — the slash-command
      module imports the *concrete* class, but the chat path
      (`Repl._handle_chat`) only sees the Protocol.

## Behavioral

- [ ] `KnowledgeBaseLookupSkill().invoke(input="hello",
      context=SkillContext(recall_coordinator=coordinator))` against a
      coordinator whose `recall()` returns `["chunk-A", "chunk-B"]` and
      whose `results()` returns `[{"source": "a.md", "chunk_index": 0,
      "similarity": 0.81}, {"source": "b.md", "chunk_index": 2,
      "similarity": 0.62}]` returns
      `SkillResult(skill="knowledge-base-lookup", output="chunk-A\n\n---\n\nchunk-B",
      metadata={"hits": [{"source": "a.md", "chunk_index": 0, "similarity": 0.81},
                         {"source": "b.md", "chunk_index": 2, "similarity": 0.62}]})`.
- [ ] `KnowledgeBaseLookupSkill().invoke(input="x",
      context=SkillContext(recall_coordinator=None))` returns
      `SkillResult(skill="knowledge-base-lookup", output="",
      metadata={"hits": []})` — **does not raise**.
- [ ] `KnowledgeBaseLookupSkill().invoke(input="x",
      context=SkillContext(recall_coordinator=coordinator))` where the
      coordinator has no `.results()` method (legacy DO-09 wiring)
      returns `SkillResult(metadata={"hits": []})` and emits a single
      `logger.debug("recall coordinator has no .results(); legacy wiring")`.
- [ ] `KnowledgeBaseLookupSkill().invoke(input="hello",
      context=SkillContext(recall_coordinator=coordinator))` against a
      coordinator whose `recall()` raises `LLMError` — propagates
      `LLMError` verbatim (the chat path catches it via the existing
      DO-12 `try/except`; the `/kb-lookup` command's own try/except
      catches it and prints a one-line message).
- [ ] `SummarizationSkill().invoke(input="  ", context=...)` returns
      `SkillResult(skill="summarization", output="(empty input)",
      metadata={"chars": 0, "summary_chars": 13})` and does NOT call the
      LLM.
- [ ] `SummarizationSkill().invoke(input="long text...",
      context=SkillContext(llm=fake_llm, model="m"))` against an LLM
      stub that returns `"summary line.\n"` produces
      `SkillResult(output="summary line.", metadata={"chars": <len>,
      "summary_chars": 13})`.
- [ ] `SummarizationSkill().invoke(input="x", context=SkillContext(
      llm=fake_llm_that_raises))` propagates `LLMError` verbatim.
- [ ] `SummarizationSkill().invoke(input="x", context=SkillContext(
      llm=None, model=""))` raises `SkillError("no model configured")`.
- [ ] `SessionManager.maybe_compact` on a transcript of 11 user/assistant
      turns (default `keep_last_n_messages=10`) calls
      `SummarizationSkill().invoke(...)` exactly once and persists the
      summary via `SessionStore.write_session_summary`; the chat loop's
      `messages` list contains a single `SystemMessage(content=summary)`
      followed by the 10 most-recent messages. Pinned by
      `test_session_manager_maybe_compact_uses_summarization_skill`.
- [ ] `Compactor.summarize` returns the same string it returned in
      DO-12 for the same input — its body is **unchanged**. Pinned by
      `test_compactor_summarize_unchanged_from_do12`.
- [ ] `Repl._handle_chat` instantiates `KnowledgeBaseLookupSkill` and
      calls `.invoke(...)` instead of `knowledge.recall(...)`. Pinned by
      `test_repl_chat_uses_kb_lookup_skill`.
- [ ] `Repl._handle_chat` writes the returned
      `metadata["hits"]` onto `app_state.last_retrieval_hits`. Pinned
      by `test_repl_chat_stashes_last_retrieval_hits`.
- [ ] `/kb-lookup <query>` invokes `KnowledgeBaseLookupSkill()`,
      prints the chunk text and a `hits: N (sources: a.md#0, b.md#2)`
      footer built from `metadata["hits"]`. Pinned by
      `test_kb_lookup_command_prints_chunks_and_sources`.
- [ ] `/kb-lookup` with no args prints `usage: /kb-lookup <query>` and
      returns `CommandResult(message=..., action="continue")`. Pinned
      by `test_kb_lookup_command_no_args_prints_usage`.
- [ ] `/kb-lookup <query>` against an `LLMError` from the recall
      coordinator prints `LLM error: <reason>` and returns. Pinned by
      `test_kb_lookup_command_swallows_llm_error`.
- [ ] `/summarize <text>` invokes `SummarizationSkill()`,
      prints `summary: <output>` and `chars: N -> summary_chars: M`.
      Pinned by `test_summarize_command_prints_summary_and_counts`.
- [ ] `/summarize` with no text prints `usage: /summarize <text>`.
      Pinned by `test_summarize_command_no_args_prints_usage`.
- [ ] `/summarize <text>` against an `LLMError` prints
      `LLM error: <reason>` and returns — never crashes the REPL.
      Pinned by `test_summarize_command_swallows_llm_error`.
- [ ] Both slash commands are listed in `/help` (DO-12 added the help
      coverage; this deliverable registers them so they appear).
- [ ] `/skills/README.md` mentions **both** skills by name and lists
      the DO-11 → DO-13 commands that auto-invoke each one. Pinned by
      `test_skills_readme_mentions_both_skills_and_auto_invocation`.
- [ ] `/skills/knowledge-base-lookup/README.md` has the five required
      sections (`## Purpose`, `## Expected input`, `## Expected output`,
      `## Invocation`, `## Working demo`) and the substring
      `Auto-invoked` is present. Pinned by
      `test_kb_lookup_readme_has_purpose_input_output_invocation_demo`.
- [ ] `/skills/summarization/README.md` has the same five sections and
      `Auto-invoked` is present. Pinned by
      `test_summarization_readme_has_purpose_input_output_invocation_demo`.

## Schema

- [ ] `class SkillError(Exception)` in `domain/skill.py`.
- [ ] `class SkillContext(BaseModel)` in `domain/skill.py`:
  - `llm: LLMClient | None = None`
  - `recall_coordinator: RecallCoordinator | None = None`
  - `model: str = ""`
- [ ] `class SkillResult(BaseModel)` in `domain/skill.py`:
  - `skill: str`
  - `output: str`
  - `metadata: dict[str, Any] = Field(default_factory=dict)`
- [ ] `class Skill(Protocol)` in `domain/skill.py`:
  - `name: str`
  - `description: str`
  - `invoke(self, *, input: str, context: SkillContext) -> SkillResult`
- [ ] `class KnowledgeBaseLookupSkill`:
  - `name: str == "knowledge-base-lookup"`
  - `description: str` (the literal in `objective.md`)
  - `invoke(self, *, input: str, context: SkillContext) -> SkillResult`
- [ ] `class SummarizationSkill`:
  - `name: str == "summarization"`
  - `description: str` (the literal in `objective.md`)
  - `invoke(self, *, input: str, context: SkillContext) -> SkillResult`
- [ ] `class KbLookupCommand`:
  - `name: str == "kb-lookup"`
  - `summary: str == "search the active vector store for relevant chunks"`
  - `execute(self, context: CommandContext) -> CommandResult`
- [ ] `class SummarizeCommand`:
  - `name: str == "summarize"`
  - `summary: str == "summarise text using the active LLM"`
  - `execute(self, context: CommandContext) -> CommandResult`
- [ ] `AppState` (DO-12) gains `last_retrieval_hits: list[dict[str,
      Any]] = field(default_factory=list)`. Default-empty so all DO-12
      tests continue to pass without change.
- [ ] `RecallCoordinator` (DO-13) gains a `results() -> list[dict]`
      accessor that returns the most-recent recall's hit metadata (or
      `[]` if the most-recent call returned no hits or was a
      trivial-gate short-circuit). This is the only schema change to
      a DO-13 module, and it is backward-compatible (the existing
      `recall()` API is unchanged).
- [ ] `/skills/README.md`, `/skills/knowledge-base-lookup/README.md`,
      `/skills/summarization/README.md` exist and contain the sections
      pinned by the behavioral tests above.