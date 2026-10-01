# DO-10 — File editing

## Goal

The agent can read and edit files in the working directory (and below) using the Anthropic SDK's tool-use API. Edits are sandboxed to a configurable allow-list of paths and cannot escape via path traversal. The agent decides when to use the tool based on the user's prompt. This completes the sixth OBJECTIVES bullet: *"The AI agent can edit files."*

## Source of truth

- `OBJECTIVES.md` — "The AI agent can edit files" + Adapter pattern (Anthropic SDK tool use).
- `docs/development-tools.md` §6 (Anthropic SDK `complete_with_tools` is the seam).

## Acceptance criteria

- [ ] `src/simple_cli_coder_with_rag/domain/file_editor.py` defines:
  ```python
  class FileEditor(Protocol):
      def read(self, path: str) -> str: ...
      def write(self, path: str, content: str) -> None: ...
      def edit(self, path: str, old_text: str, new_text: str) -> None: ...
  ```
- [ ] `src/simple_cli_coder_with_rag/application/file_editor/sandboxed_editor.py` defines `class SandboxedFileEditor`:
  - `__init__(self, root: Path, *, allowed_globs: list[str] | None = None)`. Default `allowed_globs` is `["**/*"]` (everything under `root`).
  - Resolves `path` to an absolute path; rejects paths that escape `root` (e.g., `../foo`). Raises `PathNotAllowed`.
  - `read`, `write`, `edit` operate only inside `root`. `edit` is atomic: read → assert `old_text` is present exactly once → write.
  - `read` raises `FileNotFound` when the file does not exist; `write` and `edit` create parent directories as needed.
- [ ] `src/simple_cli_coder_with_rag/application/file_editor/__init__.py` exports `SandboxedFileEditor`.
- [ ] `AnthropicLLMClient.complete_with_tools` is implemented end-to-end:
  - Calls `anthropic.Anthropic.messages.create(...)` with `tools=[{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]`.
  - Parses the response into `AssistantTurn(content=..., tool_calls=[...])`. Tool-call `arguments` is the parsed `input` dict.
  - On SDK `APIError`, wraps in `LLMError` (same as `complete`).
- [ ] `KnowledgeService.chat` is updated: if `complete_with_tools` returns non-empty `tool_calls`, the service executes them via `FileEditor` and feeds the results back into a follow-up `complete_with_tools` call (one round-trip, max one tool round per turn to keep latency bounded).
- [ ] `Settings` gains:
  - `editor_root: Path = Path.cwd()` (default: current directory at startup).
  - `editor_max_tool_rounds: int = 1` (default).
- [ ] The composition root builds `SandboxedFileEditor(root=settings.editor_root)` and assigns to `AppState`.
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

- Multi-file atomic commits (git).
- Undo/redo.
- Directory creation outside `root`.
- Network file access.
- Streaming tool calls.

## Depends on

- DO-02, DO-03.

## Blocks

- Nothing (final deliverable).
