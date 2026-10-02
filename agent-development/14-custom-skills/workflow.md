# DO-14 workflow

## Subagent delegation

**One subagent.** The Skill Protocol, both skill implementations, the
two slash commands, the small `SessionManager` / `Repl` refactors, and
the three README files are tightly coupled: the slash commands consume
the skill output's exact metadata shape, the chat path passes a specific
`SkillContext`, and the README's "auto-invocation" section has to match
the actual wiring. Splitting risks drift between the README and the
code.

### Context passed to the subagent

- `agent-development/README.md`.
- The four files in this folder.
- `OBJECTIVES.md` (Strategy, Command, Facade, Adapter patterns).
- `docs/development-tools.md` §5, §6, §8 (no extra retries, pydantic).
- The four files of DO-09, DO-11, DO-12, DO-13 — only the parts
  mentioned in `objective.md` (the relevant Protocol definitions and
  the exact surfaces this deliverable touches).
- Nothing else.

## Web-search verification

None required. The Pydantic / Python patterns in this deliverable are
the same as DO-09 / DO-12. The README test greps are written by hand.

## Steps

1. **Pre-flight.** `git status` clean.

2. **Write the test files** from `tests.md` first. Confirm they fail.

3. **Write `src/simple_cli_coder_with_rag/domain/skill.py`** with
   `SkillError`, `SkillContext`, `SkillResult`, `class Skill(Protocol)`.
   Match the schema in `contracts.md` exactly. Pydantic models for the
   data shapes; `Protocol` (not ABC) for `Skill` so skill
   implementations are duck-typed and test fakes don't need inheritance
   — same choice as `LLMClient` (DO-02), `Chunker` (DO-05),
   `Embedder` (DO-06), `VectorStore` (DO-07), `FileEditor` (DO-10).

4. **Write `src/simple_cli_coder_with_rag/application/skills/__init__.py`**
   re-exporting both skills, `Skill`, `SkillResult`, `SkillContext`,
   `SkillError`.

5. **Write `application/skills/knowledge_base_lookup.py`** with
   `KnowledgeBaseLookupSkill`:
   - Constructor takes no arguments (the skill is stateless).
   - `invoke` calls `context.recall_coordinator.recall(input)` to get
     the chunk texts. The joined output uses the same `---` separator
     as `build_chat_messages` (DO-09) for consistency.
   - Then calls `context.recall_coordinator.results()` (the new
     DO-14-friendly accessor; see step 6) to get the hit metadata.
     If `results()` is missing, log at DEBUG and return
     `metadata={"hits": []}`.
   - If `context.recall_coordinator is None`, return the empty
     `SkillResult` (do not raise).

6. **Add `RecallCoordinator.results()` accessor** in
   `src/simple_cli_coder_with_rag/application/recall_coordinator.py`:
   ```python
   def results(self) -> list[dict[str, Any]]:
       """Return the most-recent recall's hit metadata."""
       return list(self._last_results)
   ```
   The coordinator already (DO-13) keeps a `_last_results` list
   alongside `_last_texts`. Expose it. Add `test_coordinator_results_returns_last_hits`
   to the existing `tests/application/test_recall_coordinator.py`
   (DO-09) — the existing tests must not be edited, only appended to.

7. **Write `application/skills/summarization.py`** with
   `SummarizationSkill`:
   - `invoke` builds the two-message prompt from `objective.md`.
     Use the same exact wording as the DO-12 `Compactor.summarize`
     so behaviour is interchangeable.
   - Empty `input.strip()` short-circuits. No `context.model` AND no
     `context.llm.default_model` raises `SkillError("no model
     configured")`.
   - `LLMError` propagates verbatim.

8. **Refactor `SessionManager.maybe_compact`** in
   `src/simple_cli_coder_with_rag/application/session_manager.py`:
   - Replace the `compactor.summarize(transcript)` call with a
     `SummarizationSkill().invoke(input=transcript_text,
     context=SkillContext(llm=self._compactor.llm, model=...))`
     call. The resulting `SkillResult.output` is the summary string.
   - `Compactor.summarize` is **not** modified.
   - The DO-12 tests for `Compactor.summarize` continue to pass.
   - The new `test_session_manager_maybe_compact_uses_summarization_skill`
     passes.

