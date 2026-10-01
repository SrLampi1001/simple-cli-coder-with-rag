# DO-09 contracts

## Architectural

- [ ] New modules:
  - `simple_cli_coder_with_rag.application.trivial_gate`
  - `simple_cli_coder_with_rag.application.recall_coordinator`
- [ ] `RecallCoordinator` lives in `application/`.
- [ ] `import-linter` reports zero violations.
- [ ] The chat path in `presentation/repl.py` calls into `application/recall_coordinator` via `KnowledgeService`, not directly into the retriever.

## Behavioral

- [ ] `TrivialGate(max_chars=20, max_words=4).is_trivial("hi")` returns True.
- [ ] `TrivialGate(max_chars=20, max_words=4).is_trivial("why does ModuleNotFoundError happen")` returns False.
- [ ] `TrivialGate(max_chars=20, max_words=4).is_trivial("a" * 25)` returns False (long string).
- [ ] `RecallCoordinator.recall("hi")` returns `[]` and does **not** call the retriever.
- [ ] `RecallCoordinator.recall(long_prompt)` calls the retriever with `top_k=settings.recall_top_k` (default 3) and returns the texts of chunks with `similarity >= settings.recall_similarity_threshold`.
- [ ] If the retriever raises `EmbedderNotReady`, `recall` returns `[]` and logs at DEBUG.
- [ ] If the executor times out, `recall` returns `[]` and logs at DEBUG.
- [ ] `build_chat_messages(user, history, recalled=["a", "b"])` returns `[SystemMessage("The following context may be relevant:\n\na\n\n---\n\nb"), *history, UserMessage(user)]`.
- [ ] `build_chat_messages(user, history, recalled=[])` returns `[*history, UserMessage(user)]` (no extra system message).
- [ ] REPL chat path calls `knowledge.recall(input)` before `knowledge.chat(...)` and passes the result to `build_chat_messages`.
- [ ] Slash commands (`/help`, `/exit`, `/clear`, `/version`, `/learn`) do **not** trigger recall.

## Schema

- [ ] `class TrivialGate`:
  - `__init__(self, *, max_chars: int = 20, max_words: int = 4) -> None`
  - `is_trivial(self, prompt: str) -> bool`
- [ ] `class RecallCoordinator`:
  - `__init__(self, retriever: Retriever, executor: RetrievalExecutor, gate: TrivialGate, *, top_k: int, similarity_threshold: float) -> None`
  - `recall(self, prompt: str) -> list[str]`
- [ ] `build_chat_messages(user_message: str, history: list[Message], recalled: list[str]) -> list[Message]` — signature unchanged from DO-03; behavior updated.
- [ ] `Settings.recall_top_k: int = 3`.
- [ ] `Settings.recall_similarity_threshold: float = 0.5`.
- [ ] `Settings.trivial_gate_max_chars: int = 20`.
- [ ] `Settings.trivial_gate_max_words: int = 4`.
- [ ] `KnowledgeService.recall(self, prompt: str, *, top_k: int | None = None) -> list[str]` — accepts an override (used by tests).
