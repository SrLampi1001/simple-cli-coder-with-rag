"""Tests for ``ExtensionDispatchLoader`` (DO-13).

Pinned by ``agent-development/13-rag-over-documents-supabase/tests.md``.

Three format paths (``md`` / ``txt`` / ``pdf``) plus the
``UnsupportedDocumentError`` / ``FileNotFoundError`` / encoding /
zero-page edge cases. The PDF test uses the committed fixture at
``tests/fixtures/api-reference.pdf`` so the suite is hermetic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from simple_cli_coder_with_rag.domain.document_loader import (
    DocumentLoader,
    UnsupportedDocumentError,
)
from simple_cli_coder_with_rag.infrastructure.document_loaders import (
    ExtensionDispatchLoader,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_load_markdown_returns_text() -> None:
    """A ``.md`` file returns the text + ``DocumentMetadata(file_type='md')``."""
    path = _write(FIXTURES, "sample.md", "ignored")  # placeholder
    # Use the committed fixture instead so the test is hermetic.
    path = FIXTURES / "architecture.md"
    text, meta = ExtensionDispatchLoader().load(path)

    assert text == path.read_text(encoding="utf-8")
    assert meta.file_type == "md"
    assert meta.page_count is None
    assert meta.byte_size == path.stat().st_size
    assert meta.source == str(path.resolve())


def test_load_markdown_alias_markdown_extension() -> None:
    """``.markdown`` is the markdown alias — ``file_type='md'``."""
    # Build a transient file with the ``.markdown`` extension (the
    # committed fixture is ``.md``).
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".markdown", delete=False) as f:
        f.write(b"hello world\n")
        tmp = Path(f.name)
    try:
        text, meta = ExtensionDispatchLoader().load(tmp)
    finally:
        tmp.unlink(missing_ok=True)

    assert text == "hello world\n"
    assert meta.file_type == "md"


def test_load_text_returns_text() -> None:
    """A ``.txt`` file returns the text + ``DocumentMetadata(file_type='txt')``."""
    path = FIXTURES / "style-guide.txt"
    text, meta = ExtensionDispatchLoader().load(path)

    assert text == path.read_text(encoding="utf-8")
    assert meta.file_type == "txt"
    assert meta.page_count is None
    assert meta.byte_size == path.stat().st_size


def test_load_pdf_returns_text_with_page_count() -> None:
    """A one-page PDF returns the joined text + ``page_count=1``."""
    path = FIXTURES / "api-reference.pdf"
    text, meta = ExtensionDispatchLoader().load(path)

    assert meta.file_type == "pdf"
    assert meta.page_count == 1
    assert meta.byte_size == path.stat().st_size
    # The fixture has a couple of extractable lines — assert the
    # loader did not lose the text entirely.
    assert "Sample fixture" in text


def test_load_unsupported_extension(tmp_path: Path) -> None:
    """``.docx`` (or any other extension) raises ``UnsupportedDocumentError``."""
    path = _write(tmp_path, "foo.docx", "ignored")

    with pytest.raises(UnsupportedDocumentError, match=r"\.docx") as exc:
        ExtensionDispatchLoader().load(path)

    msg = str(exc.value)
    assert "pdf" in msg
    assert "md" in msg
    assert "txt" in msg


def test_load_missing_file_raises_filenotfound(tmp_path: Path) -> None:
    """A non-existent path raises ``FileNotFoundError`` (propagated from ``stat``)."""
    path = tmp_path / "nope.md"
    with pytest.raises(FileNotFoundError):
        ExtensionDispatchLoader().load(path)


def test_load_text_replaces_invalid_utf8(tmp_path: Path) -> None:
    """Invalid UTF-8 bytes in a text file become ``U+FFFD`` (replacement glyphs)."""
    path = tmp_path / "weird.md"
    path.write_bytes(b"hello \xff world")  # ``\xff`` is invalid in UTF-8

    text, meta = ExtensionDispatchLoader().load(path)

    # The text contains the replacement glyph for the invalid byte
    # and is otherwise preserved.
    assert "hello" in text
    assert "world" in text
    assert "\ufffd" in text
    assert meta.file_type == "md"


def test_load_pdf_zero_pages_returns_empty_text() -> None:
    """A PDF with no extractable text returns ``''`` and a ``page_count`` >= 0.

    Synthesised by writing a blank PDF via pypdf's writer. The
    loader returns an empty text body so the caller
    (``LearnCommand``) can surface a friendly "PDF has no
    extractable text." message. The ``page_count`` reflects the
    underlying PDF's page count (>= 0); a truly page-less PDF is
    hard to construct with pypdf's writer, so we assert the text
    is empty and ``page_count`` is a non-negative integer.
    """
    import tempfile

    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)  # no content stream

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        writer.write(f)
        tmp = Path(f.name)
    try:
        text, meta = ExtensionDispatchLoader().load(tmp)
    finally:
        tmp.unlink(missing_ok=True)

    assert text == ""
    assert meta.file_type == "pdf"
    assert meta.page_count is not None
    assert meta.page_count >= 0


def test_extension_dispatch_loader_satisfies_protocol() -> None:
    """``ExtensionDispatchLoader`` satisfies the ``DocumentLoader`` Protocol."""
    loader = ExtensionDispatchLoader()
    assert isinstance(loader, DocumentLoader)