9. **Refactor `Repl._handle_chat`** in
    `src/simple_cli_coder_with_rag/presentation/repl.py`:
    - Replace `recalled = knowledge.recall(line)` with
      ```python
      skill_result = KnowledgeBaseLookupSkill().invoke(
          input=line,
          context=SkillContext(
              llm=self._app_state.llm,
              recall_coordinator=self._app_state.knowledge._coordinator,
              model=self._app_state.knowledge._chat_model,
          ),
      )
      recalled = [skill_result.output] if skill_result.output else []
      self._app_state.last_retrieval_hits = list(skill_result.metadata.get("hits", []))
      ```
    - The captured `_handle_chat` flow continues unchanged from this
      point. `LLMError` is still caught; the missing-recall hit list
      is still tolerated.
    - Add `last_retrieval_hits` to `AppState` (DO-12 module).

10. **Write `presentation/commands/kb_lookup.py`** with
    `KbLookupCommand`:
    - Token parsed from `context.repl` (the existing Command pattern
      splits the input on the first whitespace).
    - Empty query → `usage: /kb-lookup <query>`.
    - Otherwise build a `SkillContext` from
      `app_state.knowledge._coordinator` and the chat model, call
      `KnowledgeBaseLookupSkill().invoke(...)`, print the `output`
      then `hits: N (sources: file#idx, file#idx, ...)` derived
      from `metadata["hits"]`.
    - On `LLMError`, print `LLM error: <reason>` and return
      `CommandResult(action="continue", message=...)`.

11. **Write `presentation/commands/summarize.py`** with
    `SummarizeCommand`:
    - Empty text → `usage: /summarize <text>`.
    - Otherwise call `SummarizationSkill().invoke(input=text,
      context=SkillContext(llm=app_state.llm, model=...))`, print
      `summary: <output>` and `chars: N -> summary_chars: M`.
    - On `LLMError`, print `LLM error: <reason>` and return.

12. **Register both commands** in
    `src/simple_cli_coder_with_rag/cli.py:_build_registry()`:
    ```python
    registry.register(KbLookupCommand())
    registry.register(SummarizeCommand())
    ```
    Place them after the DO-12 commands and before `HelpCommand` so
    `/help` lists them.

13. **Write `/skills/README.md`** (repo root, new file):
    ```md
    # Skills

    The CLI exposes two reusable custom skills. Each is implemented as a
    Strategy behind the project-owned `Skill` Protocol
    (`src/simple_cli_coder_with_rag/domain/skill.py`).

    ## knowledge-base-lookup
    Searches the active vector store for relevant chunks and surfaces
    the file source and similarity score. See
    [`./knowledge-base-lookup/README.md`](./knowledge-base-lookup/README.md).

    ## summarization
    Summarises a chunk of text using the active LLM. See
    [`./summarization/README.md`](./summarization/README.md).

    ## Auto-invocation
    The skills are wired into the existing commands from DO-11 / DO-12
    / DO-13 — the user does not have to invoke them by name:

    | Skill                  | Auto-invoked by                              |
    |------------------------|----------------------------------------------|
    | knowledge-base-lookup  | The chat path on every non-slash prompt (DO-09/DO-13). |
    | summarization          | `/compact` (DO-12) when a session exceeds the model's context window. |
    ```
    Place `/skills/README.md` at the repo root, alongside
    `/skills/knowledge-base-lookup/README.md` and
    `/skills/summarization/README.md`.

14. **Write `/skills/knowledge-base-lookup/README.md`** and
    **`/skills/summarization/README.md`**. Both follow the same five
    H5-headings structure: `## Purpose`, `## Expected input`, `##`
    `Expected output`, `## Invocation`, `## Working demo`. Both
    contain the substring `Auto-invoked` (the doc test greps for it).
    The working-demo sections are short, copy-pasteable REPL
    transcripts that a reviewer can reproduce against a fresh
    `uv run coder`.

15. **Run the gate.** All exit 0.

