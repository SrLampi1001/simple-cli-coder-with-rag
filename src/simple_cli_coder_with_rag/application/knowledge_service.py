"""Application-layer Facade for the LLM-powered chat loop and RAG hooks.

:class:`KnowledgeService` is the single seam between the REPL (presentation
layer) and the LLM-backed ``LLMClient`` Protocol (domain layer). It
exposes four operations:

* :meth:`KnowledgeService.chat` — chat turn (DO-03) extended in DO-10
  with a bounded tool-use loop. When the LLM returns
  ``tool_calls=[...]`` via ``complete_with_tools``, the service executes
  each call via the injected :class:`FileEditor` and feeds the results
  back into a follow-up ``complete_with_tools`` call. The loop is capped
  at ``editor_max_tool_rounds`` so the agent cannot run forever.
* :meth:`KnowledgeService.learn` — read the on-disk session, compact it
  via the compactor, chunk it via the Strategy-picked chunker, embed
  the chunks via the Strategy-picked embedder (DO-06), and persist them
  to the Strategy-picked vector store (DO-07). Returns the chunk count.
* :meth:`KnowledgeService.learn_document` — DO-13. Read a local file
  via the injected :class:`DocumentLoader`, chunk its text via the
  :meth:`FixedSizeChunker.chunk_text` companion method, embed, and
  upsert. The chunks carry ``Chunk.source`` and ``Chunk.chunk_index``
  so the chat-time prompt can cite them.
* :meth:`KnowledgeService.recall` — return relevant chunks via the
  injected :class:`RecallCoordinator` (DO-09). Returns ``[]`` when no
  coordinator is wired or when the coordinator signals a transient
  failure (timeout, embedder still loading). DO-13 changes the return
  shape from ``list[str]`` to ``list[tuple[str, int, str]]``
  (source, chunk_index, text).
* :meth:`KnowledgeService.set_vector_store` — DO-13. Swap the vector
  store (and the retriever wrapped around it) mid-session. Mirrors
  the DO-11 :meth:`set_llm` pattern. Used by ``/vector-store``.

Architectural notes:

* This module imports from :mod:`domain` and from other ``application``
  modules (the compactor, the chunkers, the session store, the recall
  coordinator). It does **not** import from :mod:`infrastructure` — no
  vendor SDKs and no ``Settings`` type. The composition root in
  :mod:`simple_cli_coder_with_rag.cli` resolves ``chat_model`` /
  ``compactor_model`` / ``editor_max_tool_rounds`` from ``Settings`` and
  passes the resolved strings into the constructor.
* ``LLMError`` is **not** caught here. The REPL catches it and prints a
  one-line message; any wrapping would only duplicate work and risk
  swallowing the wrong exception type.
* ``CompactionError`` is likewise propagated verbatim so the REPL sees a
  single failure type.
* Message persistence happens in the REPL (one ``session_store.append``
  per chat turn). ``learn`` therefore reads the full transcript from
  disk via :class:`SessionStore` — it does not need an in-memory
  message list to be passed in.
* ``embedder`` and ``vector_store`` are **optional**. When either is
  ``None`` (legacy wiring from DO-04-DO-06 that has not yet been
  upgraded to DO-07) the service still compacts and chunks, but skips
  the embed -> upsert stage. This keeps the DO-04 and DO-06 test
  suites passing without modification.
* ``coordinator`` (DO-09) replaces the DO-08 ``retriever`` field. It is
  also **optional**. When ``None``, :meth:`recall` short-circuits to
  ``[]`` — keeps pre-DO-09 test suites passing without modification.
* ``editor`` (DO-10) is the ``FileEditor`` Protocol implementation
  built by the composition root (a :class:`SandboxedFileEditor`). When
  ``None``, tool calls in the chat loop are still caught and reported
  as a friendly error string ("editor not configured") so the REPL
  does not crash on legacy / test wirings.
* :meth:`recall` delegates to :class:`RecallCoordinator`, which catches
  the wider ``RuntimeError`` (not :class:`EmbedderNotReady` directly)
  so the coordinator stays decoupled from the embedder module — same
  trick the rest of the codebase uses. The ``TimeoutRetriever`` returns
  ``[]`` on timeout instead of raising, so a timeout shows up as ``[]``
  from the coordinator.
"""

from __future__ import annotations

from pathlib import Path

