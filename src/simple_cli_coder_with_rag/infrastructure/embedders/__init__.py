"""Strategy implementations of the ``Embedder`` Protocol.

The default for v1 is ``FastembedEmbedder`` — a local ONNX-runtime
embedder based on ``fastembed`` and the ``BAAI/bge-small-en-v1.5``
model. A second implementation (e.g. an HTTP remote embedder backed
by ``httpx``) can be added later behind the same ``Embedder``
Protocol; the composition root would simply register it instead.

Architectural note: ``fastembed`` may only be imported from this
package. ``import-linter`` enforces this with a ``forbidden_imports``
contract in ``pyproject.toml``; the
``tests/infrastructure/embedders/test_fastembed_embedder.py`` smoke
test is a redundant safeguard against contract regressions.
"""

from simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder import (
    FastembedEmbedder,
)

__all__ = ["FastembedEmbedder"]
