"""Tests for the ``DocumentMetadata`` Pydantic model (DO-13).

Pinned by ``agent-development/13-rag-over-documents-supabase/tests.md``.

``DocumentMetadata`` is the structured description the
:class:`DocumentLoader` returns alongside the raw text. The model
rejects unknown ``file_type`` values and round-trips through
``model_dump_json`` / ``model_validate``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from simple_cli_coder_with_rag.domain.document_metadata import DocumentMetadata


def test_document_metadata_required_source() -> None:
    """The minimum required fields (``source``, ``file_type``, ``byte_size``) construct cleanly."""
    meta = DocumentMetadata(source="foo.md", file_type="md", byte_size=10)

    assert meta.source == "foo.md"
    assert meta.file_type == "md"
    assert meta.byte_size == 10
    assert meta.page_count is None  # default


def test_document_metadata_pdf_includes_page_count() -> None:
    """PDF metadata carries the page count."""
    meta = DocumentMetadata(
        source="x.pdf",
        file_type="pdf",
        page_count=3,
        byte_size=1024,
    )

    assert meta.page_count == 3


def test_document_metadata_rejects_unknown_file_type() -> None:
    """``file_type='docx'`` is rejected by the ``Literal`` constraint."""
    with pytest.raises(ValidationError):
        DocumentMetadata(source="x.docx", file_type="docx", byte_size=10)  # type: ignore[arg-type]


def test_document_metadata_default_page_count_is_none() -> None:
    """Omitting ``page_count`` gives ``None`` (the documented default)."""
    meta = DocumentMetadata(source="x.md", file_type="md", byte_size=1)

    assert meta.page_count is None


def test_document_metadata_round_trip_json() -> None:
    """``model_dump_json`` round-trips back into an equal ``DocumentMetadata``."""
    meta = DocumentMetadata(source="/abs/foo.md", file_type="md", page_count=None, byte_size=123)

    rebuilt = DocumentMetadata.model_validate_json(meta.model_dump_json())

    assert rebuilt == meta
