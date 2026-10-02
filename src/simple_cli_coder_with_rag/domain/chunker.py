"""Strategy interface for the chunker.

The chunker is the **first Strategy seam** in the RAG pipeline
(``OBJECTIVES.md`` — "the chunker (fixed-size vs. semantic)").
Two implementations live in
:mod:`simple_cli_coder_with_rag.application.chunkers`:

* ``FixedSizeChunker`` — sliding ``max_chars`` windows with ``overlap``
  overlap. Default. Tunes cheaply; predictable chunk sizes; helps the
  embedder's max-token budget.
* ``SemanticChunker`` — one chunk per logical record (summary, error,
  decision). No splits. Preserves record boundaries but chunk sizes can
  swing wildly.

Adding a third implementation (e.g. sentence-aware splitter) is a matter
of writing the class and registering it in the composition root in
``cli.py``. The interface below is the seam.

Architectural note: this module imports from :mod:`domain` only. It
does not import from :mod:`infrastructure` or from vendor SDKs. The
implementation classes live in :mod:`application.chunkers`, also
restricted to the :mod:`domain` surface — ``import-linter`` enforces
this on the ``layered-architecture`` contract.
"""

from __future__ import annotations

from typing import Protocol

from simple_cli_coder_with_rag.domain.chunk import Chunk
from simple_cli_coder_with_rag.domain.compacted import CompactedSession


class Chunker(Protocol):
    """Strategy interface for turning a ``CompactedSession`` into ``Chunk`` records."""

    def chunk(self, compacted: CompactedSession) -> list[Chunk]:
        """Split ``compacted`` into a list of ``Chunk`` records.

        An empty ``CompactedSession`` (no summary, no errors, no
        decisions) MUST return ``[]`` — not a single empty chunk that
        would later be embedded as a zero vector.
        """
        ...


__all__ = ["Chunker"]
