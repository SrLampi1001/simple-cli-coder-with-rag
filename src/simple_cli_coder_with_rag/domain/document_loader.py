"""Strategy interface for loading a document from disk (DO-13).

The document loader is the **first Strategy seam** in the document
ingestion pipeline (``OBJECTIVES.md`` — "the document loader
(Protocol dispatch)"). It reads a single file from disk and returns
the extracted text plus a :class:`DocumentMetadata` describing the
file. The chunker and embedder downstream only ever see the
``(text, metadata)`` tuple — they know nothing about the file system,
the format, or the loader implementation.

The shape is intentionally narrow:

* One method, :meth:`DocumentLoader.load`, returning
  ``tuple[str, DocumentMetadata]``. The string is the text content
  (UTF-8, with replacement glyphs for malformed bytes per the
  ``ExtensionDispatchLoader`` contract). The metadata carries
  everything the chat-time prompt needs to attribute the source.
* :class:`UnsupportedDocumentError` is the project-owned exception
  a loader raises when the file extension is not in the supported
  set. The message is friendly so ``LearnCommand`` can print it
  directly without a wrapper.

The only concrete implementation today is
:class:`~simple_cli_coder_with_rag.infrastructure.document_loaders.extension_dispatch.ExtensionDispatchLoader`,
which dispatches by extension to inline markdown / text / PDF
parsers. A future ``DocumentLoaderRegistry`` (out of scope v1, see
``agent-development/13-rag-over-documents-supabase/objective.md``
*Out of scope*) can be added behind the same Protocol.

Architectural note: this module imports from :mod:`domain` only. It
does not import from :mod:`infrastructure` or vendor SDKs. The
``infrastructure.document_loaders.forbidden_from_domain`` contract
in ``pyproject.toml`` enforces that the loader module itself is
never reached from the domain layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from simple_cli_coder_with_rag.domain.document_metadata import DocumentMetadata


class UnsupportedDocumentError(ValueError):
    """Raised when the file extension is not in the loader's supported set.

    A ``ValueError`` subclass so callers (``LearnCommand``) can catch
    the wider type without importing this module. The message lists
    the supported extensions so the user can fix the typo without
    reading the source.
    """


@runtime_checkable
class DocumentLoader(Protocol):
    """Strategy interface for loading a single document from disk.

    Implementations MUST:

    * Return ``(text, DocumentMetadata)`` where ``text`` is the
      extracted content (UTF-8, with replacement glyphs tolerated)
      and ``DocumentMetadata.source`` is the **absolute** path of
      the file (``Path.resolve()``).
    * Raise :class:`UnsupportedDocumentError` for unrecognised
      extensions, with a message naming the offending extension and
      the supported set.
    * Let ``FileNotFoundError`` propagate from the underlying open —
      the caller's contract is to translate it into a friendly
      REPL message.
    """

    def load(self, path: Path) -> tuple[str, DocumentMetadata]:
        """Read ``path`` and return ``(text, metadata)``.

        Parameters
        ----------
        path:
            Absolute or relative path. Implementations should
            :meth:`Path.resolve` before stashing the value on
            ``DocumentMetadata.source`` so the chunker / vector
            store see a stable dedup key.

        Raises
        ------
        UnsupportedDocumentError
            The file extension is not in the loader's supported set.
        FileNotFoundError
            The path does not exist. Propagates from the underlying
            ``open`` call.
        OSError
            The file is not readable for any other reason (permis-
            sions, transient IO error). Propagates from the
            underlying ``open`` call.
        """
        ...


__all__ = ["DocumentLoader", "UnsupportedDocumentError"]
