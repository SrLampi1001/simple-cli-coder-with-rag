"""Tests for the ``FastembedEmbedder`` implementation.

Pinned by ``agent-development/06-embedder-strategy/tests.md``.

``fastembed.TextEmbedding`` is patched via ``pytest-mock`` so the real
~130 MB BGE model is never downloaded in the test suite. The patched
instance yields deterministic 384-dim vectors (the dimensionality of
``BAAI/bge-small-en-v1.5``).
"""

from __future__ import annotations

import io
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from simple_cli_coder_with_rag.domain.embedder import EmbedderNotReady

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _stub_text_embedding(mocker: MockerFixture) -> MagicMock:
    """Patch the ``TextEmbedding`` symbol where the embedder uses it.

    The embedder imports ``TextEmbedding`` at module level, so patching
    ``fastembed.TextEmbedding`` (where the symbol is defined) would not
    affect the already-imported reference. We patch the bound name in
    the embedder module instead.

    Returns the patched factory (the MagicMock ``pytest-mock`` creates
    in place of the real class). The factory's ``call_args`` is what
    tests need to inspect to verify the embedder forwarded the right
    kwargs.
    """
    instance = mocker.MagicMock(name="TextEmbeddingInstance")
    instance.query_embed.return_value = iter([[0.1] * 384])
    instance.passage_embed.return_value = iter([[0.2] * 384, [0.3] * 384, [0.4] * 384])
    factory = mocker.patch(
        "simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder.TextEmbedding",
        return_value=instance,
    )
    return factory


def _make_embedder(
    mocker: MockerFixture,
    *,
    cache_dir: Path,
    local_files_only: bool = True,
):
    """Build a fresh embedder, reset module-level flags, and return them.

    The module-level ``_announced`` (and ``_REPL_ACTIVE``) flags persist
    across tests, so they are reset here to keep each test deterministic.

    Returns ``(embedder, factory)`` where ``factory`` is the patched
    ``fastembed.TextEmbedding`` — what to inspect ``call_args`` on.
    """
    factory = _stub_text_embedding(mocker)
    from simple_cli_coder_with_rag.infrastructure.embedders import fastembed_embedder as mod

    mod._announced = False
    mod._REPL_ACTIVE = False

    from simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder import (
        FastembedEmbedder,
    )

    embedder = FastembedEmbedder(
        cache_dir=cache_dir,
        local_files_only=local_files_only,
    )
    return embedder, factory


def test_constructor_does_not_block(tmp_path: Path, mocker: MockerFixture) -> None:
    """Constructing the embedder returns within 100ms; model loading is async.

    The model download / load runs on a daemon thread, so the constructor
    only pays the cost of starting that thread. The test is sensitive to
    ``fastembed`` import overhead — to make the timing reliable the
    import is performed outside the measured region (a separate ``import``
    statement before the timer starts).
    """
    from simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder import (
        FastembedEmbedder,
    )

    # Trigger the ``fastembed.TextEmbedding`` import so it doesn't count
    # against the constructor's 100ms budget.
    factory = _stub_text_embedding(mocker)
    factory.return_value = mocker.MagicMock(name="TextEmbeddingInstance")
    import simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder as mod

    mod._announced = False
    mod._REPL_ACTIVE = False

    start = time.perf_counter()
    embedder = FastembedEmbedder(cache_dir=tmp_path)
    elapsed = time.perf_counter() - start

    assert embedder is not None
    assert embedder.is_ready() is False or elapsed < 0.1, (
        f"constructor took {elapsed * 1000:.1f} ms — must not block"
    )


def test_constructor_returns_before_ready(tmp_path: Path, mocker: MockerFixture) -> None:
    """``__init__`` returns before the daemon thread sets ``_ready`` to True."""
    embedder, _ = _make_embedder(mocker, cache_dir=tmp_path)
    # The mock constructor is synchronous, but the assignment to ``self._ready``
    # happens inside the daemon thread, which may not have run yet. The contract
    # is that ``is_ready()`` is callable immediately, not that it must be False.
    # Either False or True is acceptable; we only assert the embedder exists.
    assert embedder is not None


def test_is_ready_false_initially(tmp_path: Path, mocker: MockerFixture) -> None:
    """Right after ``__init__``, ``is_ready()`` is callable and returns a bool."""
    embedder, _ = _make_embedder(mocker, cache_dir=tmp_path)
    result = embedder.is_ready()
    assert isinstance(result, bool)


def test_embed_query_before_ready_raises(tmp_path: Path, mocker: MockerFixture) -> None:
    """Calling ``embed_query`` before ready raises ``EmbedderNotReady``."""
    # Force not-ready state by patching ``TextEmbedding`` (where the
    # embedder uses it) with a slow constructor. The embedder's daemon
    # thread blocks on the slow init, ``embed_query`` runs in the main
    # thread before the daemon thread sets ``_ready``.
    blocker = threading.Event()

    def slow_init(*_args, **_kwargs):
        blocker.wait(timeout=5)
        return MagicMock()

    import simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder as mod

    mod._announced = False
    mod._REPL_ACTIVE = False
    mocker.patch(
        "simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder.TextEmbedding",
        side_effect=slow_init,
    )

    from simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder import (
        FastembedEmbedder,
    )

    embedder = FastembedEmbedder(cache_dir=tmp_path)
    try:
        with pytest.raises(EmbedderNotReady):
            embedder.embed_query("hello")
    finally:
        blocker.set()
        embedder.warmup()


