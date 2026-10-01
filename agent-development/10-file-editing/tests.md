# DO-10 tests

These tests must be written **before** any code in this deliverable.

## Test files

```
tests/domain/
├── test_file_editor.py
└── test_messages.py  (new: tool-role + assistant tool_calls models)

tests/application/file_editor/
├── __init__.py
└── test_sandboxed_editor.py

tests/infrastructure/
└── test_anthropic_client_tools.py  (replaces the stub test from DO-02)

tests/application/
└── test_knowledge_service_chat_with_tools.py
```

## Test functions and assertions

### `tests/domain/test_file_editor.py`

- `test_protocol_declares_methods` — `FileEditor` has the three methods.
- `test_path_not_allowed_is_permission_error` — `issubclass(PathNotAllowed, PermissionError)`.
- `test_text_not_found_is_value_error` — `issubclass(TextNotFound, ValueError)`.
- `test_ambiguous_edit_is_value_error` — `issubclass(AmbiguousEdit, ValueError)`.

### `tests/domain/test_messages.py`

- `test_tool_result_message_has_tool_role` — `ToolResultMessage(tool_call_id="1", content="x").role == "tool"`.
- `test_assistant_message_carries_tool_calls` — `AssistantMessage(content="", tool_calls=[ToolCall(id="1", name="read", arguments={})]).tool_calls` round-trips.
- `test_message_union_accepts_tool_result` — `Message.model_validate({"role": "tool", "tool_call_id": "1", "content": "x"})` validates to `ToolResultMessage`. (Supersedes DO-02's `test_message_union_validation`, which must be updated.)

### `tests/application/file_editor/test_sandboxed_editor.py`

Uses `tmp_path` for `root`.

- `test_read_returns_contents` — write a file, read it back.
- `test_read_missing_raises` — `read("nope")` raises `FileNotFound`.
- `test_write_creates_file` — write, assert file exists with content.
- `test_write_creates_parent_dirs` — write to `"a/b/c.txt"`, assert dirs created.
- `test_edit_replaces_text` — write `"hello world"`, edit `"hello"` → `"hi"`, assert `"hi world"`.
- `test_edit_missing_text_raises` — write `"hello"`, edit `"bye"` → `"x"`, raises `TextNotFound`.
- `test_edit_ambiguous_text_raises` — write `"a a"`, edit `"a"` → `"b"`, raises `AmbiguousEdit`.
- `test_edit_is_atomic` — write `"hello"`, edit fails (TextNotFound), assert file content unchanged.
- `test_read_path_traversal_raises` — `read("../foo")` raises `PathNotAllowed`.
- `test_read_absolute_outside_root_raises` — `read("/etc/passwd")` raises `PathNotAllowed`.
- `test_symlink_escape_raises` — create symlink `tmp_path/link -> /etc/passwd`; `read("link")` raises `PathNotAllowed` (resolved path is outside root).
- `test_allowed_globs_restrict` — `allowed_globs=["**/*.py"]`; `read("foo.txt")` raises; `read("foo.py")` succeeds.
- `test_write_to_disallowed_glob_raises` — same as above for `write`.

### `tests/infrastructure/test_anthropic_client_tools.py`

`anthropic.Anthropic` is patched.

- `test_complete_with_tools_returns_tool_calls` — SDK stub returns a `Message` with a `ToolUseBlock(name="read", id="1", input={"path": "foo.txt"})`. `complete_with_tools` returns `AssistantTurn(content="", tool_calls=[ToolCall(id="1", name="read", arguments={"path": "foo.txt"})])`.
- `test_complete_with_tools_returns_text_only` — SDK stub returns only text; `tool_calls` is `[]`, `content` has the text.
- `test_complete_with_tools_wraps_api_error` — SDK raises `APIError`; client raises `LLMError`.
- `test_complete_with_tools_passes_tool_schemas` — captured SDK call's `tools` arg is a list of dicts with `name`, `description`, `input_schema`.
- `test_assistant_tool_calls_map_to_tool_use_blocks` — given an `AssistantMessage(content="", tool_calls=[...])` in `messages`, the captured SDK `messages` contain an `assistant` entry whose content includes a `{"type": "tool_use", "id": ..., "name": ..., "input": ...}` block.
- `test_tool_result_messages_map_to_user_tool_result_blocks` — given consecutive `ToolResultMessage`s, the captured SDK `messages` contain a single `user` entry whose content is a list of `{"type": "tool_result", "tool_use_id": ...}` blocks. **No `tool` role is ever sent** (assert all SDK roles are `user`/`assistant`).

### `tests/application/test_knowledge_service_chat_with_tools.py`

`LLMClient` is a fake that returns `AssistantTurn` with tool calls on first call and a plain string on the second.

- `test_chat_executes_tool_call_and_returns_followup` — given `tools=[read_tool]`, the service calls `editor.read(path)`, feeds the result into the second `complete_with_tools`, returns the follow-up text.
- `test_chat_appends_assistant_turn_then_tool_result` — captured `messages` on the second call contains (in order) an `AssistantMessage` carrying the `tool_calls`, followed by a `ToolResultMessage` with the read result. This pins the Anthropic-required `tool_use` → `tool_result` ordering.
- `test_chat_respects_max_tool_rounds` — `settings.editor_max_tool_rounds=1`; LLM returns a tool call that itself triggers another tool call (worst case); service stops after one round.
- `test_chat_with_no_tool_calls_returns_first_response` — `complete_with_tools` returns `tool_calls=[]`; service returns `content` directly without a second call.
- `test_chat_propagates_editor_errors` — `editor.read` raises `PathNotAllowed`; the service catches and returns the error message as the assistant's text (NOT re-raised — the user sees "I tried to read ../foo but it's outside the allowed paths.").
- `test_chat_handles_malformed_tool_arguments` — `ToolCall.arguments` missing required keys does not raise `KeyError`; a readable error string is returned to the LLM.

## Why these tests

- The path-traversal and symlink-escape tests pin the sandbox — these are the security-critical tests of the deliverable.
- The atomic-edit test pins the contract that an edit never partially succeeds.
- The `tool_result` test pins the multi-turn message shape required by Anthropic's tool-use protocol.
