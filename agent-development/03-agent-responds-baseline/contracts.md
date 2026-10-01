# DO-03 contracts

## Architectural

- [ ] New modules sit in `application/`:
  - `simple_cli_coder_with_rag.application.knowledge_service`
  - `simple_cli_coder_with_rag.application.prompts`
- [ ] `KnowledgeService` (in `application/`) holds a reference to `LLMClient` (in `domain/`). It does **not** import from `infrastructure`.
- [ ] `import-linter` reports zero violations.
- [ ] No module in `application/` imports from `anthropic` or any vendor SDK.

## Behavioral

- [ ] When the REPL receives non-slash input, it calls `KnowledgeService.chat(input, history)` exactly once and prints the returned string to stdout.
- [ ] The user message and the assistant response are appended to `history` in that order.
- [ ] `history` is capped at 20 turns (40 messages); older messages are dropped from the front.
- [ ] Slash commands continue to work and do **not** enter the chat path.
- [ ] If `LLMClient.complete` raises `LLMError`, the REPL prints `LLM error: <message>` to stdout (NOT stderr — `prompt_toolkit` owns stderr) and continues to the next prompt.
- [ ] `KnowledgeService.learn(session_id)` raises `NotImplementedError("DO-04")`.
- [ ] `KnowledgeService.recall(query)` returns `[]`.

## Schema

- [ ] `class KnowledgeService`:
  - `__init__(self, llm: LLMClient) -> None`
  - `chat(self, user_message: str, history: list[Message]) -> str`
  - `learn(self, session_id: str) -> None`  # raises `NotImplementedError`
  - `recall(self, query: str) -> list[str]`  # returns `[]`
- [ ] `build_chat_messages(user_message: str, history: list[Message], recalled: list[str]) -> list[Message]` returns a list ending with the `UserMessage(user_message)`. The `recalled` parameter is accepted but unused in this deliverable.
- [ ] `AppState` gains `knowledge: KnowledgeService | None = None` and `history: list[Message]` (default empty list, capped at 20 turns).
