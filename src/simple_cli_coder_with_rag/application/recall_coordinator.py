"""Recall coordinator — application-layer glue between the REPL and the retriever.

:class:`RecallCoordinator` is the **single seam** the REPL talks to for
recall (DO-09). It composes three concerns:

1. The :class:`~simple_cli_coder_with_rag.application.trivial_gate.TrivialGate`
   short-circuit (the OBJECTIVES latency tip: cheap prompts skip
   retrieval).
2. A delegated :class:`~simple_cli_coder_with_rag.domain.retriever.Retriever`
   — already wrapped in
   :class:`~simple_cli_coder_with_rag.infrastructure.retrievers.timeout_retriever.TimeoutRetriever`
   by the composition root in ``cli.py`` (DO-08). The coordinator does
   **not** own an executor and does **not** wrap again (double-wrapping
   would nest executors and defeat the shared ``RetrievalExecutor``).
3. A similarity threshold that drops weakly-related chunks before they
   reach the LLM context.

Failure handling — every observable failure degrades silently to ``[]``
and logs at ``DEBUG``:

* The trivial gate fires → ``[]``. (``len(prompt) <= max_chars and
  words <= max_words``; the gate runs first, so a trivial prompt never
  reaches the retriever.)
* The retriever raises ``EmbedderNotReady`` (a ``RuntimeError``) — the
  embedder is still loading. Catch and return ``[]``.
* The retriever raises a generic ``RuntimeError`` — any other transient
  vendor/transport failure. Catch and return ``[]``. We catch the wider
  type (not :class:`EmbedderNotReady` directly) so this module stays
  decoupled from the embedder module — same trick the rest of the
  codebase uses.
* The retriever raises ``TimeoutError`` — defensive only; a real
  ``TimeoutRetriever`` returns ``[]`` instead of raising. We catch it so
  a custom retriever that propagates ``TimeoutError`` does not bring
  down the chat path.
* All other exceptions propagate — they are bugs, not transient
  failures, and the REPL benefits from the stack trace.

Architectural note: this module imports from :mod:`domain` and from
sibling :mod:`simple_cli_coder_with_rag.application` modules only. It
does **not** import from :mod:`infrastructure` (no ``Settings``, no
executor). The composition root in ``cli.py`` wires the
``TimeoutRetriever`` outside and injects it here.
"""

from __future__ import annotations

from loguru import logger

from simple_cli_coder_with_rag.application.trivial_gate import TrivialGate
from simple_cli_coder_with_rag.domain.retriever import Retriever


class RecallCoordinator:
    """Apply the trivial gate, delegate to the retriever, and threshold the hits."""

    def __init__(
        self,
        retriever: Retriever,
        gate: TrivialGate,
        *,
        top_k: int,
        similarity_threshold: float,
    ) -> None:
        if top_k <= 0:
            raise ValueError(f"top_k must be > 0, got {top_k}")
        if not 0.0 <= similarity_threshold <= 1.0:
            raise ValueError(
                f"similarity_threshold must be in [0.0, 1.0], got {similarity_threshold}"
            )
        self._retriever = retriever
        self._gate = gate
        self._top_k = top_k
        self._similarity_threshold = similarity_threshold

    @property
    def top_k(self) -> int:
        """Return the configured ``top_k`` — used as the default for tests / callers."""
        return self._top_k

    @property
    def similarity_threshold(self) -> float:
        """Return the configured similarity threshold."""
        return self._similarity_threshold

    def recall(self, prompt: str, *, top_k: int | None = None) -> list[str]:
        """Return up to ``top_k`` (or :attr:`top_k`) chunk texts relevant to ``prompt``.

        Behaviour:

        * Trivial gate fires → return ``[]`` (no retriever call).
        * Retriever raises ``RuntimeError`` (e.g. ``EmbedderNotReady``)
          or ``TimeoutError`` → return ``[]`` and log at ``DEBUG``.
        * Otherwise → filter results by ``similarity >=
          self._similarity_threshold`` and return ``[r.chunk.text for r
          in filtered]``.

        ``top_k`` defaults to :attr:`top_k` — the constructor value.
        Tests pass an override to exercise the ``top_k`` plumbing
        without rebuilding the coordinator.
        """
        if self._gate.is_trivial(prompt):
            logger.debug("trivial prompt, skipping recall (prompt length={})", len(prompt))
            return []

        effective_top_k = top_k if top_k is not None else self._top_k
        try:
            results = self._retriever.retrieve(prompt, top_k=effective_top_k)
        except RuntimeError as exc:
            # ``EmbedderNotReady`` is a ``RuntimeError``; we catch the wider
            # type so this module stays decoupled from the embedder module.
            # Same trick the rest of the codebase uses for vendor failures.
            logger.debug("recall aborted: retriever raised RuntimeError: {}", exc)
            return []
        except TimeoutError as exc:
            # Defensive: ``TimeoutRetriever`` returns ``[]`` rather than
            # raising, but a custom retriever could propagate ``TimeoutError``.
            logger.debug("recall aborted: retriever raised TimeoutError: {}", exc)
            return []

        return [r.chunk.text for r in results if r.similarity >= self._similarity_threshold]


__all__ = ["RecallCoordinator"]
