# DO-10 contracts

## Architectural

- [ ] New modules:
  - `simple_cli_coder_with_rag.domain.file_editor` (Protocol + exceptions)
  - `simple_cli_coder_with_rag.application.file_editor.sandboxed_editor`
- [ ] `import-linter` reports zero violations.
- [ ] No application-layer module imports `os.system`, `subprocess`, or any shell-execution library.

## Behavioral

- [ ] `SandboxedFileEditor(root=tmp_path).read("foo.txt")` returns the file contents.
- [ ] `SandboxedFileEditor(root=tmp_path).read("missing.txt")` raises `FileNotFound`.
- [ ] `SandboxedFileEditor(root=tmp_path).write("foo.txt", "hello")` creates the file with content `"hello"`.
- [ ] `SandboxedFileEditor(root=tmp_path).write("nested/dir/foo.txt", "x")` creates parent directories.
- [ ] `SandboxedFileEditor(root=tmp_path).edit("foo.txt", "hello", "world")` replaces `"hello"` with `"world"`.
- [ ] `SandboxedFileEditor(root=tmp_path).edit("foo.txt", "absent", "x")` raises `TextNotFound`.
- [ ] `SandboxedFileEditor(root=tmp_path).edit("foo.txt", "hello\nhello", "world")` raises `AmbiguousEdit` (old_text appears twice).
- [ ] `SandboxedFileEditor(root=tmp_path).read("../etc/passwd")` raises `PathNotAllowed`.
- [ ] `SandboxedFileEditor(root=tmp_path).read("/etc/passwd")` raises `PathNotAllowed`.
- [ ] `SandboxedFileEditor(root=tmp_path, allowed_globs=["**/*.py"]).read("foo.txt")` raises `PathNotAllowed`.
- [ ] `SandboxedFileEditor(root=tmp_path, allowed_globs=["**/*.py"]).read("foo.py")` succeeds.
- [ ] `AnthropicLLMClient.complete_with_tools(messages, model, tools)` against a mocked SDK that returns a tool-use block returns an `AssistantTurn` with the parsed `ToolCall(id, name, arguments)`.
- [ ] `KnowledgeService.chat` executes a `read` tool call via `SandboxedFileEditor.read` and feeds the result into a follow-up `complete_with_tools` call; the final response is the assistant's follow-up text.
- [ ] `KnowledgeService.chat` does **not** execute more than `editor_max_tool_rounds` (default 1) tool rounds per turn; if the LLM returns more tool calls than that, the service stops and returns the partial result.

## Schema

- [ ] `class FileEditor(Protocol)`:
  - `read(self, path: str) -> str`
  - `write(self, path: str, content: str) -> None`
  - `edit(self, path: str, old_text: str, new_text: str) -> None`
- [ ] `class PathNotAllowed(PermissionError)` in `domain/file_editor.py`.
- [ ] `class FileNotFound(FileNotFoundError)` (re-export from stdlib; defined in `domain/file_editor.py` for consumers).
- [ ] `class TextNotFound(ValueError)` in `domain/file_editor.py`.
- [ ] `class AmbiguousEdit(ValueError)` in `domain/file_editor.py`.
- [ ] `class SandboxedFileEditor`:
  - `__init__(self, root: Path, *, allowed_globs: list[str] | None = None) -> None`
  - `read(self, path: str) -> str`
  - `write(self, path: str, content: str) -> None`
  - `edit(self, path: str, old_text: str, new_text: str) -> None`
- [ ] `AnthropicLLMClient.complete_with_tools(self, messages, *, model, tools) -> AssistantTurn` — full implementation.
- [ ] `Settings.editor_root: Path = Path.cwd()`.
- [ ] `Settings.editor_max_tool_rounds: int = 1`.
- [ ] `AppState.editor: FileEditor | None = None`.
