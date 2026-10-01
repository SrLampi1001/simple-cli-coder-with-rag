# DO-09 workflow

## Subagent delegation

**One subagent.** The trivial gate, recall coordinator, prompt builder update, and REPL integration are tightly coupled. Splitting risks the gate being bypassed.

### Context passed to the subagent

- `agent-development/README.md`.
- The four files in this folder.
- `docs/development-tools.md` §5 (concurrency, threshold, top-k), §9 (concurrency model).
- Nothing else.

## Web-search verification

Not required.

## Steps

1. **Pre-flight.** `git status` clean.

2. **Write the test files** from `tests.md` first. Confirm they fail.

3. **Write `src/simple_cli_coder_with_rag/application/trivial_gate.py`** with `TrivialGate`. `is_trivial` is `len(prompt) <= max_chars and len(prompt.split()) <= max_words`. Empty string is trivial (0 chars, 0 words). **Use `and`, not `or`**: with `or`, a single long word (e.g. `"a" * 25`) has 1 word ≤ 4 and would wrongly count as trivial, contradicting the DO-09 contract and `test_long_string_is_not_trivial`.

4. **Update `Settings`** in `infrastructure/settings.py` with the four new fields.

5. **Write `src/simple_cli_coder_with_rag/application/recall_coordinator.py`** with `RecallCoordinator`. Implementation notes:
   - `recall(prompt)`:
     - If `self.gate.is_trivial(prompt)`: `logger.debug("trivial prompt, skipping recall"); return []`.
     - Call `self.retriever.retrieve(prompt, top_k=self.top_k)` **directly**. The injected `Retriever` is already `TimeoutRetriever`-wrapped by the composition root (DO-08), so bounded latency is the Decorator's job — do **not** submit to an executor or wrap again here (double-wrapping nests executors and defeats the shared `RetrievalExecutor`).
     - On `EmbedderNotReady`: catch and return `[]`, log at DEBUG.
     - On `TimeoutError`: catch and return `[]`, log at DEBUG. This is defensive only: a `TimeoutRetriever` returns `[]` rather than raising, but a custom retriever could raise.
     - Filter results by `similarity >= self.similarity_threshold`; return `[r.chunk.text for r in filtered]`.

6. **Update `KnowledgeService.recall`** to take an optional `top_k` override and delegate to `self.coordinator.recall(prompt, top_k=top_k or self.coordinator.top_k)`.

7. **Update `build_chat_messages`** in `application/prompts.py`:
   ```python
   messages: list[Message] = []
   if recalled:
       sys_content = "The following context may be relevant:\n\n" + "\n\n---\n\n".join(recalled)
       messages.append(SystemMessage(content=sys_content))
   messages.extend(history)
   messages.append(UserMessage(content=user_message))
   return messages
   ```

8. **Update `Repl`** in `presentation/repl.py`:
   - Before `chat`, call `recalled = app_state.knowledge.recall(input)`.
   - Pass `recalled` to a new private helper or call `build_chat_messages` directly with the result.

9. **Update composition root** in `cli.py`:
   - Build `TrivialGate(max_chars=settings.trivial_gate_max_chars, max_words=settings.trivial_gate_max_words)`.
   - Build `RecallCoordinator(retriever=<the TimeoutRetriever from DO-08>, gate=gate, top_k=settings.recall_top_k, similarity_threshold=settings.recall_similarity_threshold)`. The coordinator takes the **already-wrapped** retriever; it does not own an executor.
   - Pass to `KnowledgeService` (constructor takes `coordinator` instead of `retriever`).

10. **Run the gate.** All exit 0. **`test_recall_latency_under_threshold` is part of the gate** — its 100 ms assertion is the UX budget for recall. If it fails:
    - **Stop and report to the user.** Recall latency is not negligible and the OBJECTIVES latency tip ("Run retrieval concurrently while you prepare the rest of the request") has been regressed.
    - **Resolution path:** implement overlap with the LLM call. Sketch:
      1. Introduce `LLMCallExecutor(max_workers=1)` (a separate executor — `RetrievalExecutor` is scoped to retrieval only, see DO-08 contracts).
      2. In `KnowledgeService.chat`, `llm_future = llm_call_executor.submit(self.llm.complete_with_tools, prepped_messages, ...)` **before** awaiting recall.
      3. After recall completes, `messages = build_chat_messages_with_recall(...)` and pass the updated messages list to a second `llm_call_executor.submit` only if the first future finished; otherwise `llm_future.result()` (with a small additional timeout) on the prepped list, then send the follow-up with recall appended as an additional user turn ("here is context that arrived while you were thinking…") instead of mutating the in-flight messages.
      4. Wire `LLMCallExecutor.shutdown()` to the REPL exit hook alongside `RetrievalExecutor.shutdown()`.
      5. Add `test_chat_overlaps_recall_with_llm_call` (asserts `complete_with_tools` is submitted before `recall` finishes when recall latency is artificially inflated) and re-run `test_recall_latency_under_threshold` (it should now pass even with higher absolute latency because the user-perceived pause is hidden).
    - **Do not** simply raise the 100 ms threshold. The threshold exists to catch this regression; raising it would silence the alarm.

