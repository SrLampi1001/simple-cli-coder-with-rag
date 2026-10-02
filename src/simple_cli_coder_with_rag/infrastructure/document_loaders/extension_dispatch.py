"""``ExtensionDispatchLoader`` — the default ``DocumentLoader`` for DO-13.

Dispatches on file extension:

* ``.md`` / ``.markdown`` → :meth:`_load_markdown`
* ``.txt``                → :meth:`_load_text`
* ``.pdf``                → :meth:`_load_pdf`

Markdown and text are read verbatim as UTF-8 with ``errors="replace"``
so a malformed byte becomes a single ``U+FFFD`` replacement glyph
and the pipeline keeps moving. PDF uses :class:`pypdf.PdfReader` and
joins per-page text with a form-feed (``\f``) separator so the
chunker can later break on page boundaries if it wants (the v1
``FixedSizeChunker`` does not — it slides over the joined text
indiscriminately, the same way it does for the session path).

The byte_size field is taken from ``Path.stat().st_size`` for all
three formats — it is the on-disk size, not the decoded character
count, so the chat-time prompt can report the file size in the
human-friendly "learned N chunks from X (md, 1234 bytes)" message.

Architectural note: this module is the only place the codebase may
import :mod:`pypdf`. ``import-linter`` enforces this with a
``forbidden_imports`` contract (``pypdf-only-in-document-loaders``)
in ``pyproject.toml``; the
``tests/infrastructure/document_loaders/test_extension_dispatch.py``
test suite is a redundant safeguard.
"""

from __future__ import annotations

from pathlib import Path

from simple_cli_coder_with_rag.domain.document_loader import (
    UnsupportedDocumentError,
)
from simple_cli_coder_with_rag.domain.document_metadata import DocumentMetadata

# Supported extension set. The list is the source of truth for the
# friendly error message — keeping it as a module-level constant
# makes the "Supported: pdf, md, markdown, txt." phrase a one-line
# edit when a new format lands.
_SUPPORTED_EXTENSIONS: tuple[str, ...] = (".pdf", ".md", ".markdown", ".txt")

# Form-feed separator joining per-page PDF text. The chunker can
# break on it later; the v1 ``FixedSizeChunker`` does not, but the
# document is at least reversible for the chat-time debug path.
_PDF_PAGE_SEPARATOR = "\f"


class ExtensionDispatchLoader:
    """Dispatch to one of three inline loaders by file extension.

    The dispatch lives in :meth:`load`; each format's read logic is
    a private method. YAGNI on a loader Registry for v1 — adding a
    fourth format (DOCX, HTML, …) is a future DO. The Protocol is
    the seam, so the swap is a one-line change at the composition
    root in :mod:`simple_cli_coder_with_rag.cli`.
    """

    def load(self, path: Path) -> tuple[str, DocumentMetadata]:
        """Read ``path`` and return ``(text, metadata)``.

        The path is :meth:`Path.resolve`'d before the metadata is
        built so the chunker / vector store see a stable absolute
        dedup key (``source``). ``byte_size`` comes from
        :meth:`Path.stat` on the original path — the on-disk size
        matches the user's expectation.
        """
        # ``stat`` runs first so a missing file raises
        # ``FileNotFoundError`` with the right message regardless of
        # the extension. ``stat`` is also what populates ``byte_size``,
        # so doing it once at the top is the right place.
        byte_size = path.stat().st_size
        resolved = path.resolve()
        suffix = resolved.suffix.lower()

        if suffix == ".pdf":
            text, page_count = self._load_pdf(resolved)
            file_type = "pdf"
        elif suffix in (".md", ".markdown"):
            text = self._load_text(resolved)
            page_count = None
            file_type = "md"
        elif suffix == ".txt":
            text = self._load_text(resolved)
            page_count = None
            file_type = "txt"
        else:
            raise UnsupportedDocumentError(
                f"unsupported file type: '{suffix}'. Supported: pdf, md, markdown, txt."
            )

        metadata = DocumentMetadata(
            source=str(resolved),
            file_type=file_type,  # type: ignore[arg-type]
            page_count=page_count,
            byte_size=byte_size,
        )
        return text, metadata

    @staticmethod
    def _load_text(path: Path) -> str:
        """Read ``path`` as UTF-8 with replacement glyphs for malformed bytes.

        ``errors="replace"`` is the contract — a user with a
        half-decoded file still gets a successful ``/learn`` rather
        than a crash. The ``U+FFFD`` glyphs surface in the chunk
        text and the LLM can usually ignore them.
        """
        return path.read_text(encoding="utf-8", errors="replace")

    @staticmethod
    def _load_pdf(path: Path) -> tuple[str, int]:
        """Read ``path`` as PDF and return ``(joined_text, page_count)``.

        Per-page text is extracted with :meth:`Page.extract_text`
        and joined with a form-feed (``\f``) separator. A PDF with
        zero extractable pages returns ``("", 0)`` — the
        ``LearnCommand`` translates this into a friendly
        "PDF has no extractable text." message.

        ``pypdf`` is imported **inside** the method (not at module
        scope) so the rest of the loader module — and the rest of
        the project — does not pay the import cost on every cold
        start. The import-linter ``pypdf-only-in-document-loaders``
        contract catches accidental imports from upper layers.
        """
        import pypdf  # local import — see module docstring

        reader = pypdf.PdfReader(str(path))
        page_texts = [page.extract_text() or "" for page in reader.pages]
        return _PDF_PAGE_SEPARATOR.join(page_texts), len(reader.pages)


__all__ = ["ExtensionDispatchLoader"]
