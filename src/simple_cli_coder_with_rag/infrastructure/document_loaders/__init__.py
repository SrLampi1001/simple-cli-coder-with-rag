"""Strategy implementations of the ``DocumentLoader`` Protocol.

The default for v1 is :class:`ExtensionDispatchLoader` — a single class
with three private methods (``_load_markdown``, ``_load_text``,
``_load_pdf``) that dispatches by file extension. A future
``DocumentLoaderRegistry`` (out of scope v1, see the DO-13 *Out of
scope* section) can be added behind the same Protocol.

Architectural note: this package is the only place in the codebase
that may import :mod:`pypdf` (the PDF parser). ``import-linter``
enforces this with a ``forbidden_imports`` contract in
``pyproject.toml`` mirroring the existing ``sqlite-vec`` /
``fastembed`` rules. The
``tests/infrastructure/document_loaders/test_extension_dispatch.py``
test suite is a redundant safeguard against contract regressions.
"""

from simple_cli_coder_with_rag.infrastructure.document_loaders.extension_dispatch import (
    ExtensionDispatchLoader,
)

__all__ = ["ExtensionDispatchLoader"]