from simple_cli_coder_with_rag.application.chunkers import (
    FixedSizeChunker,
    SemanticChunker,
)
from simple_cli_coder_with_rag.application.compactor import Compactor
from simple_cli_coder_with_rag.application.prompts import build_chat_messages
from simple_cli_coder_with_rag.application.recall_coordinator import (
    RecallCoordinator,
)
from simple_cli_coder_with_rag.application.session_store import SessionStore
from simple_cli_coder_with_rag.domain.chunk import Chunk
from simple_cli_coder_with_rag.domain.chunker import Chunker
from simple_cli_coder_with_rag.domain.document_loader import DocumentLoader
from simple_cli_coder_with_rag.domain.embedder import Embedder
from simple_cli_coder_with_rag.domain.file_editor import FileEditor
from simple_cli_coder_with_rag.domain.llm_client import LLMClient
from simple_cli_coder_with_rag.domain.messages import (
    AssistantMessage,
    Message,
    ToolCall,
    ToolResultMessage,
    ToolSpec,
)
from simple_cli_coder_with_rag.domain.retriever import Retriever
from simple_cli_coder_with_rag.domain.vector_store import VectorStore

# Tool schemas exposed to the LLM via ``complete_with_tools``. The shape is
# the project-owned ``ToolSpec`` — each adapter translates it to the
# provider's native format. ``read``, ``write``, and ``edit`` mirror the
# three methods on the ``FileEditor`` Protocol; ``path`` is the only
# required argument for all three.
_READ_TOOL_SPEC = ToolSpec(
    name="read",
    description=(
        "Read a UTF-8 text file and return its contents. The path must be inside the sandbox."
    ),
    input_schema={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Path inside the sandbox."}},
        "required": ["path"],
    },
)
_WRITE_TOOL_SPEC = ToolSpec(
    name="write",
    description=(
        "Write content to a UTF-8 text file (creating parent directories "
        "as needed). The path must be inside the sandbox."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path inside the sandbox."},
            "content": {"type": "string", "description": "File contents (UTF-8)."},
        },
        "required": ["path", "content"],
    },
)
_EDIT_TOOL_SPEC = ToolSpec(
    name="edit",
    description=(
        "Replace old_text with new_text in a UTF-8 text file. "
        "The path must be inside the sandbox. The edit is atomic and "
        "refuses to guess when old_text appears more than once."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path inside the sandbox."},
            "old_text": {"type": "string", "description": "Exact text to find."},
            "new_text": {"type": "string", "description": "Replacement text."},
        },
        "required": ["path", "old_text", "new_text"],
    },
)

_ALL_TOOL_SPECS: tuple[ToolSpec, ...] = (_READ_TOOL_SPEC, _WRITE_TOOL_SPEC, _EDIT_TOOL_SPEC)


