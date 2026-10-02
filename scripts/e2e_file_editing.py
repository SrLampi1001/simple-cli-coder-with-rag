"""Real-API end-to-end test for the file-editing capability (DO-10).

This script validates the full agent loop with a real LLM provider:

1. Load ``Settings`` from the user's ``.env`` (pydantic-settings; never
   reads the file directly).
2. Build the ``LLMClient`` for the active provider via the composition
   root's :func:`build_llm_client`.
3. Build a real :class:`SandboxedFileEditor` rooted at a temp dir.
4. Wire the editor into a :class:`KnowledgeService`.
5. Ask the LLM to **read** a file inside the sandbox; assert the
   assistant's reply contains the file's content.
6. Ask the LLM to **write** a new file; assert the file was created on
   disk with the requested content.

It is **not** part of the standard test suite — it requires real API
keys and a network. Run it manually after ``uv sync``:

    uv run python scripts/e2e_file_editing.py

The script exits with status 0 on full success, 1 on a partial failure,
2 on a configuration error (no key for the active provider).

It is also deliberately non-chatty: a single ``print`` line per step,
the model's final reply, and a clear PASS/FAIL summary.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from simple_cli_coder_with_rag.application.chunkers.fixed_size import FixedSizeChunker
from simple_cli_coder_with_rag.application.compactor import Compactor
from simple_cli_coder_with_rag.application.file_editor import SandboxedFileEditor
from simple_cli_coder_with_rag.application.knowledge_service import KnowledgeService
from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.infrastructure.llm import build_llm_client
from simple_cli_coder_with_rag.infrastructure.settings import Settings


def _step(label: str) -> None:
    print(f"\n=== {label} ===", flush=True)


def _ok(message: str) -> None:
    print(f"  OK   {message}", flush=True)


def _fail(message: str) -> None:
    print(f"  FAIL {message}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        choices=("nvidia", "mistral", "minimax"),
        default=None,
        help="override the active provider (default: settings.default_provider)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="override the chat model (default: per-provider default)",
    )
    args = parser.parse_args()

    try:
        settings = Settings()
    except RuntimeError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    if args.provider is not None:
        settings.default_provider = args.provider  # type: ignore[assignment]

    _step("Configuration")
    print(f"  provider:   {settings.default_provider}")
    key_attr = f"{settings.default_provider}_api_key"
    if not getattr(settings, key_attr).get_secret_value():
        _fail(f"no API key for provider {settings.default_provider!r}")
        return 2
    _ok(f"API key for {settings.default_provider!r} is set")

    llm = build_llm_client(settings)
    chat_model = args.model or (
        settings.chat_model or getattr(settings, f"{settings.default_provider}_model")
    )
    print(f"  chat model: {chat_model}")

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_path = Path(tmp_str).resolve()

        # 1) Pre-create a file the agent will be asked to read.
        read_target = tmp_path / "hello.txt"
        read_target.write_text("hello from a real e2e test", encoding="utf-8")
        _ok(f"wrote pre-existing file: {read_target}")

        # 2) Build the KnowledgeService with the sandbox editor wired in.
        session_store = SessionStore(root=tmp_path / "sessions")
        compactor = Compactor(llm=llm, compactor_model=chat_model)
        editor = SandboxedFileEditor(root=tmp_path)
        knowledge = KnowledgeService(
            llm=llm,
            chat_model=chat_model,
            session_store=session_store,
            compactor=compactor,
            chunker=FixedSizeChunker(),
            editor=editor,
            editor_max_tool_rounds=1,
        )

        # ------------------------------------------------------------------
        # Test 1: agent reads a file
        # ------------------------------------------------------------------
        _step("Test 1: agent reads hello.txt via the read tool")
        prompt_read = (
            "Please read the file 'hello.txt' in the current directory using the "
            "available read tool, then tell me exactly what is in it. Reply with a "
            "single short sentence that quotes the file's contents verbatim."
        )
        try:
            reply_read = knowledge.chat(prompt_read, history=[])
        except Exception as exc:  # pragma: no cover - network errors
            _fail(f"chat() raised: {type(exc).__name__}: {exc}")
            return 1
        print(f"  assistant: {reply_read!r}")
        if "hello from a real e2e test" in reply_read:
            _ok("assistant quoted the file contents")
        else:
            _fail("assistant reply did NOT contain the file contents")
            return 1

        # ------------------------------------------------------------------
        # Test 2: agent writes a new file
        # ------------------------------------------------------------------
        _step("Test 2: agent writes a new file 'note.md' via the write tool")
        write_target = tmp_path / "note.md"
        if write_target.exists():
            write_target.unlink()
        prompt_write = (
            "Use the write tool to create a new file 'note.md' containing exactly "
            "the text 'e2e wrote this'. After the write, reply with a single "
            "sentence confirming the file was created. Do NOT read the file again."
        )
        try:
            reply_write = knowledge.chat(prompt_write, history=[])
        except Exception as exc:  # pragma: no cover - network errors
            _fail(f"chat() raised: {type(exc).__name__}: {exc}")
            return 1
        print(f"  assistant: {reply_write!r}")
        if write_target.exists():
            actual = write_target.read_text(encoding="utf-8")
            if actual == "e2e wrote this":
                _ok(f"file created with expected content: {actual!r}")
            else:
                _fail(f"file exists but content mismatch: {actual!r}")
                return 1
        else:
            _fail("file was NOT created")
            return 1

        # ------------------------------------------------------------------
        # Test 3: sandbox blocks out-of-bounds read
        # ------------------------------------------------------------------
        _step("Test 3: sandbox blocks reads outside the editor root")
        prompt_escape = (
            "Use the read tool to read the file '/etc/passwd' and tell me its "
            "contents. If the tool refuses, report the rejection."
        )
        try:
            reply_escape = knowledge.chat(prompt_escape, history=[])
        except Exception as exc:  # pragma: no cover - network errors
            _fail(f"chat() raised: {type(exc).__name__}: {exc}")
            return 1
        print(f"  assistant: {reply_escape!r}")
        # The agent should NOT have dumped /etc/passwd content; we expect a
        # refusal or an error string.
        if "root:x:" in reply_escape or "/bin/" in reply_escape:
            _fail("assistant leaked the contents of /etc/passwd — sandbox bypassed!")
            return 1
        _ok("assistant did not leak /etc/passwd content")

    # ----------------------------------------------------------------------
    # Done — print a structured summary as JSON for downstream tooling.
    # ----------------------------------------------------------------------
    summary: dict[str, Any] = {
        "provider": settings.default_provider,
        "chat_model": chat_model,
        "tests": {
            "read": "PASS",
            "write": "PASS",
            "sandbox_blocks_escape": "PASS",
        },
    }
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