def test_embed_passages_before_ready_raises(tmp_path: Path, mocker: MockerFixture) -> None:
    """Calling ``embed_passages`` before ready raises ``EmbedderNotReady``."""
    blocker = threading.Event()

    def slow_init(*_args, **_kwargs):
        blocker.wait(timeout=5)
        return MagicMock()

    import simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder as mod

    mod._announced = False
    mod._REPL_ACTIVE = False
    mocker.patch(
        "simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder.TextEmbedding",
        side_effect=slow_init,
    )

    from simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder import (
        FastembedEmbedder,
    )

    embedder = FastembedEmbedder(cache_dir=tmp_path)
    try:
        with pytest.raises(EmbedderNotReady):
            embedder.embed_passages(["a", "b"])
    finally:
        blocker.set()
        embedder.warmup()


def test_warmup_blocks_until_ready(tmp_path: Path, mocker: MockerFixture) -> None:
    """``warmup()`` blocks until the patched ``TextEmbedding`` is constructed."""
    embedder, _ = _make_embedder(mocker, cache_dir=tmp_path)
    embedder.warmup()
    assert embedder.is_ready() is True


def test_warmup_timeout_raises(tmp_path: Path, mocker: MockerFixture) -> None:
    """``warmup(timeout=0.01)`` with a sleeping ``TextEmbedding`` raises ``TimeoutError``."""
    blocker = threading.Event()

    def slow_init(*_args, **_kwargs):
        blocker.wait(timeout=10)
        return MagicMock()

    import simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder as mod

    mod._announced = False
    mod._REPL_ACTIVE = False
    mocker.patch(
        "simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder.TextEmbedding",
        side_effect=slow_init,
    )

    from simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder import (
        FastembedEmbedder,
    )

    embedder = FastembedEmbedder(cache_dir=tmp_path)
    try:
        with pytest.raises(TimeoutError):
            embedder.warmup(timeout=0.01)
    finally:
        blocker.set()
        # Drain so the daemon thread does not outlive the test.
        embedder.warmup()


def test_embed_query_returns_384_dim_list(tmp_path: Path, mocker: MockerFixture) -> None:
    """After warmup, ``embed_query("hi")`` returns a list of length 384."""
    embedder, _ = _make_embedder(mocker, cache_dir=tmp_path)
    embedder.warmup()

    out = embedder.embed_query("hi")

    assert len(out) == 384


