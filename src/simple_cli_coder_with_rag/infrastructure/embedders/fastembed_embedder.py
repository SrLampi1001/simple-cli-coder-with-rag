"""``FastembedEmbedder`` — local ONNX-runtime implementation of ``Embedder``.

This module is the **only** place in the codebase that imports
``fastembed``. The ``import-linter`` ``forbidden_imports`` contract in
``pyproject.toml`` enforces this; the ``test_does_not_pollute_other_layers``
smoke test is a redundant safeguard.

Design notes (``docs/development-tools.md`` §5):

* Default model: ``BAAI/bge-small-en-v1.5`` (384-dim, BGE family).
* Cache dir: ``Path(platformdirs.user_cache_dir(...)) / "models"`` so
  the ~130 MB download survives reboots and reinstalls.
* ``local_files_only=True`` so subsequent runs do not hit HuggingFace
  when the model is already cached (``fastembed`` would otherwise ping
  HF on every init).
* Two embed methods (``embed_query`` / ``embed_passages``) so BGE's
  instruction-prefix-for-queries convention is honoured.

Warm-up:

* Constructor returns immediately.
* A ``threading.Thread(daemon=True, target=self._load)`` runs in the
  background, builds ``TextEmbedding(...)``, then sets ``_ready = True``
  and signals ``_ready_event``.
* Downstream code (``KnowledgeService.recall`` in DO-09, the retriever
  in DO-08) gates on :meth:`is_ready` and degrades gracefully when the
  model is still loading. ``embed_query`` / ``embed_passages`` raise
  :class:`~simple_cli_coder_with_rag.domain.embedder.EmbedderNotReady`
  in the meantime.

First-run UX:

* On a cold cache, ``_load`` writes
  ``"downloading embedding model (one time only)…"`` to **stderr**.
  ``prompt_toolkit`` is not yet on screen at that point, so stderr is
  safe. The message is gated by a module-level ``_announced`` flag
  so subsequent embedders in the same process never repeat it.
* If the model is still loading **after** the REPL is up, the message
  would corrupt the prompt. The composition root flips the
  module-level ``_REPL_ACTIVE`` flag to ``True`` immediately before
  ``repl.run()``; with the flag set, the cold-cache message goes
  through ``loguru`` to the log file instead of stderr. The embedder
  does **not** import anything from the presentation layer — the flag
  is a one-line module attribute the composition root sets directly.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any

from fastembed import TextEmbedding
from loguru import logger

from simple_cli_coder_with_rag.domain.embedder import EmbedderNotReady

# Module-level flags. Both are read/written from outside (the
# composition root flips ``_REPL_ACTIVE`` before ``repl.run()``). Tests
# reset ``_announced`` so the cold-cache message is predictable per-test.
_announced: bool = False
_REPL_ACTIVE: bool = False

# The HuggingFace-hub snapshot directory naming convention is
# ``models--<org>--<model>``. fastembed uses ``huggingface_hub.snapshot_download``
# under the hood, which creates that directory.
_HF_SNAPSHOT_PREFIX = "models--"


def _is_cache_warm(cache_dir: Path, model_name: str) -> bool:
    """Return ``True`` if the model's snapshot directory is already on disk.

    The check is intentionally conservative: we only look for the
    directory that ``huggingface-hub`` would have created. A directory
    without any model files would still be detected as warm — that is
    the right behaviour for ``fastembed`` too, because the user can
    always pass ``local_files_only=False`` to refresh.
    """
    snapshot = cache_dir / f"{_HF_SNAPSHOT_PREFIX}{model_name.replace('/', '--')}"
    return snapshot.exists()


class FastembedEmbedder:
    """Local ``fastembed``-backed implementation of ``Embedder``.

    Construction is cheap (microseconds). The first embed call blocks
    on the model download / load if the warm-up thread has not yet
    finished. ``is_ready()`` and ``warmup()`` are the contract the
    caller uses to coordinate with that thread.
    """

    def __init__(
        self,
        *,
        model_name: str = "BAAI/bge-small-en-v1.5",
        cache_dir: Path | None = None,
        local_files_only: bool = True,
    ) -> None:
        """Schedule background load; return immediately.

        ``cache_dir`` defaults to ``None`` so the composition root is
        the single source of truth for the platform-dependent path. The
        ``local_files_only=True`` default matches ``dev-tools.md`` §5
        (no HuggingFace network check when the model is cached).
        """
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._local_files_only = local_files_only

        self._model: Any = None
        self._ready: bool = False
        self._ready_event = threading.Event()

        # Announce the cold-cache download once per process. The check
        # happens in the constructor (not in ``_load``) so the message
        # is gated even when the daemon thread takes a while to start.
        global _announced
        if (
            not _announced
            and self._cache_dir is not None
            and not _is_cache_warm(self._cache_dir, model_name)
        ):
            _announced = True
            if _REPL_ACTIVE:
                logger.info("downloading embedding model (one time only)…")
            else:
                # The one allowed stderr write before ``prompt_toolkit``
                # takes over. See module docstring for why this is safe.
                print("downloading embedding model (one time only)…", file=sys.stderr)

        # Daemon thread so a slow first-time download never delays
        # process exit. The composition root does **not** call
        # ``warmup()``; this thread drives the model load.
        threading.Thread(
            target=self._load,
            name=f"FastembedEmbedder.load-{model_name}",
            daemon=True,
        ).start()

    def _load(self) -> None:
        """Build the ``TextEmbedding`` instance and flip the ready flag.

        Runs on the daemon thread scheduled in ``__init__``. ``local_files_only``
        is forwarded to ``fastembed`` so cached models do not require a
        HuggingFace round-trip. Failures are logged but otherwise swallowed:
        the embedder surface (``embed_query`` / ``embed_passages``) keeps
        raising :class:`EmbedderNotReady` until the daemon thread succeeds,
        so a permanent failure surfaces to the REPL as "no memories"
        rather than a hard crash.
        """
        kwargs: dict[str, Any] = {
            "model_name": self._model_name,
            "local_files_only": self._local_files_only,
        }
        if self._cache_dir is not None:
            kwargs["cache_dir"] = str(self._cache_dir)

        try:
            self._model = TextEmbedding(**kwargs)
        except Exception as exc:
            logger.error("Failed to load embedding model: {}", exc)
            return

        self._ready = True
        self._ready_event.set()

    def is_ready(self) -> bool:
        """Return ``True`` if the model has finished loading."""
        return self._ready

    def warmup(self, *, timeout: float | None = None) -> None:
        """Block until the model is ready, or ``timeout`` seconds elapse.

        ``timeout=None`` waits indefinitely; ``timeout=N`` raises
        :class:`TimeoutError` if the model is still not ready after
        ``N`` seconds. The composition root does not call this; tests do.
        """
        if not self._ready_event.wait(timeout=timeout):
            raise TimeoutError(
                f"FastembedEmbedder not ready after {timeout}s (model={self._model_name!r})"
            )

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query and return a 384-dim ``list[float]``.

        BGE models retrieve better when queries carry an instruction
        prefix; ``fastembed``'s ``query_embed`` bakes that in.
        """
        if not self._ready:
            raise EmbedderNotReady(
                "FastembedEmbedder is still loading; call warmup() or "
                "check is_ready() before embed_query()."
            )
        vec = next(self._model.query_embed([text]))
        return [float(x) for x in vec]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Embed ``texts`` and return one ``list[float`` : per input.

        Passages are stored verbatim — no instruction prefix.
        """
        if not self._ready:
            raise EmbedderNotReady(
                "FastembedEmbedder is still loading; call warmup() or "
                "check is_ready() before embed_passages()."
            )
        return [[float(x) for x in vec] for vec in self._model.passage_embed(texts)]


__all__ = ["FastembedEmbedder"]
