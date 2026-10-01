# DO-10 workflow

## Subagent delegation

**One subagent.** The `SandboxedFileEditor`, the `AnthropicLLMClient.complete_with_tools` implementation, the `KnowledgeService.chat` tool loop, and the composition root are tightly coupled. Splitting risks drift in the tool-call schema and message-shape assumptions.

### Context passed to the subagent

- `agent-development/README.md`.
- The four files in this folder.
- `docs/development-tools.md` §6 in full (Anthropic SDK, `complete_with_tools` seam).
- Nothing else.

## Web-search verification

Before relying on the Anthropic SDK's tool-use shape:

1. `websearch "anthropic python sdk tool use messages.create 2026"` — confirm the `tools=[{name, description, input_schema}]` shape and the response's `ToolUseBlock(id, name, input)`. This API has been stable across 2024–2026 but a structural change would break the implementation.

If the shape has changed, update the code and add a `bump: anthropic-sdk <old> -> <new>` line to the commit body.

## Steps

1. **Pre-flight.** `git status` clean.

2. **Write the test files** from `tests.md` first. Confirm they fail.

3. **Write `src/simple_cli_coder_with_rag/domain/file_editor.py`** with the Protocol and the four exceptions.

4. **Write `src/simple_cli_coder_with_rag/application/file_editor/__init__.py`** (empty) and `sandboxed_editor.py` with `SandboxedFileEditor`. Implementation notes:
   - Resolve `path` to absolute via `(self.root / path).resolve()`. If `resolved != self.root` and not `resolved.is_relative_to(self.root)`, raise `PathNotAllowed`.
   - For symlinks, `resolve()` follows them; that's how the symlink-escape test passes.
   - Apply `allowed_globs` via `fnmatch.fnmatch(resolved.relative_to(self.root), glob)`. If no glob matches, raise `PathNotAllowed`.
   - `edit` is atomic: read content, find `old_text` count (must be 1), write new content. If anything raises, re-raise without writing.
   - `write` creates parents via `resolved.parent.mkdir(parents=True, exist_ok=True)`.

5. **Update `AnthropicLLMClient.complete_with_tools`**:
   ```python
   response = self._client.messages.create(
       model=model,
       max_tokens=4096,
       system=...,  # pull system messages from the front of `messages`
       tools=[{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools],
       messages=[{"role": m.role, "content": m.content} for m in messages if m.role != "system"],
   )
   ```
   Walk the response's `content` blocks; collect `TextBlock.text` into `content` and `ToolUseBlock` into `ToolCall(id=..., name=..., arguments=block.input)`. Wrap `APIError` in `LLMError`.

6. **Update `KnowledgeService.chat`** with a tool loop:
   ```python
   def chat(self, user_message, history, recalled):
       messages = build_chat_messages(user_message, history, recalled)
       tools = self._build_tools()  # [ToolSpec(name="read", ...), ToolSpec(name="write", ...), ToolSpec(name="edit", ...)]
       turn = self.llm.complete_with_tools(messages, model=settings.chat_model, tools=tools)
       rounds = 0
       while turn.tool_calls and rounds < settings.editor_max_tool_rounds:
           # Execute each tool call, append results as tool-role messages
           for call in turn.tool_calls:
               result = self._execute_tool(call)  # dispatches to FileEditor
               messages.append(ToolMessage(tool_call_id=call.id, content=result))
           turn = self.llm.complete_with_tools(messages, model=settings.chat_model, tools=tools)
           rounds += 1
       return turn.content
   ```
   Define `ToolMessage` (a new Pydantic model with `role: Literal["tool"]`, `tool_call_id: str`, `content: str`) in `domain/messages.py`. Update `Message` union if present.

   `_execute_tool` catches `PathNotAllowed`, `FileNotFound`, `TextNotFound`, `AmbiguousEdit` and returns a human-readable error string instead of re-raising.

7. **Update `Settings`** in `infrastructure/settings.py`:
   ```python
   editor_root: Path = Path.cwd()
   editor_max_tool_rounds: int = 1
   ```

8. **Update `AppState`** to add `editor: FileEditor | None = None`.

9. **Update composition root** in `cli.py`:
   - `editor = SandboxedFileEditor(root=settings.editor_root)`.
   - `app_state.editor = editor`.
   - Pass `editor` to `KnowledgeService` (constructor takes `editor`).

10. **Run the gate.** All exit 0.

11. **Manual smoke test** (separate terminal, not committed): in a temp directory, `uv run coder`, type `"create a file hello.txt with content 'world'"`. Confirm the file is created and the assistant reports success. Try `"read /etc/passwd"`; confirm the assistant says it's outside the allowed paths.

12. **Commit:**
    ```bash
    git add src/simple_cli_coder_with_rag/domain/file_editor.py \
            src/simple_cli_coder_with_rag/domain/messages.py \
            src/simple_cli_coder_with_rag/application/file_editor \
            src/simple_cli_coder_with_rag/infrastructure/llm/anthropic_client.py \
            src/simple_cli_coder_with_rag/application/knowledge_service.py \
            src/simple_cli_coder_with_rag/infrastructure/settings.py \
            src/simple_cli_coder_with_rag/presentation/commands/__init__.py \
            src/simple_cli_coder_with_rag/cli.py \
            tests/domain/test_file_editor.py \
            tests/application/file_editor \
            tests/infrastructure/test_anthropic_client_tools.py \
            tests/application/test_knowledge_service_chat_with_tools.py
    git status
    git commit -m "feat(editor): SandboxedFileEditor + Anthropic tool-use + chat tool loop

    - domain/file_editor.py: FileEditor Protocol (read, write, edit) and four
      exceptions (PathNotAllowed, FileNotFound, TextNotFound, AmbiguousEdit).
    - application/file_editor/sandboxed_editor.py: SandboxedFileEditor(root,
      allowed_globs). Resolves paths against root; rejects traversal and symlink
      escape. edit() is atomic (read -> assert -> write). write() creates parent
      dirs.
    - domain/messages.py: ToolMessage added to the Message union.
    - infrastructure/llm/anthropic_client.py: complete_with_tools calls
      messages.create with the tool schemas; parses ToolUseBlock into ToolCall.
    - application/knowledge_service.py: chat executes tool calls via FileEditor
      and feeds results back into a follow-up complete_with_tools, capped at
      editor_max_tool_rounds (default 1). Editor exceptions are returned to the
      LLM as text rather than re-raised.
    - Settings.editor_root (Path.cwd by default), editor_max_tool_rounds (1).

    Satisfies README bullet 6: 'The AI agent can edit files'."
    ```

13. **Post-flight.** `git status` clean. **This is the final deliverable.** After this commit, the README's six delivery objectives are all satisfied. The REPL works, `/learn` writes JSON, embeddings work, vectors are stored, semantic search runs before chat, and the agent can edit files.

## Failure modes

- **Anthropic SDK tool-use shape changed:** the `web-search` step will catch it. If not caught, `complete_with_tools` will fail at runtime; the test `test_complete_with_tools_passes_tool_schemas` pins the schema.
- **Sandbox bypass via symlink:** the symlink-escape test pins this. If the test ever passes when it shouldn't, `Path.resolve()` is being misused — it does follow symlinks by default.
- **Tool loop never terminates:** `editor_max_tool_rounds` is the upper bound. Test `test_chat_respects_max_tool_rounds` pins this. If the LLM keeps asking for tools, the service stops after one round and returns whatever it has — the user sees a partial response.
- **`subprocess` / `os.system` introduced for "just in case":** the architectural contract explicitly forbids it. `grep -r "import subprocess" src/simple_cli_coder_with_rag/` should return nothing.