11. **Manual smoke test** (separate terminal, not committed): recall only produces something to inject if the vector store is non-empty. Either use a **real** API key to run real chat turns and `/learn` (DO-04–07 must already be in place), or pre-seed the store with a test helper. Then start a new session, type a non-trivial prompt, and observe the recall injection in the log file (not stdout — loguru writes to file). A fake key alone stores zero chunks, so the injection will be empty and the smoke test will be inconclusive. Also observe the wall-clock pause between typing the prompt and the first LLM token — it should be subjectively instantaneous (< 200 ms); if you can count a one-Mississippi, the latency test is the wrong threshold and the LLM-call overlap sketch in step 10 must be implemented.

12. **Commit (suggested template — adapt to actual changes):**
    ```bash
    git add src/simple_cli_coder_with_rag/application/trivial_gate.py \
            src/simple_cli_coder_with_rag/application/recall_coordinator.py \
            src/simple_cli_coder_with_rag/application/prompts.py \
            src/simple_cli_coder_with_rag/application/knowledge_service.py \
            src/simple_cli_coder_with_rag/presentation/repl.py \
            src/simple_cli_coder_with_rag/infrastructure/settings.py \
            src/simple_cli_coder_with_rag/cli.py \
            tests/application/test_trivial_gate.py \
            tests/application/test_recall_coordinator.py \
            tests/application/test_prompts_with_recall.py \
            tests/application/test_knowledge_service_recall_with_coordinator.py \
            tests/presentation/test_repl_recall_path.py
    git status
    git commit -m "feat(rag): recall before chat, trivial-prompt gate, similarity threshold, top-k=3

    - application/trivial_gate.py: TrivialGate skips retrieval for prompts <=20 chars
      and <=4 words (use AND, not OR — single long words must not be trivial).
    - application/recall_coordinator.py: RecallCoordinator delegates to the
      TimeoutRetriever-wrapped Retriever built by DO-08; filters by similarity >=
      threshold; EmbedderNotReady and raised TimeoutError both degrade to []
      silently (DEBUG log). The coordinator does NOT own an executor — timeout
      is the TimeoutRetriever's job.
    - application/prompts.py: build_chat_messages injects recalled chunks as a
      SystemMessage at the head of the messages list when recalled is non-empty.
    - presentation/repl.py: chat path calls knowledge.recall(input) before
      knowledge.chat(...), passes result to build_chat_messages. Slash commands
      do not trigger recall.
    - Settings: recall_top_k=3, recall_similarity_threshold=0.5, trivial gate tunables.
    - Recall latency budget: 100 ms end-to-end on a non-trivial prompt, pinned
      by test_recall_latency_under_threshold. If the test fails, overlap the
      LLM call with recall (LLMCallExecutor, sketched in workflow.md step 10).

    Satisfies OBJECTIVES bullet 5: 'A prompt triggers semantic search and retrieves
    the important context'. True concurrency with the LLM call is deferred and
    is the documented resolution if the latency budget is exceeded."
    ```
    **Note:** The above message is a template. If the gate thresholds changed, if the coordinator's error handling differs, if the injected context format (SystemMessage) changed, if the recall budget was revised, or if `KnowledgeService.recall` signature/return type evolved — update the commit body to reflect the actual implementation.

13. **Post-flight.** `git status` clean.

## Failure modes

- **`build_chat_messages` system message placed after the user message:** recall must be at the head; otherwise the LLM sees the user request before the context. The `test_recalled_preserves_history_order` test pins the order.
- **Trivial gate threshold too aggressive:** the boundary tests catch `>` vs `>=` mistakes. Stay inclusive.
- **Recall fires for `/learn`:** slash commands must hit the dispatch table before the recall path. Pin with `test_repl_skips_recall_for_slash_command`.
