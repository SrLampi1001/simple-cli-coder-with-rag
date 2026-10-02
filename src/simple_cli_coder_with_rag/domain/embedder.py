"""Strategy interface for the embedding model.

The embedder is the **third Strategy seam** in the RAG pipeline
(``OBJECTIVES.md`` — "the embedder (local vs. API)"). The local
implementation lives in
:mod:`simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder`
and is the default for v1. A remote (HTTP) implementation can be added
behind the same Protocol by installing the ``[remote-embedder]`` extra
and wiring a second adapter — the rest of the codebase does not need to
change.

The two-method split (``embed_query`` / ``embed_passages``) is a
deliberate choice from ``docs/development-tools.md`` §5: BGE-family
models retrieve better when **queries** carry the model's instruction
prefix and **passages** do not. ``fastembed`` exposes those two entry
points and bakes the prefix in internally; we mirror them here so the
caller does not have to know which model is wired.

``warmup`` / ``is_ready`` exist because the local model takes real
wall-clock time to load (~hundreds of ms on first download). The
composition root starts the load on a background thread so the prompt
appears immediately. Downstream code (``KnowledgeService.recall`` in
DO-09) gates retrieval on :meth:`Embedder.is_ready` and degrades
gracefully to "no memories" when the model is still loading.

Architectural note: this module imports from :mod:`domain` only. It
does not import from :mod:`infrastructure` or from vendor SDKs.
``import-linter`` enforces this on the ``layered-architecture``
contract, plus a ``forbidden_imports`` rule that keeps ``fastembed``
out of every layer except ``infrastructure/embedders/``.
"""

from __future__ import annotations

from typing import Protocol


class Embedder(Protocol):
    """Strategy interface for turning text into dense vectors."""

    def embed_query(self, text: str) -> list[float]:
        """Embed a single user query and return a vector.

        Implementations may apply a model-specific instruction prefix
        internally (e.g. the BGE "Represent this sentence..." prefix
        baked into ``fastembed``'s ``query_embed``).
        """
        ...

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of passages and return one vector per input.

        Implementations must not apply the query instruction prefix;
        passages are stored verbatim.
        """
        ...

    def warmup(self, *, timeout: float | None = None) -> None:
        """Block until the model is loaded and ready to embed.

        ``timeout=None`` waits indefinitely. ``timeout=N`` waits at most
        ``N`` seconds; if the model is still not ready at the deadline
        the implementation must raise :class:`TimeoutError`.

        The composition root does **not** call :meth:`warmup` itself;
        the background thread drives the model load. This method exists
        for tests and for the few cases (e.g. tests, smoke checks) that
        need a synchronous ready signal.
        """
        ...

    def is_ready(self) -> bool:
        """Return ``True`` if the model has finished loading.

        Cheap, lock-free read — call it from any thread. Used by the
        REPL and by the retriever to decide whether to call
        :meth:`embed_query` or to short-circuit to "no memories" while
        the model is still warming up.
        """
        ...


class EmbedderNotReady(RuntimeError):  # noqa: N818 — name pinned by the DO-06 contracts
    """Raised when an embed call is made before the model is ready.

    A ``RuntimeError`` subclass — not a generic ``Exception`` — so the
    surrounding service
    (:class:`~simple_cli_coder_with_rag.application.knowledge_service.KnowledgeService`
    via ``recall`` in DO-09, and the retriever in DO-08) can catch
    ``RuntimeError`` without importing this domain module. Catching
    ``EmbedderNotReady`` directly would couple the application layer
    to a specific embedder implementation; ``RuntimeError`` is the
    wider type that buys us that decoupling.
    """


__all__ = ["Embedder", "EmbedderNotReady"]
