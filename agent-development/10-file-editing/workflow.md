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

5. **Update `AnthropicLLMClient.complete_with_tools`** (this is the adapter's job: the application layer must never know the wire shape):
   ```python
   response = self._client.messages.create(
       model=model,
       max_tokens=4096,
       system=<concatenated system messages>,
       tools=[{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools],
       messages=self._to_sdk_messages(messages),
   )
   ```
   Walk the response's `content` blocks; collect `TextBlock.text` into `content` and `ToolUseBlock` into `ToolCall(id=..., name=..., arguments=block.input)`. Wrap `APIError` in `LLMError`.

   **`_to_sdk_messages` translation rules (Anthropic Messages API only allows `user` and `assistant` roles — there is no `tool` role):**
   - `SystemMessage` → pulled out into the `system=` parameter (never placed in `messages`).
   - `UserMessage` → `{"role": "user", "content": m.content}`.
   - `AssistantMessage` → `{"role": "assistant", "content": [ ... ]}` where the block list is `[{"type": "text", "text": m.content}]` (omit when empty) followed by one `{"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}` per `m.tool_calls`.
   - `ToolResultMessage` → must be sent as a **`user`** message whose content is a list of `{"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}` blocks. **Group consecutive `ToolResultMessage`s into a single user message** (multiple `tool_result` blocks) so the tool results belong to the preceding assistant `tool_use` turn.
   - Interleaving rule: an assistant `tool_use` turn must be immediately followed by the matching `tool_result` (user) turn. Never emit an orphan `tool_use` or `tool_result`.

6. **Update `KnowledgeService.chat`** with a tool loop that appends the assistant tool-use turn **and** the tool results (Anthropic rejects a `tool_result` with no preceding `tool_use`):
   ```python
   def chat(self, user_message, history, recalled):
       messages = build_chat_messages(user_message, history, recalled)
       tools = self._build_tools()  # [ToolSpec(name="read", ...), ToolSpec(name="write", ...), ToolSpec(name="edit", ...)]
       turn = self.llm.complete_with_tools(messages, model=settings.chat_model, tools=tools)
       rounds = 0
       while turn.tool_calls and rounds < settings.editor_max_tool_rounds:
           # 1. echo the assistant's tool-use turn back into the transcript
           messages.append(AssistantMessage(content=turn.content, tool_calls=turn.tool_calls))
           # 2. append one tool-result message per call (adapter groups them)
           for call in turn.tool_calls:
               result = self._execute_tool(call)  # dispatches to FileEditor
               messages.append(ToolResultMessage(tool_call_id=call.id, content=result))
           turn = self.llm.complete_with_tools(messages, model=settings.chat_model, tools=tools)
           rounds += 1
       return turn.content
   ```
   In `domain/messages.py`, **extend `AssistantMessage`** with `tool_calls: list[ToolCall] = Field(default_factory=list)` (defaults keep DO-02/DO-03 callers valid) and add a new `ToolResultMessage` model with `role: Literal["tool"] = "tool"`, `tool_call_id: str`, `content: str`. Add it to the `Message` union. Update the DO-02 test `test_message_union_validation` (which asserts `role="tool"` is rejected) accordingly — this deliverable intentionally introduces the tool role at the domain level; only the adapter maps it to the wire format.

   `_execute_tool` catches `PathNotAllowed`, `FileNotFound` (the `FileNotFoundError` re-export), `TextNotFound`, `AmbiguousEdit` and returns a human-readable error string instead of re-raising. It must also handle a malformed tool input (missing/extra keys) by returning an error string rather than raising `KeyError`.

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

12. **Commit (suggested template — adapt to actual changes):**
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
            tests/domain/test_messages.py \
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
    - domain/messages.py: AssistantMessage gains tool_calls; ToolResultMessage
      added to the Message union.
    - infrastructure/llm/anthropic_client.py: complete_with_tools calls
      messages.create with the tool schemas; parses ToolUseBlock into ToolCall;
      maps AssistantMessage.tool_calls to tool_use blocks and ToolResultMessage to
      a user message with tool_result blocks (Anthropic has no tool role).
    - application/knowledge_service.py: chat echoes the assistant tool-use turn,
      executes tool calls via FileEditor, appends ToolResultMessages, and feeds them
      back into a follow-up complete_with_tools, capped at editor_max_tool_rounds
      (default 1). Editor exceptions and malformed tool input are returned to the
      LLM as text rather than re-raised.
    - Settings.editor_root (Path.cwd by default), editor_max_tool_rounds (1).

    Satisfies README bullet 6: 'The AI agent can edit files'."
    ```
    **Note:** The above message is a template. If the tool schema changed, if the sandbox rules were tightened/loosened, if `_execute_tool` handles more/fewer exceptions, if the tool loop cap differs, or if the message models changed shape — update the commit body to match the actual implementation.

13. **Post-flight.** `git status` clean. **This is the final deliverable.** After this commit, the README's six delivery objectives are all satisfied. The REPL works, `/learn` writes JSON, embeddings work, vectors are stored, semantic search runs before chat, and the agent can edit files.

## Failure modes

- **Anthropic SDK tool-use shape changed:** the `web-search` step will catch it. If not caught, `complete_with_tools` will fail at runtime; the test `test_complete_with_tools_passes_tool_schemas` pins the schema.
- **`tool_result` sent without a preceding `tool_use`, or with `role="tool"`:** the API returns a 400. The adapter must translate `ToolResultMessage` into a **user** message with a `tool_result` block, and `KnowledgeService.chat` must append the assistant `tool_use` turn first. Pinned by `test_assistant_tool_calls_map_to_tool_use_blocks`, `test_tool_result_messages_map_to_user_tool_result_blocks`, and `test_chat_appends_assistant_turn_then_tool_result`.
- **Sandbox bypass via symlink:** the symlink-escape test pins this. If the test ever passes when it shouldn't, `Path.resolve()` is being misused — it does follow symlinks by default.
- **Tool loop never terminates:** `editor_max_tool_rounds` is the upper bound. Test `test_chat_respects_max_tool_rounds` pins this. If the LLM keeps asking for tools, the service stops after one round and returns whatever it has — the user sees a partial response.
- **`subprocess` / `os.system` introduced for "just in case":** the architectural contract explicitly forbids it. `grep -r "import subprocess" src/simple_cli_coder_with_rag/` should return nothing.
