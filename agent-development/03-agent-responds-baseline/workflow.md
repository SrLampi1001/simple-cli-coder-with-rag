# DO-03 workflow

## Subagent delegation

**One subagent.** The `KnowledgeService`, `prompts`, REPL chat-path integration, and composition-root wiring are tightly coupled.

### Context passed to the subagent

- `agent-development/README.md` (master).
- The four files in this folder.
- `docs/development-tools.md` §6 only (no concurrency yet).
- Nothing else.

## Web-search verification

Not required. The `LLMClient` Protocol from DO-02 is stable; no new dependencies.

## Steps

1. **Pre-flight.** `git status` clean.

2. **Read** `docs/development-tools.md` §6 only.

3. **Write the test files** from `tests.md` first. Confirm they fail.

4. **Write `src/simple_cli_coder_with_rag/application/prompts.py`** with `build_chat_messages`. Signature exactly as in `contracts.md`.

5. **Write `src/simple_cli_coder_with_rag/application/knowledge_service.py`** with `KnowledgeService`. `chat` calls `build_chat_messages` (with `recalled=[]`), then `self.llm.complete(messages, model=...)` (where the model is read from `Settings` — pass it as a constructor arg or read from a passed `Settings`; pick one and stick with it). Return the string. `learn` and `recall` are stubs.

6. **Update `AppState`** in `presentation/commands/__init__.py`:
   - `knowledge: KnowledgeService | None = None`
   - `history: list[Message] = field(default_factory=list)`
   - `history_cap: int = 20`

7. **Update `Repl`** in `presentation/repl.py`:
   - Take `app_state.history` as the history source.
   - On non-slash input: try `chat = app_state.knowledge.chat(...)`; on success, print and append; on `LLMError`, print `f"LLM error: {e}"` and continue.
   - After appending, if `len(history) > 2 * cap`, drop from the front: `history = history[-(2*cap):]`.

8. **Update composition root** in `cli.py`:
   - Instantiate `KnowledgeService(llm=app_state.llm)`.
   - Assign to `app_state.knowledge`.

9. **Run the gate.** All exit 0.

10. **Smoke test** (separate terminal, not committed): with a fake `.env` containing `ANTHROPIC_API_KEY=sk-fake`, run `uv run coder`, type `hello`, observe a chat response (or a graceful `LLMError` if the key is fake — both are acceptable for this smoke test).

11. **Commit (suggested template — adapt to actual changes):**
    ```bash
    git add src/simple_cli_coder_with_rag/application \
            src/simple_cli_coder_with_rag/presentation \
            tests/application tests/presentation/test_repl_chat_path.py
    git status
    git commit -m "feat(chat): KnowledgeService facade, REPL chat path, history cap

    - application/knowledge_service.py: KnowledgeService(chat, learn, recall);
      chat delegates to LLMClient.complete; learn/recall are NotImplementedError/[]
      stubs filled in by DO-04 and DO-09.
    - application/prompts.py: build_chat_messages composes history + user message.
    - presentation/repl.py: non-slash input routes through KnowledgeService.chat,
      response printed to stdout, history appended, history capped at 20 turns.
    - LLMError caught and printed as 'LLM error: <msg>' (no stack trace); REPL
      continues to next prompt.
    - composition root in cli.py builds KnowledgeService and wires AppState.

    Satisfies OBJECTIVES bullet 1: 'The CLI works and the agents answer'."
    ```
    **Note:** The above message is a template. Edit to match actual implementation. If the history cap changed, if error handling differs, if `build_chat_messages` signature changed, or if any stubs were implemented differently — update the commit body accordingly.

12. **Post-flight.** `git status` clean.

## Failure modes

- **`LLMClient` import in `application/`:** a sign the agent imported `AnthropicLLMClient` instead of the `LLMClient` Protocol. Always inject the protocol.
- **History grows unbounded:** the cap test will fail loudly. Drop from the front, not the back.
- **`LLMError` printed twice or with a stack trace:** the REPL must catch *only* `LLMError`, not `Exception`, and must print only the message.
