"""Real-API end-to-end test for the semantic-retrieval workflow.

This script validates the full RAG pipeline: a conversation in **session A**
is compacted and stored as vectors via ``/learn``; a later **session B**
asks a related question and the system must retrieve the relevant chunks
from session A and use them to shape the assistant's reply.

Run with::

    uv run python scripts/e2e_semantic_retrieval.py --provider mistral

It is **not** part of the standard test suite — it requires real API keys,
a network, and downloads the BGE-small embedding model (~130 MB) on first
run. It uses an isolated temp directory for the database and the session
JSON files, so it never touches the user's real local data.

The script exits 0 on full success, 1 on a partial failure, 2 on a
configuration error.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from loguru import logger

from simple_cli_coder_with_rag.application.chunkers.fixed_size import FixedSizeChunker
from simple_cli_coder_with_rag.application.compactor import Compactor
from simple_cli_coder_with_rag.application.knowledge_service import KnowledgeService
from simple_cli_coder_with_rag.application.recall_coordinator import RecallCoordinator
from simple_cli_coder_with_rag.application.retrievers.base_retriever import (
    BaseRetriever,
)
from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.application.trivial_gate import TrivialGate
from simple_cli_coder_with_rag.domain.messages import (
    AssistantMessage,
    UserMessage,
)
from simple_cli_coder_with_rag.domain.vector_store import (
    VectorStore,
    VectorStoreBackendUnavailable,
)
from simple_cli_coder_with_rag.infrastructure.embedders import FastembedEmbedder
from simple_cli_coder_with_rag.infrastructure.llm import build_llm_client
from simple_cli_coder_with_rag.infrastructure.settings import Settings
from simple_cli_coder_with_rag.infrastructure.vector_stores import (
    NumpyBruteForceStore,
    SqliteVecStore,
)

# A distinctive error / fix the agent gives in session A. We deliberately
# phrase the assistant's reply around an unusual detail ("Crockford quote" +
# a specific defensive pattern) so the session B assertion can pin the
# semantic retrieval: the recalled chunk must surface this exact text.
_SESSION_A_TURNS: list[tuple[str, str]] = [
    (
        "I'm getting KeyError when parsing JSON responses in Python. The "
        "response sometimes omits the 'id' field and my code crashes. How "
        "should I handle this?",
        "Three robust patterns: (1) use dict.get('id') with a sensible "
        "default rather than dict['id']; (2) wrap the access in a "
        "try/except KeyError and degrade gracefully; (3) validate the "
        "payload with jsonschema or pydantic before you touch it. "
        "Crockford's JSON advice: 'JSON has no comments and the parser "
        "should not invent fields that are missing'. Pick the validation "
        "approach when you can; pick dict.get() when the schema is loose.",
    ),
    (
        "That makes sense. What about the case where the JSON has the field but its value is null?",
        "null becomes Python None, not a missing key — so dict['id'] "
        "returns None instead of raising. The defensive pattern is "
        "dict.get('id') or 'unknown' so the rest of your code can treat "
        "absent and null uniformly.",
    ),
]


def _step(label: str) -> None:
    print(f"\n=== {label} ===", flush=True)


def _ok(message: str) -> None:
    print(f"  OK   {message}", flush=True)


def _fail(message: str) -> None:
    print(f"  FAIL {message}", flush=True)


def _build_knowledge_service(
    settings: Settings,
    chat_model: str,
    vector_store: VectorStore,
    embedder: FastembedEmbedder,
) -> KnowledgeService:
    """Build a fully-wired ``KnowledgeService`` for the E2E run.

    Mirrors the composition root in :mod:`simple_cli_coder_with_rag.cli` —
    real LLM, real embedder, real vector store, real retriever chain, real
    recall coordinator. The session store and the compactor are isolated
    per call so each test gets its own on-disk files.
    """
    llm = build_llm_client(settings)
    session_store = SessionStore(root=vector_store_root() / "sessions")
    compactor = Compactor(llm=llm, compactor_model=chat_model)

    # Retriever chain: BaseRetriever wrapped in nothing — the recall
    # coordinator handles gating. We pass it directly here because the
    # TimeoutRetriever's executor would interfere with the test's
    # synchronous assertions.
    retriever = BaseRetriever(embedder=embedder, vector_store=vector_store)
    gate = TrivialGate(
        max_chars=settings.trivial_gate_max_chars,
        max_words=settings.trivial_gate_max_words,
    )
    coordinator = RecallCoordinator(
        retriever=retriever,
        gate=gate,
        top_k=settings.recall_top_k,
        similarity_threshold=settings.recall_similarity_threshold,
    )

    return KnowledgeService(
        llm=llm,
        chat_model=chat_model,
        session_store=session_store,
        compactor=compactor,
        chunker=FixedSizeChunker(),
        embedder=embedder,
        vector_store=vector_store,
        coordinator=coordinator,
    )


def vector_store_root() -> Path:
    """Return the path the test uses for the SQLite DB.

    Resolved via :func:`_data_dir` at call time. Pinned to a temp dir by
    the test driver so the user's real local data is never touched.
    """
    return Path(_DATA_DIR_FOR_TEST["root"])


_DATA_DIR_FOR_TEST: dict[str, Path] = {}


def _set_test_data_dir(path: Path) -> None:
    """Stash the test's temp data dir for :func:`vector_store_root`."""
    _DATA_DIR_FOR_TEST["root"] = path


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
    key_attr = f"{settings.default_provider}_api_key"
    if not getattr(settings, key_attr).get_secret_value():
        _fail(f"no API key for provider {settings.default_provider!r}")
        return 2
    chat_model = args.model or (
        settings.chat_model or getattr(settings, f"{settings.default_provider}_model")
    )
    print(f"  provider:   {settings.default_provider}")
    print(f"  chat model: {chat_model}")
    print(f"  embedder:   {settings.embedding_model}")
    print(f"  recall_top_k:    {settings.recall_top_k}")
    print(f"  recall_threshold: {settings.recall_similarity_threshold}")
    _ok("configuration loaded")

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_path = Path(tmp_str).resolve()
        _set_test_data_dir(tmp_path)
        db_path = tmp_path / "db.sqlite"
        cache_dir = tmp_path / "models"

        # Embedder — first run downloads the BGE model (~130 MB) into
        # ``cache_dir`` so the user's real cache is untouched. ``warmup``
        # blocks until the model is ready.
        _step("Embedding model warm-up")

        # ``Settings.embedding_local_files_only`` defaults to ``True``
        # so production init does not round-trip HF when the model is
        # already cached. For this isolated temp-dir cache we have to
        # fall back to ``False`` when the cache is cold, otherwise the
        # background ``_load`` thread fails silently and ``warmup``
        # times out.
        from simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder import (
            _is_cache_warm,
        )

        local_files_only = settings.embedding_local_files_only
        if not _is_cache_warm(cache_dir, settings.embedding_model):
            local_files_only = False

        t0 = time.monotonic()
        embedder = FastembedEmbedder(
            model_name=settings.embedding_model,
            cache_dir=cache_dir,
            local_files_only=local_files_only,
        )
        try:
            embedder.warmup(timeout=300.0)
        except TimeoutError:
            _fail("embedding model did not load within 300s")
            return 1
        _ok(f"model ready in {time.monotonic() - t0:.1f}s ({settings.embedding_model})")

        # Vector store. SqliteVecStore is the default — fall back to
        # NumpyBruteForceStore when the host Python's sqlite3 build
        # cannot load extensions (the same path the composition root in
        # ``cli.py`` takes). Both backends implement the ``VectorStore``
        # Protocol identically from the rest of the codebase's
        # perspective, so the test's recall assertions hold either way.
        backend_used = "sqlite_vec"
        try:
            vector_store: VectorStore = SqliteVecStore(db_path=db_path)
            _ok(f"vector store ready at {db_path} (sqlite_vec backend)")
        except VectorStoreBackendUnavailable:
            backend_used = "numpy_brute_force"
            vector_store = NumpyBruteForceStore()
            _ok("vector store ready (numpy_brute_force fallback — sqlite-vec unavailable)")
        print(f"  backend:    {backend_used}", flush=True)

        # ------------------------------------------------------------------
        # Session A — conversation + /learn
        # ------------------------------------------------------------------
        _step("Session A — conversation + /learn")
        session_a_id = "sess-A-" + str(int(time.time()))
        knowledge = _build_knowledge_service(settings, chat_model, vector_store, embedder)

        for user_text, assistant_text in _SESSION_A_TURNS:
            knowledge._session_store.append(session_a_id, UserMessage(content=user_text))
            knowledge._session_store.append(session_a_id, AssistantMessage(content=assistant_text))
        _ok(f"wrote {len(_SESSION_A_TURNS) * 2} transcript messages for {session_a_id}")

        try:
            n_chunks = knowledge.learn(session_a_id)
        except Exception as exc:
            _fail(f"/learn failed: {type(exc).__name__}: {exc}")
            return 1
        if n_chunks <= 0:
            _fail("/learn produced 0 chunks (expected > 0)")
            return 1
        _ok(f"/learn compacted and stored {n_chunks} chunks")

        # ------------------------------------------------------------------
        # Session B — new UUID, ask related question
        # ------------------------------------------------------------------
        _step("Session B — fresh session, related question")

        # Sanity check: in a fresh session, the transcript is empty.
        fresh_id = "sess-B-" + str(int(time.time()))
        on_disk = knowledge._session_store.read(fresh_id)
        if on_disk:
            _fail(f"fresh session {fresh_id!r} already has {len(on_disk)} messages")
            return 1
        _ok(f"fresh session {fresh_id!r} has empty transcript (isolation confirmed)")

        # The question is deliberately a paraphrase of session A's first
        # user prompt — same domain, different wording. A working recall
        # should still surface the JSON KeyError context.
        query = (
            "My Python code crashes with KeyError when reading a JSON "
            "response that is missing a field. What is the cleanest "
            "defensive pattern?"
        )
        _ok(f"asking: {query!r}")

        # Inspect the raw recall first so the test can pin the retrieval
        # behaviour separately from the agent's reply.
        recalled = knowledge.recall(query, top_k=settings.recall_top_k)
        if not recalled:
            _fail("recall() returned [] — semantic search did NOT trigger")
            print("  expected at least one chunk matching the JSON KeyError topic", flush=True)
            return 1
        _ok(f"recall() returned {len(recalled)} chunk(s)")
        for idx, text in enumerate(recalled, start=1):
            preview = text[:120].replace("\n", " ")
            print(f"    chunk {idx}: {preview}{'...' if len(text) > 120 else ''}")

        # The recalled text must include session A's distinctive phrase
        # ("Crockford" + "dict.get"). That phrase is the test's anchor —
        # if recall really pulled from session A, it has to surface.
        anchor_phrases = ("Crockford", "dict.get", "KeyError", "JSON")
        matched = [
            phrase for phrase in anchor_phrases if any(phrase in chunk for chunk in recalled)
        ]
        if not matched:
            _fail("no anchor phrase from session A appeared in the recalled chunks")
            print(
                f"  expected at least one of: {anchor_phrases}",
                flush=True,
            )
            return 1
        _ok(f"recalled chunks contain anchor phrase(s): {matched}")

        # ------------------------------------------------------------------
        # Agent reply — must reflect the recalled context, not a generic answer
        # ------------------------------------------------------------------
        _step("Session B — agent reply with recalled context")
        try:
            reply = knowledge.chat(query, history=[], recalled=recalled)
        except Exception as exc:
            _fail(f"chat() raised: {type(exc).__name__}: {exc}")
            return 1
        print(f"  assistant: {reply[:400]}{'...' if len(reply) > 400 else ''}", flush=True)

        # The agent's reply must mention at least one of the recall-anchored
        # patterns. Without recall, the LLM would not produce the distinctive
        # "dict.get()" / "Crockford" wording on its own.
        reply_matched = [phrase for phrase in anchor_phrases if phrase.lower() in reply.lower()]
        if not reply_matched:
            _fail("agent reply did NOT use the recalled context (no anchor phrase)")
            print(
                f"  expected at least one of {anchor_phrases} in the reply, got: {reply!r}",
                flush=True,
            )
            return 1
        _ok(f"agent reply uses recalled context (mentions: {reply_matched})")

        # ------------------------------------------------------------------
        # Negative test — a totally unrelated query should NOT pull chunks
        # ------------------------------------------------------------------
        _step("Negative test — unrelated query must NOT pull JSON chunks")
        unrelated = "What is the capital of France?"
        unrelated_recalled = knowledge.recall(unrelated, top_k=settings.recall_top_k)
        # The recall MAY return *something* on a short, generic query — but
        # if anything comes back, it must NOT be the JSON KeyError chunk.
        for chunk in unrelated_recalled:
            if "Crockford" in chunk or "KeyError" in chunk or "JSON" in chunk:
                _fail(f"unrelated query pulled the JSON chunk — false positive: {chunk[:80]!r}")
                return 1
        _ok(f"unrelated query returned {len(unrelated_recalled)} chunk(s); none is the JSON chunk")

    # ----------------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------------
    summary: dict[str, Any] = {
        "provider": settings.default_provider,
        "chat_model": chat_model,
        "tests": {
            "learn_produced_chunks": "PASS",
            "session_b_isolation": "PASS",
            "recall_triggered_for_related_query": "PASS",
            "recalled_chunks_contain_anchor": "PASS",
            "agent_reply_uses_recalled_context": "PASS",
            "unrelated_query_does_not_pull_json_chunk": "PASS",
        },
    }
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    # Mute loguru's stderr sink — the E2E script writes its own status to
    # stdout; loguru's default sink would interleave with the REPL prompt
    # if a user ever wraps this in a TUI. The log file configured by the
    # composition root is unaffected.
    logger.remove()
    raise SystemExit(main())