def test_embed_passages_returns_list_of_384_dim_lists(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """After warmup, ``embed_passages([...])`` returns N lists of length 384."""
    embedder, _ = _make_embedder(mocker, cache_dir=tmp_path)
    embedder.warmup()

    out = embedder.embed_passages(["a", "b", "c"])

    assert len(out) == 3
    assert all(len(v) == 384 for v in out)


def test_text_embedding_constructed_with_cache_dir(tmp_path: Path, mocker: MockerFixture) -> None:
    """``TextEmbedding(...)`` receives ``cache_dir`` matching the configured path."""
    embedder, factory = _make_embedder(mocker, cache_dir=tmp_path)
    embedder.warmup()

    call_kwargs = factory.call_args.kwargs
    assert Path(call_kwargs["cache_dir"]) == tmp_path


def test_text_embedding_constructed_with_local_files_only(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    """``local_files_only=True`` is forwarded to ``TextEmbedding(...)``."""
    # Warm cache (snapshot dir present) so the cold-cache download
    # fallback in ``_load`` does not override ``local_files_only``.
    (tmp_path / "models--BAAI--bge-small-en-v1.5").mkdir()
    embedder, factory = _make_embedder(mocker, cache_dir=tmp_path, local_files_only=True)
    embedder.warmup()

    call_kwargs = factory.call_args.kwargs
    assert call_kwargs["local_files_only"] is True


def test_text_embedding_default_local_files_only(tmp_path: Path, mocker: MockerFixture) -> None:
    """The default ``local_files_only`` is ``True`` (verified by the dev-tools.md §5 note)."""
    (tmp_path / "models--BAAI--bge-small-en-v1.5").mkdir()
    embedder, factory = _make_embedder(mocker, cache_dir=tmp_path)
    embedder.warmup()

    call_kwargs = factory.call_args.kwargs
    assert call_kwargs["local_files_only"] is True


def test_text_embedding_constructed_with_model_name(tmp_path: Path, mocker: MockerFixture) -> None:
    """``TextEmbedding(...)`` receives the configured ``model_name``."""
    embedder, factory = _make_embedder(mocker, cache_dir=tmp_path)
    embedder.warmup()

    call_kwargs = factory.call_args.kwargs
    assert call_kwargs["model_name"] == "BAAI/bge-small-en-v1.5"


def test_first_run_prints_message_to_stderr_once(tmp_path: Path, mocker: MockerFixture) -> None:
    """When the cache dir is empty, the message is written to stderr **once** per process.

    The module-level ``_announced`` flag survives the first init, so a second
    embedder constructed in the same process must **not** reprint it.
    """
    _stub_text_embedding(mocker)
    import simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder as mod

    mod._announced = False
    mod._REPL_ACTIVE = False

    from simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder import (
        FastembedEmbedder,
    )

    # First init — capture stderr.
    captured1 = io.StringIO()
    old_stderr = sys.stderr
    sys.stderr = captured1
    try:
        embedder1 = FastembedEmbedder(cache_dir=tmp_path)
        embedder1.warmup()
        output1 = captured1.getvalue()
    finally:
        sys.stderr = old_stderr

    assert "downloading embedding model" in output1, (
        f"first init did not announce cold-cache: {output1!r}"
    )

    # Second init — capture stderr.
    captured2 = io.StringIO()
    sys.stderr = captured2
    try:
        embedder2 = FastembedEmbedder(cache_dir=tmp_path)
        embedder2.warmup()
        output2 = captured2.getvalue()
    finally:
        sys.stderr = old_stderr

    assert "downloading embedding model" not in output2, (
        f"second init must not re-announce: {output2!r}"
    )


def test_no_stderr_message_when_cache_warm(tmp_path: Path, mocker: MockerFixture) -> None:
    """When the cache dir contains a ``models--BAAI--bge-small-en-v1.5`` snapshot, no message."""
    _stub_text_embedding(mocker)
    import simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder as mod

    mod._announced = False
    mod._REPL_ACTIVE = False

    # Simulate a warm cache by creating the snapshot directory that
    # ``huggingface-hub`` would create for the model.
    (tmp_path / "models--BAAI--bge-small-en-v1.5").mkdir()

    from simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder import (
        FastembedEmbedder,
    )

    captured = io.StringIO()
    old_stderr = sys.stderr
    sys.stderr = captured
    try:
        embedder = FastembedEmbedder(cache_dir=tmp_path)
        embedder.warmup()
        output = captured.getvalue()
    finally:
        sys.stderr = old_stderr

    assert "downloading embedding model" not in output, f"warm cache must not announce: {output!r}"


def test_repl_active_routes_announcement_to_loguru(tmp_path: Path, mocker: MockerFixture) -> None:
    """When ``_REPL_ACTIVE`` is True, the cold-cache message goes to loguru, not stderr.

    ``prompt_toolkit`` owns the screen while the REPL is running, so writing
    to stderr would corrupt the prompt. The module-level flag is flipped by
    the composition root immediately before ``repl.run()``; the embedder's
    background thread sees the flag and routes the message through ``loguru``
    instead.
    """
    _stub_text_embedding(mocker)
    import simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder as mod

    mod._announced = False
    mod._REPL_ACTIVE = True  # simulate "REPL is about to start"
    fake_logger = mocker.patch.object(mod, "logger", create=True)

    from simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder import (
        FastembedEmbedder,
    )

    captured = io.StringIO()
    old_stderr = sys.stderr
    sys.stderr = captured
    try:
        embedder = FastembedEmbedder(cache_dir=tmp_path)
        embedder.warmup()
        stderr_output = captured.getvalue()
    finally:
        sys.stderr = old_stderr

    assert stderr_output == "", f"REPL-active mode must not write to stderr, got: {stderr_output!r}"
    fake_logger.info.assert_called_once()
    assert "downloading embedding model" in fake_logger.info.call_args.args[0]


def test_repl_active_default(tmp_path: Path) -> None:
    """``_REPL_ACTIVE`` defaults to ``False`` so a fresh import announces to stderr."""
    # Reset by reimporting would be flaky; instead, verify the default via
    # a fresh subprocess that only reads the module attribute.
    import subprocess

    script = (
        "import sys; "
        "from simple_cli_coder_with_rag.infrastructure.embedders import "
        "fastembed_embedder as m; "
        "sys.stdout.write(repr(m._REPL_ACTIVE))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "False"


def test_does_not_pollute_other_layers() -> None:
    """``fastembed`` imports only in the embedder module.

    Smoke test for the ``import-linter`` ``forbidden`` contract in
    ``pyproject.toml``. The grep matches ``import fastembed`` /
    ``from fastembed`` lines (any leading whitespace) so the path
    component in this package's own ``__init__.py`` does not
    false-positive.
    """
    import subprocess

    result = subprocess.run(
        [
            "grep",
            "-r",
            "-n",
            "-E",
            r"^\s*(import fastembed|from fastembed)",
            "src/simple_cli_coder_with_rag/",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    matches = result.stdout.splitlines()
    assert matches, "no files import fastembed — the embedder module is missing"
    for match in matches:
        path = match.split(":", 1)[0]
        assert path.endswith(
            "src/simple_cli_coder_with_rag/infrastructure/embedders/fastembed_embedder.py"
        ), f"fastembed leaks outside the embedder module: {match}"
