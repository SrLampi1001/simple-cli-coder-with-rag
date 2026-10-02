"""``/learn`` command — compact the current session, chunk it, and store it.

This is the user-facing surface of the DO-04 + DO-05 pipeline. The command:

1. Pulls ``session_id``, ``history``, and ``session_store`` off
   :class:`AppState`.
2. Persists any in-memory history messages to the session store
   (idempotent — skips messages already on disk).
3. Snapshots the transcript **now** and hands that snapshot to
   :meth:`KnowledgeService.learn` on a background thread, so the user
   can keep chatting while the LLM compact + embed + upsert runs.
   Later turns never leak into an in-flight ``/learn``.
4. Prints a one-line result (``learned N chunks`` / ``learn failed: ...``)
   when the background run finishes.

DO-13 added an optional ``<path>`` argument that switches the command
into the **document ingestion** path: ``/learn <path>`` loads the file
via the injected :class:`DocumentLoader`, chunks it with
:meth:`FixedSizeChunker.chunk_text`, embeds, and upserts. The two
modes are mutually exclusive — ``/learn`` with no args compacts the
session, ``/learn <path>`` ingests a document. Both run on the
background thread (so the user can keep chatting) and both report the
chunk count when done.

``LLMError``, :class:`CompactionError`, ``TimeoutError``, and transient
``RuntimeError`` failures are reported in the completion message so a
failed ``/learn`` never brings down the REPL. Anything else (programming
bug) also surfaces in the message — the REPL must stay alive even for
that.
"""

from __future__ import annotations

import threading
from pathlib import Path

from simple_cli_coder_with_rag.application.compactor import CompactionError
from simple_cli_coder_with_rag.domain.document_loader import (
    DocumentLoader,
    UnsupportedDocumentError,
)
from simple_cli_coder_with_rag.domain.llm_client import LLMError
from simple_cli_coder_with_rag.presentation.commands import (
    CommandContext,
    CommandResult,
)

# Guards against two ``/learn`` runs overlapping (the underlying store +
# vector-store writes are not designed for concurrent writers).
_LEARN_LOCK = threading.Lock()

# Default document loader wired by the composition root in ``cli.py``.
# Kept as a module-level reference so ``LearnCommand`` can reach it
# without a constructor parameter — the alternative (passing it via
# ``AppState``) would couple the command to the infrastructure layer
# for no real benefit.
_DOCUMENT_LOADER: DocumentLoader | None = None


def set_default_document_loader(loader: DocumentLoader) -> None:
    """Register the process-wide default :class:`DocumentLoader` (DO-13).

    Called once by the composition root in ``cli.py``. The default
    survives the lifetime of the process so ``LearnCommand`` does not
    need to receive the loader via :class:`AppState` (which would
    couple the command to the infrastructure package).
    """
    global _DOCUMENT_LOADER
    _DOCUMENT_LOADER = loader


class LearnCommand:
    """``/learn``: compact the current session, or ingest a document (DO-13)."""

    name = "learn"
    summary = "Compact the current session, or ingest a document with `/learn <path>`."

    def execute(self, context: CommandContext) -> CommandResult:
        args = context.args.strip()
        if args:
            return self._learn_document(args, context)

        knowledge = context.app_state.knowledge
        session_id = context.app_state.session_id
        history = context.app_state.history
        session_store = context.app_state.session_store
        if knowledge is None:
            return CommandResult(
                action="continue", message="learn failed: knowledge not configured"
            )

        # Persist any in-memory history that is not yet on disk. The REPL
        # does this on each chat turn in DO-04's contract; the idempotency
        # check protects against re-persisting on a repeated ``/learn``.
        if session_store is not None:
            existing = session_store.read(session_id)
            seen: set[tuple[str, str]] = {(m.role, m.content) for m in existing}
            for msg in history:
                key = (msg.role, msg.content)
                if key in seen:
                    continue
                session_store.append(session_id, msg)
                seen.add(key)
            snapshot = session_store.read(session_id)
        else:
            snapshot = list(history)

        if not _LEARN_LOCK.acquire(blocking=False):
            return CommandResult(
                action="continue", message="learn is already running; wait for it to finish"
            )

        def _run() -> None:
            try:
                count = knowledge.learn(session_id, messages=snapshot)
                print(f"learn: done — learned {count} chunks", flush=True)
            except (LLMError, CompactionError, TimeoutError, RuntimeError) as exc:
                print(f"learn failed: {exc}", flush=True)
            except Exception as exc:  # never let a background crash kill the REPL
                print(f"learn failed: {exc}", flush=True)
            finally:
                _LEARN_LOCK.release()

        threading.Thread(target=_run, name="learn-worker", daemon=True).start()
        return CommandResult(
            action="continue",
            message=(
                "learning session in the background — you can keep chatting; I'll report when done"
            ),
        )

    def _learn_document(self, raw_path: str, context: CommandContext) -> CommandResult:
        """Run the document ingestion path (``/learn <path>``) — DO-13.

        Validates the path, kicks the loader + chunker + embedder + upsert
        on a background thread, and returns an immediate
        ``learning <path> in the background …`` message. The final
        ``learned N chunks from <path> (md, 1234 bytes, page_count=1)``
        message is printed when the background run finishes.

        All error paths return a friendly message; nothing raises out
        of this method. The background thread prints the result or
        failure to stdout (the REPL's print sink) so the user sees
        the same surface as the session path.
        """
        knowledge = context.app_state.knowledge
        if knowledge is None:
            return CommandResult(
                action="continue", message="learn failed: knowledge not configured"
            )
        if _DOCUMENT_LOADER is None:
            return CommandResult(
                action="continue",
                message="learn failed: document loader not configured (boot bug)",
            )

        expanded = Path(raw_path).expanduser()
        if not expanded.exists() or not expanded.is_file():
            return CommandResult(action="continue", message=f"{raw_path} does not exist.")

        if not _LEARN_LOCK.acquire(blocking=False):
            return CommandResult(
                action="continue", message="learn is already running; wait for it to finish"
            )

        # Snapshot the path so the background thread cannot race a
        # subsequent ``/learn <other>`` call.
        path = expanded
        loader = _DOCUMENT_LOADER

        def _run() -> None:
            try:
                text, metadata = loader.load(path)
                if not text:
                    page_count = metadata.page_count
                    page_note = f" (page_count={page_count})" if page_count is not None else ""
                    print(
                        f"learn failed: PDF has no extractable text{page_note}.",
                        flush=True,
                    )
                    return
                count = knowledge.learn_document(path, loader=loader)
                page_count = metadata.page_count
                page_note = f", page_count={page_count}" if page_count is not None else ""
                print(
                    f"learn: done — learned {count} chunks from "
                    f"{path} ({metadata.file_type}, {metadata.byte_size} bytes"
                    f"{page_note}).",
                    flush=True,
                )
            except UnsupportedDocumentError as exc:
                print(f"learn failed: {exc}", flush=True)
            except FileNotFoundError as exc:
                print(f"learn failed: {exc}", flush=True)
            except (LLMError, CompactionError, TimeoutError, RuntimeError) as exc:
                print(f"learn failed: {exc}", flush=True)
            except Exception as exc:  # never let a background crash kill the REPL
                print(f"learn failed: {exc}", flush=True)
            finally:
                _LEARN_LOCK.release()

        threading.Thread(target=_run, name="learn-doc-worker", daemon=True).start()
        return CommandResult(
            action="continue",
            message=(
                f"learning document {path} in the background — "
                f"you can keep chatting; I'll report when done"
            ),
        )


__all__ = ["LearnCommand", "set_default_document_loader"]
