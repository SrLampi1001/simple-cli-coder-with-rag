"""Strategy implementations of the ``Chunker`` Protocol.

Two concrete chunkers ship with the project:

* ``FixedSizeChunker`` — sliding ``max_chars`` windows with ``overlap``
  overlap. Default. Produces predictable chunk sizes; helps the
  embedder's max-token budget.
* ``SemanticChunker`` — one chunk per logical record (summary, error,
  decision). No splits. Preserves record boundaries.

The composition root in ``cli.py`` picks one of these based on
``Settings.chunker_strategy``. New implementations are a matter of
defining a class with a ``chunk(compacted) -> list[Chunk]`` method and
registering it in ``cli.py``.

Architectural note: this module imports from :mod:`domain` only. The
implementation classes live in :mod:`application.chunkers` so the
layered-architecture contract (``pyproject.toml`` ``[tool.importlinter]``)
stays clean: ``application`` may depend on ``domain``, never the reverse.
"""

from simple_cli_coder_with_rag.application.chunkers.fixed_size import FixedSizeChunker
from simple_cli_coder_with_rag.application.chunkers.semantic import SemanticChunker

__all__ = ["FixedSizeChunker", "SemanticChunker"]