class KnowledgeService:
    """Facade exposing ``chat`` / ``learn`` / ``recall`` to the REPL."""

    def __init__(
        self,
        llm: LLMClient,
        chat_model: str,
        session_store: SessionStore,
        compactor: Compactor,
        chunker: Chunker,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
        coordinator: RecallCoordinator | None = None,
        editor: FileEditor | None = None,
        editor_max_tool_rounds: int = 1,
    ) -> None:
        self._llm = llm
        self._chat_model = chat_model
        self._session_store = session_store
        self._compactor = compactor
        self._chunker = chunker
        self._embedder = embedder
        self._vector_store = vector_store
        self._coordinator = coordinator
        self._editor = editor
        self._editor_max_tool_rounds = max(0, editor_max_tool_rounds)
        # Most recent ``chunk`` result, populated by ``learn``. ``[]``
        # before the first ``/learn``. DO-06 (embedder) and DO-07
        # (vector store) read this so they can embed and persist
        # exactly the chunks that ``learn`` produced.
        self.last_chunks: list[Chunk] = []

    def set_llm(self, llm: LLMClient) -> None:
        """Swap the LLM adapter mid-session (provider switch).

        Everything else (chunker, embedder, vector store, coordinator,
        editor) is preserved — only the adapter changes. The compactor's
        adapter is swapped too so ``/learn`` keeps working against the
        new provider.
        """
        self._llm = llm
        self._compactor.set_llm(llm)

    def set_model(self, chat_model: str, compactor_model: str | None = None) -> None:
        """Swap the chat / compaction models (provider switch)."""
        self._chat_model = chat_model
        self._compactor.set_model(compactor_model if compactor_model is not None else chat_model)

    def chat(
        self,
        user_message: str,
        history: list[Message],
        recalled: list[tuple[str, int, str]] | None = None,
    ) -> str:
        """Send ``user_message`` (with prior ``history``) to the LLM and return the reply.

        ``recalled`` (DO-09, updated DO-13) is a list of
        ``(source, chunk_index, text)`` tuples retrieved from the
        vector store before this turn. ``None`` (the default) is
        equivalent to ``[]``. The prompt builder injects the recalled
        chunks (with source attribution and the LLM-decides decision
        rules) as a ``SystemMessage`` at the head of the messages
        list when non-empty, so the LLM sees the context **before**
        the user's request.

        Tool loop (DO-10): after the initial ``complete_with_tools``
        call, any non-empty ``tool_calls`` are executed via the injected
        ``FileEditor``, the results are appended as ``ToolResultMessage``s,
        and a follow-up ``complete_with_tools`` call is made. The loop
        is capped at ``editor_max_tool_rounds`` (default 1) so the
        agent cannot run forever. Each round MUST append the assistant
        tool-use turn before the tool results — Anthropic rejects a
        ``tool_result`` whose preceding assistant turn does not contain
        a matching ``tool_use`` block.

        ``LLMError`` propagates verbatim so the caller (the REPL) can decide
        how to surface it. Editor exceptions (and malformed tool
        arguments) are caught and returned as the tool result's
        ``content`` so the LLM can explain the failure to the user.
        """
        messages = build_chat_messages(user_message, history, recalled=recalled or [])
        tools = self._build_tools()

        turn = self._llm.complete_with_tools(messages, model=self._chat_model, tools=tools)

        rounds = 0
        while turn.tool_calls and rounds < self._editor_max_tool_rounds:
            # 1. Echo the assistant's tool-use turn back into the transcript
            #    so the tool results below are paired with it on the wire.
            messages.append(AssistantMessage(content=turn.content, tool_calls=turn.tool_calls))
            # 2. Append one tool-result message per call. The adapter groups
            #    consecutive ``ToolResultMessage``s into a single ``user``
            #    block on the Anthropic wire format.
            for call in turn.tool_calls:
                result_text = self._execute_tool(call)
                messages.append(ToolResultMessage(tool_call_id=call.id, content=result_text))

            # 3. Follow-up call. The loop guard (``rounds < max``) caps it.
            turn = self._llm.complete_with_tools(messages, model=self._chat_model, tools=tools)
            rounds += 1

        return turn.content

    def _build_tools(self) -> list[ToolSpec]:
        """Return the tool specs to expose to the LLM.

        The static ``_ALL_TOOL_SPECS`` tuple is the single source of
        truth. Kept as a method so future code (e.g. config-driven tool
        filtering) can override without changing the chat-loop.
        """
        return list(_ALL_TOOL_SPECS)

    def _execute_tool(self, call: ToolCall) -> str:
        """Run a single ``ToolCall`` and return its textual result.

        Every error path returns a human-readable string (not an
        exception) so the LLM can read it on the next turn and explain
        the failure to the user. The REPL never sees these errors
        directly — the chat loop has already absorbed them.

        Supported tool names:

        * ``read``  — ``{"path": ...}`` → ``FileEditor.read(path)``.
        * ``write`` — ``{"path": ..., "content": ...}`` → ``FileEditor.write(path, content)``.
        * ``edit``  — ``{"path": ..., "old_text": ..., "new_text": ...}``
                      → ``FileEditor.edit(path, old_text, new_text)``.

        Unknown tool names return ``"unknown tool: <name>"``.
        Malformed arguments (missing keys, wrong types) return an
        explicit error string rather than raising ``KeyError`` /
        ``TypeError`.
        """
        if self._editor is None:
            return "editor not configured; tool calls are not available in this session."

        name = call.name
        args = call.arguments or {}

        try:
            if name == "read":
                path = args.get("path")
                if not isinstance(path, str):
                    return self._bad_arg("read", "path", "string")
                return self._editor.read(path)
            if name == "write":
                path = args.get("path")
                content = args.get("content")
                if not isinstance(path, str):
                    return self._bad_arg("write", "path", "string")
                if not isinstance(content, str):
                    return self._bad_arg("write", "content", "string")
                self._editor.write(path, content)
                return f"wrote {len(content)} bytes to {path}"
            if name == "edit":
                path = args.get("path")
                old_text = args.get("old_text")
                new_text = args.get("new_text")
                if not isinstance(path, str):
                    return self._bad_arg("edit", "path", "string")
                if not isinstance(old_text, str):
                    return self._bad_arg("edit", "old_text", "string")
                if not isinstance(new_text, str):
                    return self._bad_arg("edit", "new_text", "string")
                self._editor.edit(path, old_text, new_text)
                return f"edited {path}"
            return f"unknown tool: {name!r}"
        except FileNotFoundError as exc:
            # Covers both the project-owned ``FileNotFound`` and any
            # stdlib ``FileNotFoundError`` that may leak from the editor.
            return f"file not found: {exc}"
        except Exception as exc:
            # Every other editor exception (``PathNotAllowed``,
            # ``TextNotFound``, ``AmbiguousEdit``, ...) is surfaced as a
            # readable string. We do NOT re-raise: the chat loop must
            # stay alive even when the LLM guesses a bad path.
            return f"tool {name!r} failed: {exc}"

    @staticmethod
    def _bad_arg(tool: str, key: str, expected: str) -> str:
        return f"tool {tool!r} received a malformed argument: {key!r} must be a {expected}"

    def learn(
        self,
        session_id: str,
        *,
        messages: list[Message] | None = None,
    ) -> int:
        """Compact, chunk, embed, and persist the on-disk session for ``session_id``.

        Algorithm:

        1. Read the on-disk transcript (returns ``[]`` on a fresh
           session).
        2. Ask the compactor for a structured :class:`CompactedSession`.
           The compactor short-circuits on an empty list without
           contacting the LLM.
        3. Persist the compacted document via ``write_compacted`` (which
           overwrites any prior file — the second ``/learn`` replaces
           the first).
        4. Chunk the compacted document with the configured Strategy
           chunker. Store the result on :attr:`last_chunks`.
        5. **If** an embedder + vector store are configured, embed the
           chunks and upsert them in one batch. The embedder and store
           are wired together because they are the only place that
           knows the embedding dimensionality (``bge-small-en-v1.5`` is
           384-d by default; the embedder publishes the contract).
        6. Return ``len(chunks)`` so the caller (``LearnCommand``) can
           display the count.

        ``LLMError`` and :class:`~simple_cli_coder_with_rag.application.compactor.CompactionError`
        propagate verbatim.
        """
        all_messages = self._session_store.read(session_id) if messages is None else list(messages)
        compacted = self._compactor.compact(session_id, all_messages)
        self._session_store.write_compacted(session_id, compacted)
        self.last_chunks = self._chunker.chunk(compacted)
        if self._embedder is not None and self._vector_store is not None:
            # The embedder loads on a background thread so a cold-cache
            # download never delays the prompt. ``/learn`` needs it
            # synchronously, so block briefly here instead of raising
            # ``EmbedderNotReady`` when the user runs ``/learn`` too early.
            self._embedder.warmup(timeout=60.0)
            vectors = self._embedder.embed_passages([c.text for c in self.last_chunks])
            self._vector_store.upsert(self.last_chunks, vectors)
        return len(self.last_chunks)

    def recall(self, query: str, *, top_k: int | None = None) -> list[tuple[str, int, str]]:
        """Return up to ``top_k`` most relevant chunks as ``(source, chunk_index, text)`` tuples.

        Delegates to the injected :class:`RecallCoordinator`. ``top_k``
        defaults to the coordinator's configured value (``None`` here →
        the coordinator's :attr:`top_k` is used). When no coordinator is
        wired, returns ``[]``.

        DO-13 changes the return type from ``list[str]`` to
        ``list[tuple[str, int, str]]`` so the chat-time prompt builder
        can format chunks with their source attribution. Session
        chunks (DO-04 / DO-09) have ``source == ""`` and
        ``chunk_index == 0``; document chunks (DO-13) carry the
        file path and a per-source index.

        The coordinator itself applies the trivial-prompt gate, the
        similarity threshold, and the ``RuntimeError`` /
        ``TimeoutError`` fail-safes — see
        :class:`~simple_cli_coder_with_rag.application.recall_coordinator.RecallCoordinator`.
        """
        if self._coordinator is None:
            return []
        effective_top_k = top_k if top_k is not None else self._coordinator.top_k
        return self._coordinator.recall(query, top_k=effective_top_k)

    def learn_document(
        self,
        path: Path,
        *,
        loader: DocumentLoader,
    ) -> int:
        """Load ``path``, chunk it, embed, and upsert (DO-13).

        The companion entry point to :meth:`learn` for the
        ``/learn <path>`` flow. Algorithm:

        1. Load the file via the injected ``loader``. The loader
           returns ``(text, DocumentMetadata)`` and propagates
           :class:`UnsupportedDocumentError` / :class:`FileNotFoundError`
           for ``LearnCommand`` to translate into friendly REPL
           messages. The loader is **required** (no default) so the
           application layer stays decoupled from the infrastructure
           package — the composition root in ``cli.py`` wires the
           default :class:`ExtensionDispatchLoader`.
        2. Chunk the text via :meth:`FixedSizeChunker.chunk_text` with
           ``source=metadata.source``. A ``TypeError`` is raised if
           the configured chunker is not a
           :class:`FixedSizeChunker` (the only chunker that
           implements ``chunk_text`` in v1).
        3. **If** an embedder + vector store are configured, warm the
           embedder (block up to 60s on a cold cache) and upsert in
           one batch. When either is ``None`` (legacy / test wirings)
           the chunks are still produced and the method returns the
           count; the caller is responsible for surfacing "no store"
           if it cares.
        4. Return ``len(chunks)`` so the caller (``LearnCommand``)
           can format the chat-time message
           (``learned N chunks from X (md, 1234 bytes)``).

        ``UnsupportedDocumentError`` and :class:`FileNotFoundError`
        propagate verbatim so ``LearnCommand`` can translate them
        into friendly REPL messages — the service stays free of UI
        concerns.
        """
        text, metadata = loader.load(path)
        if not text:
            # PDF with no extractable text — caller surfaces a friendly
            # message ("PDF has no extractable text.").
            self.last_chunks = []
            return 0

        chunker = self._chunker
        # ``chunk_text`` is a method on ``FixedSizeChunker`` only;
        # ``SemanticChunker`` does not implement it (its contract is
        # one chunk per record, which does not apply to raw document
        # text). The composition root wires a ``FixedSizeChunker`` for
        # the document path; this assertion guards a misconfiguration.
        if not isinstance(chunker, FixedSizeChunker):
            raise TypeError(
                f"learn_document requires a FixedSizeChunker (got {type(chunker).__name__})"
            )

        self.last_chunks = chunker.chunk_text(text, source=metadata.source)
        if self._embedder is not None and self._vector_store is not None:
            self._embedder.warmup(timeout=60.0)
            vectors = self._embedder.embed_passages([c.text for c in self.last_chunks])
            self._vector_store.upsert(self.last_chunks, vectors)
        return len(self.last_chunks)

    def set_vector_store(
        self,
        vector_store: VectorStore,
        retriever: Retriever,
    ) -> None:
        """Swap the vector store (and its retriever) mid-session (DO-13).

        Mirrors the DO-11 :meth:`set_llm` pattern. Used by
        ``/vector-store`` when the user wants to flip between
        backends. Everything else (chunker, embedder, editor, LLM)
        is preserved — only the store + retriever change.

        The new ``retriever`` is the **already-TimeoutRetriever-
        wrapped** instance; the coordinator rebuilds itself against
        it (mirroring the composition root's wiring). The gate,
        ``top_k``, and similarity threshold are preserved so the
        user's retrieval tuning survives the swap — only the
        backend changes.

        The chat-time ``recall`` flow uses the new store on the next
        turn.
        """
        self._vector_store = vector_store
        if self._coordinator is not None:
            self._coordinator = RecallCoordinator(
                retriever=retriever,
                gate=self._coordinator.gate,
                top_k=self._coordinator.top_k,
                similarity_threshold=self._coordinator.similarity_threshold,
            )


def build_chunker(strategy: str) -> Chunker:
    """Resolve a chunker Strategy from ``strategy``.

    Pulled out of the composition root so unit tests can exercise the
    same selection logic without spinning up a Settings instance. New
    strategies are added by extending the ``if`` chain here.
    """
    if strategy == "semantic":
        return SemanticChunker()
    if strategy == "fixed":
        return FixedSizeChunker()
    raise ValueError(f"unknown chunker strategy: {strategy!r}")


__all__ = ["KnowledgeService", "build_chunker"]
