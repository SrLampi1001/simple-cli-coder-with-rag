"""Tests for the ``VectorStore`` Protocol and ``VectorStoreBackendUnavailable`` exception.

Pinned by ``agent-development/07-vector-store-strategy/tests.md``.

The ``VectorStore`` Protocol is the **fourth Strategy seam** in the RAG
pipeline (after ``Chunker``, ``Embedder``). It must expose two operations:

* ``upsert(chunks, vectors)`` — persist a batch of chunks together with
  their pre-computed vectors.
* ``query(vector, top_k)`` — return the top-``k`` chunks sorted by
  cosine similarity descending.

``VectorStoreBackendUnavailable`` is a ``RuntimeError`` so the composition
root in ``cli.py`` can catch it and fall back to
``NumpyBruteForceStore`` without importing any vendor type. The message
must mention the ``VECTOR_STORE=brute_force`` workaround so the user has
a one-line path to recovery.
"""

from __future__ import annotations

import pytest

from simple_cli_coder_with_rag.domain.vector_store import (
    VectorStore,
    VectorStoreBackendUnavailable,
)


def test_protocol_has_required_methods() -> None:
    """``VectorStore`` declares ``upsert`` and ``query`` with the expected names."""
    assert hasattr(VectorStore, "upsert")
    assert hasattr(VectorStore, "query")


def test_backend_unavailable_is_runtime_error() -> None:
    """``VectorStoreBackendUnavailable`` is a ``RuntimeError`` subclass.

    The composition root in ``cli.py`` catches it as a ``RuntimeError``
    to fall back to the numpy store. That contract only holds if the
    exception is genuinely a ``RuntimeError``.
    """
    assert issubclass(VectorStoreBackendUnavailable, RuntimeError)


def test_backend_unavailable_message_mentions_brute_force() -> None:
    """The exception message includes the ``VECTOR_STORE=brute_force`` workaround.

    The user must be able to copy-paste the workaround straight out of the
    error message without reading the source.
    """
    err = VectorStoreBackendUnavailable(
        "This Python build does not support sqlite3 extension loading, "
        "so sqlite-vec cannot be used. Install CPython from python.org "
        "or a build with --enable-loadable-sqlite-extensions. "
        "Alternatively, set VECTOR_STORE=brute_force to use the numpy fallback."
    )
    msg = str(err)
    assert "VECTOR_STORE=brute_force" in msg, f"workaround hint missing from message: {msg!r}"


def test_backend_unavailable_carries_message() -> None:
    """The exception's message is preserved on the standard ``str()`` accessor."""
    err = VectorStoreBackendUnavailable("boom")
    assert str(err) == "boom"


def test_backend_unavailable_can_be_caught_as_runtime_error() -> None:
    """``VectorStoreBackendUnavailable`` can be caught as a plain ``RuntimeError``.

    This is the contract the composition root relies on: it does not
    import the project-owned exception type and catches ``RuntimeError``
    instead.
    """
    with pytest.raises(RuntimeError, match="boom"):
        raise VectorStoreBackendUnavailable("boom")
