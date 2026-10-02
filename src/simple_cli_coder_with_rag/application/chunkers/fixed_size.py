"""Default ``Chunker`` Strategy: sliding ``max_chars`` windows with ``overlap`` overlap.

Algorithm:

1. Build a list of ``(source, text)`` records by iterating
   ``compacted.summary`` (one record), each error
   (``"Error: {signature}\\n{message}"``), and each decision
   (``"Decision: {summary}\\n{rationale}"``).
2. For each record, slide a ``max_chars`` window over its text with
   ``overlap`` characters of overlap. When the natural end of a
   window falls inside a word, the implementation backs off to the
   nearest preceding space so chunks end on word boundaries; if no
   space is found, it hard-cuts.
3. Chunks from all records are concatenated in record order.
4. Each chunk's ``metadata["source"]`` is the source of the record
   the chunk came from, and ``metadata["index"]`` counts from zero in
   the global chunk order.

This "slide per record" approach keeps source attribution deterministic
— a chunk from a summary cannot be mis-attributed to an error that
happens to fall in the same window — at the cost of slightly different
boundary behaviour than a single global sliding window. The trade-off
is documented in the module docstring and the chunker is exposed
behind the same ``Chunker`` Protocol as the alternative
:class:`SemanticChunker`, so swapping is a one-line change at the
composition root.

When the compacted session is empty (no summary, no errors, no
decisions) the chunker returns ``[]`` rather than a single empty chunk,
so the embedder never sees a zero-length input.

Architectural note: this module imports from :mod:`domain` only (no
infrastructure, no vendor SDKs). It is part of the application layer
and may be replaced at the composition root in ``cli.py``.
"""

from __future__ import annotations

from simple_cli_coder_with_rag.domain.chunk import Chunk
from simple_cli_coder_with_rag.domain.compacted import CompactedSession

# Type alias used internally for the (source, text) record tuple. The
# source string mirrors ``metadata["source"]`` exactly so the chunker
# cannot drift away from the documented values.
_Source = str

# Documented source values. Mirrored in the SemanticChunker below.
_SOURCE_SUMMARY = "summary"
_SOURCE_ERROR = "error"
_SOURCE_DECISION = "decision"

# Window-minimum guard. If backing off to the last space would leave a
# window shorter than this, we keep the natural end instead (avoids
# degenerate single-character windows on the first iteration when
# ``start == 0``).
_MIN_WINDOW_CHARS = 16


class FixedSizeChunker:
    """Slide a ``max_chars`` window over each compacted-session record.

    Parameters
    ----------
    max_chars:
        Width of the sliding window. Must be positive.
    overlap:
        Number of characters of overlap between consecutive windows.
        Must satisfy ``0 <= overlap < max_chars`` — the off-by-one case
        (``overlap == max_chars``) is rejected because it would produce
        a window that never advances, and a negative overlap is rejected
        because it has no useful semantics for this chunker.
    """

    def __init__(self, *, max_chars: int = 512, overlap: int = 64) -> None:
        if max_chars <= 0:
            raise ValueError(f"max_chars must be > 0, got {max_chars}")
        if overlap < 0 or overlap >= max_chars:
            raise ValueError(
                f"overlap must satisfy 0 <= overlap < max_chars, "
                f"got overlap={overlap} with max_chars={max_chars}"
            )
        self._max_chars = max_chars
        self._overlap = overlap

    @property
    def max_chars(self) -> int:
        """Return the configured window width."""
        return self._max_chars

    @property
    def overlap(self) -> int:
        """Return the configured overlap width."""
        return self._overlap

    def chunk(self, compacted: CompactedSession) -> list[Chunk]:
        """Return the sliding-window chunks for ``compacted``.

        An empty ``CompactedSession`` yields ``[]`` (no empty chunk).
        Otherwise each record is windowed independently; chunks from
        all records are concatenated in record order. Each chunk
        carries ``metadata["source"]`` of its record and
        ``metadata["index"]`` counting from zero in chunk order.
        """
        records = _records_for(compacted)
        if not records:
            return []

        chunks: list[Chunk] = []
        for source, text in records:
            for window_text in _slide(text, self._max_chars, self._overlap):
                chunks.append(
                    Chunk(
                        text=window_text,
                        metadata={
                            "source": source,
                            "index": len(chunks),
                        },
                        session_id=compacted.session_id,
                    )
                )
        return chunks


def _records_for(compacted: CompactedSession) -> list[tuple[_Source, str]]:
    """Build the ``(source, text)`` record list for ``compacted``.

    Records are returned in the order summary → errors → decisions so
    the chunked output mirrors the JSON schema's logical order.
    """
    records: list[tuple[_Source, str]] = []
    if compacted.summary:
        records.append((_SOURCE_SUMMARY, compacted.summary))
    for err in compacted.errors:
        records.append((_SOURCE_ERROR, f"Error: {err.signature}\n{err.message}"))
    for dec in compacted.decisions:
        records.append((_SOURCE_DECISION, f"Decision: {dec.summary}\n{dec.rationale}"))
    return records


def _slide(text: str, max_chars: int, overlap: int) -> list[str]:
    """Slide a ``max_chars`` window over ``text`` and return the window contents.

    Each window snaps to the nearest preceding space when doing so
    would not leave a degenerate window. The final window reaches the
    end of ``text`` even if its length is less than ``max_chars``.
    """
    step = max_chars - overlap
    windows: list[str] = []
    start = 0
    text_len = len(text)
    while start < text_len:
        natural_end = min(start + max_chars, text_len)
        end = _snap_to_space(text, start, natural_end)
        # Trim trailing partial UTF-8 bytes (window may chop a
        # multi-byte char). ``encode/decode`` with ``errors="ignore"``
        # drops the partial bytes.
        window_text = (
            text[start:end].encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")
        )
        windows.append(window_text)
        if end == text_len:
            break
        start += step
    return windows


def _snap_to_space(text: str, start: int, natural_end: int) -> int:
    """Return ``natural_end`` snapped back to the nearest preceding space.

    If backing off would leave a window shorter than
    :data:`_MIN_WINDOW_CHARS`, return ``natural_end`` unchanged. If no
    space exists in the window, also return ``natural_end`` (hard-cut).
    ``natural_end == len(text)`` is returned verbatim because the
    window already covers the rest of the document.
    """
    if natural_end >= len(text):
        return natural_end
    window_len = natural_end - start
    if window_len < _MIN_WINDOW_CHARS:
        return natural_end
    # ``rfind`` on the slice ``text[start:natural_end]`` finds the last
    # space before the natural end.
    search_slice = text[start:natural_end]
    last_space_rel = search_slice.rfind(" ")
    if last_space_rel == -1:
        return natural_end
    return start + last_space_rel


__all__ = ["FixedSizeChunker"]
