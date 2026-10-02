"""Alternative ``Chunker`` Strategy: one chunk per logical record.

Each chunk maps 1-to-1 onto a single record of the compacted session:

* One summary chunk (when ``summary`` is non-empty).
* One chunk per error (``"Error: {signature}\\n{message}"``).
* One chunk per decision (``"Decision: {summary}\\n{rationale}"``).

This chunker never splits. Chunk sizes can swing wildly — a session
with a long error message and a short decision will produce uneven
chunks. It is the alternative to ``FixedSizeChunker`` and is selected
by setting ``CHUNKER_STRATEGY=semantic``.

An empty ``CompactedSession`` returns ``[]`` (no empty chunk), matching
the contract that ``Chunker.chunk`` must not return ``[Chunk(text="")]``.

Architectural note: this module imports from :mod:`domain` only (no
infrastructure, no vendor SDKs). It is part of the application layer
and may be replaced at the composition root in ``cli.py``.
"""

from __future__ import annotations

from simple_cli_coder_with_rag.domain.chunk import Chunk
from simple_cli_coder_with_rag.domain.compacted import CompactedSession


class SemanticChunker:
    """One chunk per logical record of the compacted session.

    Parameters
    ----------
    max_chars:
        Reserved upper bound on the chunk size. **Not enforced** in v1
        because no chunker split ever occurs at the ``SemanticChunker``
        level — a single record is the largest possible chunk. The
        parameter exists so the two chunkers can be swapped without
        touching the composition root (the constructor signature is
        uniform).
    """

    def __init__(self, *, max_chars: int = 1024) -> None:
        # Stored for parity with ``FixedSizeChunker``; not used in v1.
        self._max_chars = max_chars

    @property
    def max_chars(self) -> int:
        """Return the configured (informational) chunk-size upper bound."""
        return self._max_chars

    def chunk(self, compacted: CompactedSession) -> list[Chunk]:
        """Return one chunk per non-empty record of ``compacted``.

        Empty records (``""``) are skipped so the chunker never returns
        a single empty chunk on an otherwise-empty session.
        """
        chunks: list[Chunk] = []
        index = 0

        if compacted.summary:
            chunks.append(
                Chunk(
                    text=compacted.summary,
                    metadata={"source": "summary", "index": index},
                    session_id=compacted.session_id,
                )
            )
            index += 1

        for err in compacted.errors:
            text = f"Error: {err.signature}\n{err.message}"
            if not text.strip():
                continue
            chunks.append(
                Chunk(
                    text=text,
                    metadata={"source": "error", "index": index},
                    session_id=compacted.session_id,
                )
            )
            index += 1

        for dec in compacted.decisions:
            text = f"Decision: {dec.summary}\n{dec.rationale}"
            if not text.strip():
                continue
            chunks.append(
                Chunk(
                    text=text,
                    metadata={"source": "decision", "index": index},
                    session_id=compacted.session_id,
                )
            )
            index += 1

        return chunks


__all__ = ["SemanticChunker"]
