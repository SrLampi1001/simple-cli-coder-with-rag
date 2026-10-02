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

``LLMError``, :class:`CompactionError`, ``TimeoutError``, and transient
``RuntimeError`` failures are reported in the completion message so a
failed ``/learn`` never brings down the REPL. Anything else (programming
bug) also surfaces in the message — the REPL must stay alive even for
that.
"""

from __future__ import annotations

import threading

from simple_cli_coder_with_rag.application.compactor import CompactionError
from simple_cli_coder_with_rag.domain.llm_client import LLMError
from simple_cli_coder_with_rag.presentation.commands import (
    CommandContext,
    CommandResult,
)

# Guards against two ``/learn`` runs overlapping (the underlying store +
# vector-store writes are not designed for concurrent writers).
_LEARN_LOCK = threading.Lock()


class LearnCommand:
    """``/learn``: compact the current session and store it."""

    name = "learn"
    summary = "Compact the current session and store it."

    def execute(self, context: CommandContext) -> CommandResult:
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


__all__ = ["LearnCommand"]
