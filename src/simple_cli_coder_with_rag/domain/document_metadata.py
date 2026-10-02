"""Pydantic model carrying the metadata of a loaded document (DO-13).

``DocumentMetadata`` is the structured description the
:class:`~simple_cli_coder_with_rag.domain.document_loader.DocumentLoader`
Protocol returns alongside the raw text. It carries the four fields the
rest of the ingestion pipeline needs:

* ``source`` — the absolute, resolved file path. Used as the
  ``Chunk.source`` value and as the dedup key the vector store indexes
  on. ``Path.resolve()`` is the right thing at the loader site; the
  metadata model stores the string the caller passes.
* ``file_type`` — one of the three supported extensions
  (``"pdf"`` / ``"md"`` / ``"txt"``). The literal is closed so a typo
  in a future ``ExtensionDispatchLoader`` branch is caught at
  construction time, not at retrieval time.
* ``page_count`` — only meaningful for PDFs; ``None`` for the text
  formats. The chat-time prompt uses it as a one-line context hint.
* ``byte_size`` — the file size in bytes. The chat-time prompt uses
  it to format the user-facing message ("learned N chunks from X
  (md, 1234 bytes)").

Architectural note: this module imports from :mod:`pydantic` only. It
does not import from :mod:`infrastructure` or vendor SDKs.
``import-linter`` enforces this on the ``layered-architecture``
contract, and the
``infrastructure.document_loaders.forbidden_from_domain`` contract
keeps the loader module itself out of the domain layer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class DocumentMetadata(BaseModel):
    """Structured metadata the loader returns with each document's text.

    See the module docstring for the field-level contract. The
    ``file_type`` literal is closed at the model level so unknown
    extensions are rejected at validation time, not at retrieval time.
    """

    source: str
    file_type: Literal["pdf", "md", "txt"]
    page_count: int | None = None
    byte_size: int


__all__ = ["DocumentMetadata"]