16. **Manual smoke test** (separate terminal, not committed):
    ```bash
    uv run coder
    ```
    At the prompt:
    ```
    >>> /kb-lookup what is the project structure?
    hits: N (sources: ...)
    >>> /summarize The CLI uses a layered architecture with ...
    summary: ...
    chars: 412 -> summary_chars: 198
    >>> /chats
    <session list — sanity check that DO-12 still works>
    >>> /exit
    ```
    Then run `pre-commit run --all-files` to catch any drift between
    the README's `Auto-invoked` claim and the actual `Repl` /
    `SessionManager` wiring.

17. **Commit (suggested template — adapt to actual changes):**
    ```bash
    git add \
        src/simple_cli_coder_with_rag/domain/skill.py \
        src/simple_cli_coder_with_rag/application/skills \
        src/simple_cli_coder_with_rag/application/recall_coordinator.py \
        src/simple_cli_coder_with_rag/application/session_manager.py \
        src/simple_cli_coder_with_rag/presentation/repl.py \
        src/simple_cli_coder_with_rag/presentation/commands/__init__.py \
        src/simple_cli_coder_with_rag/presentation/commands/kb_lookup.py \
        src/simple_cli_coder_with_rag/presentation/commands/summarize.py \
        src/simple_cli_coder_with_rag/cli.py \
        skills/README.md \
        skills/knowledge-base-lookup/README.md \
        skills/summarization/README.md \
        tests/domain/test_skill.py \
        tests/application/skills \
        tests/application/test_recall_coordinator.py \
        tests/application/test_session_manager_uses_summarization_skill.py \
        tests/presentation/test_repl_chat_uses_kb_lookup_skill.py \
        tests/presentation/commands/test_kb_lookup_command.py \
        tests/presentation/commands/test_summarize_command.py \
        tests/docs/test_skills_readme.py
    git status
    git commit -m "feat(skills): knowledge-base-lookup + summarization skills

    - domain/skill.py: SkillError, SkillContext, SkillResult Pydantic models,
      Skill Protocol (name, description, invoke(*, input, context) -> SkillResult).
    - application/skills/knowledge_base_lookup.py: KnowledgeBaseLookupSkill wraps
      RecallCoordinator.recall (DO-09/DO-13). Returns joined chunk text and a
      metadata['hits'] list of {source, chunk_index, similarity}. Tolerates a
      missing recall coordinator (empty SkillResult, never raises) and a legacy
      coordinator without .results() (hits=[]).
    - application/skills/summarization.py: SummarizationSkill wraps the LLM
      with the DO-12 Compactor.summarize two-message prompt. Empty input
      short-circuits. No model configured raises SkillError. LLMError
      propagates verbatim.
    - application/recall_coordinator.py: gains .results() accessor (backward
      compatible with DO-09; DO-13 already kept _last_results internally).
    - application/session_manager.py: maybe_compact now calls
      SummarizationSkill().invoke instead of compactor.summarize directly.
      Compactor.summarize is NOT modified (DO-12 contract preserved).
    - presentation/repl.py: chat path uses KnowledgeBaseLookupSkill().invoke
      instead of knowledge.recall. metadata['hits'] is stashed on
      AppState.last_retrieval_hits for /memory (DO-12).
    - presentation/commands/{kb_lookup,summarize}.py: /kb-lookup <q> and
      /summarize <text> slash commands print the SkillResult and a one-line
      footer; LLMError is surfaced, never re-raised.
    - cli._build_registry: registers KbLookupCommand and SummarizeCommand.
    - /skills/README.md, /skills/knowledge-base-lookup/README.md,
      /skills/summarization/README.md: five-section docs (Purpose, Input,
      Output, Invocation, Working demo) plus the Auto-invoked paragraph
      that the doc test greps for.

    Satisfies OBJECTIVES.md (Strategy + Command patterns, both unchanged)
    and TL acceptance criterion #5: at least 2 custom skills, both usable
    in a working demo, with the auto-invocation wired into the DO-11 -> DO-13
    commands."
    ```
    **Note:** Adjust the body to reflect what was *actually* implemented. If
    the schema changed, if the slash-command footer format changed, or if a
    third skill was added — update the commit body accordingly.

