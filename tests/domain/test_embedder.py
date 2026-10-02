"""Tests for the ``Embedder`` Protocol and ``EmbedderNotReady`` exception.

Pinned by ``agent-development/06-embedder-strategy/tests.md``.

The ``Embedder`` Protocol is the third Strategy seam in the RAG pipeline
(after ``Chunker`` and before ``VectorStore``). It must expose two
embedding methods (``embed_query`` / ``embed_passages``) plus the
warm-up surface (``warmup`` / ``is_ready``) the composition root needs
to start the model on a daemon thread without blocking the REPL.

``EmbedderNotReady`` is a ``RuntimeError`` so the surrounding service
(:class:`~simple_cli_coder_with_rag.application.knowledge_service.KnowledgeService`
via ``recall`` in DO-09) can let ``RuntimeError`` short-circuit to
"no memories" without importing a third-party type.
"""

from __future__ import annotations

import pytest

from simple_cli_coder_with_rag.domain.embedder import Embedder, EmbedderNotReady


def test_protocol_has_required_methods() -> None:
    """``Embedder`` declares all four required methods with the expected names."""
    assert hasattr(Embedder, "embed_query")
    assert hasattr(Embedder, "embed_passages")
    assert hasattr(Embedder, "warmup")
    assert hasattr(Embedder, "is_ready")


def test_embedder_not_ready_is_runtime_error() -> None:
    """``EmbedderNotReady`` is a ``RuntimeError`` subclass.

    The retriever in DO-08 catches ``RuntimeError`` (not the project-owned
    exception type) to stay decoupled from this domain module; that contract
    only holds if the exception is genuinely a ``RuntimeError``.
    """
    assert issubclass(EmbedderNotReady, RuntimeError)


def test_embedder_not_ready_carries_message() -> None:
    """The exception's message is preserved on the standard ``str()`` accessor."""
    err = EmbedderNotReady("still loading")
    assert str(err) == "still loading"


def test_embedder_not_ready_can_be_caught_as_runtime_error() -> None:
    """``EmbedderNotReady`` can be caught as a plain ``RuntimeError``."""
    with pytest.raises(RuntimeError, match="loading"):
        raise EmbedderNotReady("still loading")
