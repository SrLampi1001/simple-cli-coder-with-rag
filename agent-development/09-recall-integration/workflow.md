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

3. **Write `src/simple_cli_coder_with_rag/application/trivial_gate.py`** with `TrivialGate`. `is_trivial` is `len(prompt) <= max_chars or len(prompt.split()) <= max_words`. Empty string is trivial (0 chars, 0 words).

4. **Update `Settings`** in `infrastructure/settings.py` with the four new fields.

5. **Write `src/simple_cli_coder_with_rag/application/recall_coordinator.py`** with `RecallCoordinator`. Implementation notes:
   - `recall(prompt)`:
     - If `self.gate.is_trivial(prompt)`: `logger.debug("trivial prompt, skipping recall"); return []`.
     - Submit `self.retriever.retrieve(prompt, top_k=self.top_k)` to `self.executor` via `executor.submit(self.retriever.retrieve, prompt, top_k=self.top_k)`.
     - Wrap with `TimeoutRetriever` **inside** `recall` (do not require the caller to wrap). Implementation: `try: future.result(timeout=settings.retrieval_timeout_seconds) except FuturesTimeout: ...`.
     - On `EmbedderNotReady`: catch and return `[]`, log at DEBUG.
     - On `TimeoutError`: catch and return `[]`, log at DEBUG.
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
   - Build `RecallCoordinator(retriever=..., executor=..., gate=..., top_k=settings.recall_top_k, similarity_threshold=settings.recall_similarity_threshold)`.
   - Pass to `KnowledgeService` (constructor takes `coordinator` instead of `retriever`).

10. **Run the gate.** All exit 0.

11. **Manual smoke test** (separate terminal, not committed): with a fake `ANTHROPIC_API_KEY`, run `/learn` after a couple of chat turns (DO-04–07 must already be in place). Then in a new session, type a non-trivial prompt; observe the recall injection in the log file (not stdout — loguru writes to file).

12. **Commit:**
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
      or <=4 words.
    - application/recall_coordinator.py: RecallCoordinator wraps the retriever in
      TimeoutRetriever, filters by similarity >= threshold, returns chunk texts;
      EmbedderNotReady and timeout both degrade to [] silently (DEBUG log).
    - application/prompts.py: build_chat_messages injects recalled chunks as a
      SystemMessage at the head of the messages list when recalled is non-empty.
    - presentation/repl.py: chat path calls knowledge.recall(input) before
      knowledge.chat(...), passes result to build_chat_messages. Slash commands
      do not trigger recall.
    - Settings: recall_top_k=3, recall_similarity_threshold=0.5, trivial gate tunables.

    Satisfies README bullet 5: 'A prompt triggers semantic search and retrieves
    the important context'."
    ```

13. **Post-flight.** `git status` clean.

## Failure modes

- **`build_chat_messages` system message placed after the user message:** recall must be at the head; otherwise the LLM sees the user request before the context. The `test_recalled_preserves_history_order` test pins the order.
- **Trivial gate threshold too aggressive:** the boundary tests catch `>` vs `>=` mistakes. Stay inclusive.
- **Recall fires for `/learn`:** slash commands must hit the dispatch table before the recall path. Pin with `test_repl_skips_recall_for_slash_command`.