18. **Documentation consolidation (FINAL STEP — the next DO cannot
    start until this commit lands).** Step 13 + step 14 above create the
    three `/skills/*` README files inline; this step is a **final sweep**
    that catches anything missed, removes stale wording, and commits the
    docs as **one** `docs(do-14):` commit — the **last** commit of this
    DO, separate from the big feature commit above. Scope by file:
    - **README.md** —
        - Add the two new slash commands (`/kb-lookup <query>`,
          `/summarize <text>`) to the slash-commands table; describe
          each in one line, including the footer format
          (`hits: N (sources: ...)` for `/kb-lookup` and
          `chars: N -> summary_chars: M` for `/summarize`).
        - Add a new top-level *Custom skills* section that cross-links
          to `/skills/README.md` and notes that the skills are
          auto-invoked by the chat path (DO-09/DO-13) and `/compact`
          (DO-12) — the user does not have to invoke them by name.
        - Patch any leftover wording that still describes the OLD
          direct `KnowledgeService.recall(...)` call in the chat path
          (DO-09/DO-13); that call now lives inside
          `KnowledgeBaseLookupSkill.invoke`.
        - Verify the *TL acceptance criteria* checklist at the top of
          README (if DO-12 added one) marks "at least 2 custom skills
          documented and demo-able" as ✅.
    - **`/skills/README.md`, `/skills/knowledge-base-lookup/README.md`,
      `/skills/summarization/README.md`** —
        - Confirm all three exist (created by steps 13 + 14) and that
          each follows the five-section structure (`## Purpose`, `##
          Expected input`, `## Expected output`, `## Invocation`, `##
          Working demo`).
        - Confirm the substring `Auto-invoked` is present in each
          (the doc test greps for it — see step 16).
        - Patch any drift between what steps 13/14 wrote and what the
          code does.
    - **`coding-assistance/`** — **NOT created by DO-14**. The
      `coding-assistance/` folder (TL acceptance criterion #6 —
      `README.md` + `prompts.jsonl` of every AI-coding prompt used
      during development) is **out of scope** for DO-14. The
      numbering note in `objective.md` flags that `coding-assistance/`
      is a separate deliverable (originally numbered DO-14, swapped to
      DO-15 under the user's instruction). When that follow-up DO
      lands, its `prompts.jsonl` must include every prompt sent to an
      AI coding assistant across DO-00 → DO-15 — none of which is
      captured today. **Do not** create the folder here; flag it in
      the `docs(do-14):` commit body so the gap is visible from
      `git log`.
    - The sweep produces **one** commit at the very end of DO-14:
        - `docs(do-14): consolidate README + /skills/* READMEs for custom skills; flag coding-assistance/ as follow-up`
        - The commit body lists every file touched and a one-line
          summary of the change in each, and includes a one-line
          `gap: coding-assistance/ README.md and prompts.jsonl still pending (planned follow-up DO).` so the AI-trace gap is visible from the log without grepping the repo.
19. **Post-flight.** `git status` clean.

## Failure modes

- **Skill swallows LLMError and prints an empty `output`** — the chat
  path is built to tolerate empty recall, so the REPL never crashes,
  but the slash-command outputs become blank. Pinned by
  `test_kb_lookup_command_swallows_llm_error` and
  `test_summarize_command_swallows_llm_error`. If those tests fail, the
  command is hiding the error; fix it before merging.
- **DO-12 tests break after the `SessionManager` refactor** — the
  refactor is intentionally non-breaking (`Compactor.summarize` is not
  modified). If a DO-12 test fails, the refactor leaked into DO-12.
  Restore the original `Compactor.summarize` call site.
- **`/skills/README.md` and the wiring diverge** — the doc test
  greps for `Auto-invoked`; if a worker renames a section, the test
  fails. Update the README in lockstep with the code, or update the
  test in lockstep with a deliberate rename.
- **The third skill from TL (structured extraction / source
  explanation) is added without updating the DSL** — out of scope.
  If added, the `Skill` Protocol already accommodates it; only the
  README index and the `AgentSummary` table need to grow. Add it in a
  follow-up commit, not here.
- **`SummarizationSkill` is invoked with `context.llm=None` and
  `context.model=""`** — `SkillError("no model configured")` is the
  expected outcome. Pinned by
  `test_invoke_no_llm_and_no_model_raises_skill_error`. If a worker
  catches the error and prints empty, the test fails — the user must
  see a readable reason, never silent zero output.