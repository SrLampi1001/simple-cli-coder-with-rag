# DO-03 — Agent responds baseline

## Goal

The REPL accepts non-slash input, sends it to the LLM, and prints the response. Slash commands continue to work alongside chat input. This completes the first README bullet: *"The CLI works and the agents answer."*

## Source of truth

- `README.md` — "The CLI works and the agents answer" + Facade pattern.
- `docs/development-tools.md` §6 (LLM), §9 (concurrency model — but concurrency is for RAG retrieval, **not** needed here).

## Acceptance criteria

- [ ] `src/simple_cli_coder_with_rag/application/knowledge_service.py` defines `class KnowledgeService`. It takes `llm: LLMClient` and (optionally) a `retriever` stub.
  - `chat(self, user_message: str, history: list[Message]) -> str` — calls `llm.complete`, returns the response string.
  - `learn(self, session_id: str) -> None` — raises `NotImplementedError` here; DO-04 implements it.
  - `recall(self, query: str) -> list[str]` — returns `[]` here; DO-09 implements it.
- [ ] `src/simple_cli_coder_with_rag/application/prompts.py` defines `build_chat_messages(user_message: str, history: list[Message], recalled: list[str]) -> list[Message]`. For now, `recalled` is unused; DO-09 injects them.
- [ ] `src/simple_cli_coder_with_rag/presentation/repl.py` is updated:
  - When the input does **not** start with `/`, the REPL calls `knowledge_service.chat(input, history)`, prints the response, appends to history.
  - History is maintained for the session (capped at 20 turns; older turns are dropped from the front).
  - The REPL still respects the `exit` action from any command.
- [ ] The composition root in `cli.py` builds `KnowledgeService` and stashes it on `AppState`.
- [ ] `AppState` is extended with `knowledge: KnowledgeService | None = None`.
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

- `/learn` (DO-04).
- Semantic recall before chat (DO-09).
- Tool use (DO-10).
- Streaming responses.
- Markdown rendering of the response.

## Depends on

- DO-00, DO-01, DO-02.

## Blocks

- DO-04 (uses `chat` flow as a reference), DO-09, DO-10.
