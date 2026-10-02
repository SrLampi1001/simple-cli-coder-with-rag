"""Tests for the ``SqliteVecStore`` implementation.

Pinned by ``agent-development/07-vector-store-strategy/tests.md``.

``sqlite_vec`` and the ``sqlite3`` ``Connection`` are patched via
``pytest-mock`` so the real extension is not loaded and the test suite is
deterministic. The patched connection captures ``execute`` /
``executemany`` calls; tests assert on the captured call lists.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from simple_cli_coder_with_rag.domain.chunk import Chunk
from simple_cli_coder_with_rag.domain.vector_store import (
    VectorStoreBackendUnavailable,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class _StubConn:
    """Minimal stand-in for ``sqlite3.Connection`` capturing DDL/DML calls.

    ``__enter__`` / ``__exit__`` are implemented so ``with conn:``
    blocks work without raising. ``fetchall`` is what the store reads
    inside ``query``; tests populate it directly.
    """

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...] | None]] = []
        self.executemany_payloads: list[tuple[str, list[tuple[Any, ...]]]] = []
        self.executemany_calls: list[tuple[str, list[tuple[Any, ...]]]] = []
        self.fetchall_result: list[tuple[Any, ...]] = []
        self.enable_load_extension: Any = lambda *_a, **_k: None
        self.load_extension_calls: list[str] = []
        # Default ``load_extension`` is a no-op so the store's startup
        # check passes; tests that want to simulate failure override it.
        self.load_extension: Any = lambda *_a, **_k: None

    def __enter__(self) -> _StubConn:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> _StubConn:
        self.executed.append((sql, params))
        return self

    def executemany(self, sql: str, params: list[tuple[Any, ...]]) -> _StubConn:
        self.executemany_calls.append((sql, list(params)))
        self.executemany_payloads.append((sql, list(params)))
        return self

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.fetchall_result

    def commit(self) -> None:
        pass

    def close(self) -> None:
        pass


def _patch_sqlite3_connect(mocker: MockerFixture) -> tuple[Any, _StubConn]:
    """Patch ``sqlite3.connect`` so every call yields the same stub connection.

    Returns ``(factory, conn)`` where ``factory`` is the patched
    ``sqlite3.connect`` (tests inspect ``call_count`` on it) and
    ``conn`` is the stub connection the factory returns.
    """
    conn = _StubConn()
    factory = mocker.patch(
        "simple_cli_coder_with_rag.infrastructure.vector_stores.sqlite_vec_store.sqlite3.connect",
        return_value=conn,
    )
    return factory, conn


def _make_store(mocker: MockerFixture, tmp_path: Path) -> tuple[Any, _StubConn]:
    """Build a ``SqliteVecStore`` against a stubbed ``sqlite3.connect``.

    Returns ``(factory, conn)`` so tests can inspect the patched factory
    and the captured SQL calls.
    """
    from simple_cli_coder_with_rag.infrastructure.vector_stores.sqlite_vec_store import (
        SqliteVecStore,
    )

    factory, conn = _patch_sqlite3_connect(mocker)
    SqliteVecStore(tmp_path)
    return factory, conn


def _build_constructed_store(
    mocker: MockerFixture, tmp_path: Path
) -> tuple[Any, _StubConn, object]:
    """Build a ``SqliteVecStore`` and return ``(factory, conn, store)``.

    Same as ``_make_store`` but also returns the constructed store
    instance so the test can call ``upsert`` / ``query`` on it without
    re-patching ``sqlite3.connect`` or using ``__new__`` tricks.
    """
    from simple_cli_coder_with_rag.infrastructure.vector_stores.sqlite_vec_store import (
        SqliteVecStore,
    )

    factory, conn = _patch_sqlite3_connect(mocker)
    store = SqliteVecStore(tmp_path)
    return factory, conn, store


def test_init_raises_when_enable_load_extension_is_none(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """``SqliteVecStore(...)`` raises ``VectorStoreBackendUnavailable`` when the method is NULL.

    On SQLite builds with ``SQLITE_OMIT_LOAD_EXTENSION``,
    ``Connection.enable_load_extension`` is ``None``. The store must
    detect this on init and raise the documented exception.
    """
    from simple_cli_coder_with_rag.infrastructure.vector_stores.sqlite_vec_store import (
        SqliteVecStore,
    )

    conn = _StubConn()
    conn.enable_load_extension = None
    mocker.patch(
        "simple_cli_coder_with_rag.infrastructure.vector_stores.sqlite_vec_store.sqlite3.connect",
        return_value=conn,
    )

    with pytest.raises(VectorStoreBackendUnavailable):
        SqliteVecStore(tmp_path)


def test_init_raises_when_enable_load_extension_raises_not_supported(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """``enable_load_extension`` raising ``NotSupportedError`` triggers the fallback exception."""
    from simple_cli_coder_with_rag.infrastructure.vector_stores.sqlite_vec_store import (
        SqliteVecStore,
    )

    conn = _StubConn()

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise sqlite3.NotSupportedError("disabled")

    conn.enable_load_extension = _boom
    mocker.patch(
        "simple_cli_coder_with_rag.infrastructure.vector_stores.sqlite_vec_store.sqlite3.connect",
        return_value=conn,
    )

    with pytest.raises(VectorStoreBackendUnavailable):
        SqliteVecStore(tmp_path)


def test_init_raises_when_enable_load_extension_raises_operational(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """``enable_load_extension`` raising ``OperationalError`` triggers the fallback exception."""
    from simple_cli_coder_with_rag.infrastructure.vector_stores.sqlite_vec_store import (
        SqliteVecStore,
    )

    conn = _StubConn()

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise sqlite3.OperationalError("disabled by build")

    conn.enable_load_extension = _boom
    mocker.patch(
        "simple_cli_coder_with_rag.infrastructure.vector_stores.sqlite_vec_store.sqlite3.connect",
        return_value=conn,
    )

    with pytest.raises(VectorStoreBackendUnavailable):
        SqliteVecStore(tmp_path)


def test_init_raises_when_load_extension_raises(mocker: MockerFixture, tmp_path: Path) -> None:
    """``load_extension`` itself raising also triggers the fallback exception."""
    from simple_cli_coder_with_rag.infrastructure.vector_stores.sqlite_vec_store import (
        SqliteVecStore,
    )

    conn = _StubConn()

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise sqlite3.OperationalError("vec0 not found")

    conn.load_extension = _boom
    mocker.patch(
        "simple_cli_coder_with_rag.infrastructure.vector_stores.sqlite_vec_store.sqlite3.connect",
        return_value=conn,
    )

    with pytest.raises(VectorStoreBackendUnavailable):
        SqliteVecStore(tmp_path)


def test_init_creates_schema_with_cosine_aux_and_metadata(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """The ``CREATE VIRTUAL TABLE`` statement matches the dev-tools.md §4 schema.

    The captured DDL must include ``vec0``, ``float[384]``,
    ``distance_metric=cosine``, ``+text`` (auxiliary), ``session_id`` and
    ``created_at``. Auxiliary columns are returned with hits but not
    searched; plain columns are metadata for filtering.
    """
    _, conn = _make_store(mocker, tmp_path)

    ddl = [sql for sql, _ in conn.executed if sql.lstrip().upper().startswith("CREATE")]
    assert ddl, "no CREATE statement captured"
    statement = ddl[0]

    assert "vec0" in statement, statement
    assert "float[384]" in statement, statement
    assert "distance_metric=cosine" in statement, statement
    assert "+text" in statement, (
        "text column must be auxiliary (+) so long chunk text doesn't blow the metadata size cap"
    )
    assert "TEXT" in statement, statement
    assert "session_id" in statement, statement
    assert "created_at" in statement, statement


def test_init_calls_load_extension_with_vec0(mocker: MockerFixture, tmp_path: Path) -> None:
    """``init`` calls ``conn.load_extension('vec0')`` exactly once."""
    from simple_cli_coder_with_rag.infrastructure.vector_stores.sqlite_vec_store import (
        SqliteVecStore,
    )

    conn = _StubConn()
    conn.load_extension_calls = []

    real_load = conn.load_extension  # type: ignore[attr-defined]

    def _load_record(name: str) -> None:
        conn.load_extension_calls.append(name)
        real_load(name)

    conn.load_extension = _load_record  # type: ignore[assignment]
    mocker.patch(
        "simple_cli_coder_with_rag.infrastructure.vector_stores.sqlite_vec_store.sqlite3.connect",
        return_value=conn,
    )

    SqliteVecStore(tmp_path)

    assert conn.load_extension_calls == ["vec0"], (
        f"expected one load_extension('vec0') call, got {conn.load_extension_calls!r}"
    )


def test_upsert_writes_rows(mocker: MockerFixture, tmp_path: Path) -> None:
    """``upsert`` ``executemany`` payload matches ``(vector, text, session_id, created_at)``."""
    _factory, conn, store = _build_constructed_store(mocker, tmp_path)

    chunks = [
        Chunk(text="hello", session_id="s1", metadata={"index": 0}),
        Chunk(text="world", session_id="s1", metadata={"index": 1}),
    ]
    vectors = [[0.1] * 384, [0.2] * 384]

    store.upsert(chunks, vectors)

    insert_calls = [
        (sql, params) for sql, params in conn.executemany_payloads if "INSERT" in sql.upper()
    ]
    assert insert_calls, "no INSERT executemany captured"
    rows = insert_calls[0][1]
    assert len(rows) == 2, f"expected 2 insert rows, got {len(rows)}"

    expected_texts = ["hello", "world"]
    expected_session = "s1"
    for row, text in zip(rows, expected_texts, strict=True):
        # The tuple shape is ``(vector, text, session_id, created_at)``.
        assert isinstance(row[0], bytes), f"expected blob vector, got {type(row[0]).__name__}"
        assert row[1] == text
        assert row[2] == expected_session
        assert isinstance(row[3], int), f"created_at must be int, got {type(row[3]).__name__}"


def test_upsert_is_idempotent_by_session(mocker: MockerFixture, tmp_path: Path) -> None:
    """Two ``upsert`` calls for the same ``session_id`` produce exactly one set of rows."""
    _, conn, store = _build_constructed_store(mocker, tmp_path)

    store.upsert(
        [Chunk(text="hi", session_id="idem", metadata={"i": 0})],
        [[0.1] * 384],
    )
    first_insert_rows = [
        len(params) for sql, params in conn.executemany_payloads if "INSERT" in sql.upper()
    ]
    assert first_insert_rows == [1], first_insert_rows

    store.upsert(
        [Chunk(text="updated", session_id="idem", metadata={"i": 0})],
        [[0.2] * 384],
    )

    second_insert_rows = [
        len(params) for sql, params in conn.executemany_payloads if "INSERT" in sql.upper()
    ]
    assert second_insert_rows == [1, 1], (
        f"second upsert must not append rows for the same session: {second_insert_rows}"
    )

    # The DELETE must target the right session id.
    delete_calls = [
        params
        for sql, params in conn.executed
        if sql.lstrip().upper().startswith("DELETE") and params is not None
    ]
    assert all(params == ("idem",) for params in delete_calls), (
        f"DELETE clauses did not all target session_id='idem': {delete_calls}"
    )


def test_query_returns_top_k_by_cosine_similarity(mocker: MockerFixture, tmp_path: Path) -> None:
    """``query`` returns at most ``top_k`` chunks, sorted by similarity descending.

    Fixture: 5 chunks with orthogonal unit vectors. Query with ``[1,0,...]``
    and ``top_k=2``. The first hit is the chunk whose vector was
    ``[1,0,...]`` itself, with cosine similarity ``1.0``; the second has
    similarity ``0.0``. Both come back; everything else is filtered out.
    """
    _, conn, store = _build_constructed_store(mocker, tmp_path)

    dim = 384
    unit_vectors = [
        [1.0] + [0.0] * (dim - 1),
        [0.0, 1.0] + [0.0] * (dim - 2),
        [0.0, 0.0, 1.0] + [0.0] * (dim - 3),
        [0.0, 0.0, 0.0, 1.0] + [0.0] * (dim - 4),
        [0.0] * 5 + [1.0] + [0.0] * (dim - 6),
    ]

    chunks = [
        Chunk(text=f"chunk-{i}", session_id="s", metadata={"index": i})
        for i in range(len(unit_vectors))
    ]
    store.upsert(chunks, unit_vectors)

    # ``sqlite-vec`` with ``distance_metric=cosine`` returns
    # ``distance = 1 - cosine_similarity``. distance 0.0 → similarity 1.0,
    # distance 1.0 → similarity 0.0.
    conn.fetchall_result = [
        (0.0, "chunk-0", "s", 1),
        (1.0, "chunk-1", "s", 1),
    ]

    results = store.query([1.0] + [0.0] * (dim - 1), top_k=2)

    assert len(results) == 2
    assert results[0][0].text == "chunk-0"
    assert results[0][1] == pytest.approx(1.0)
    assert results[1][0].text == "chunk-1"
    assert results[1][1] == pytest.approx(0.0)


def test_query_returns_similarity_in_minus_one_one(mocker: MockerFixture, tmp_path: Path) -> None:
    """Every similarity score returned by ``query`` is in ``[-1.0, 1.0]``.

    Cosine similarity is mathematically in this range. Floating-point
    error can push ``1 - distance`` a hair outside the range for a
    perfectly aligned vector. The store clamps.
    """
    _, conn, store = _build_constructed_store(mocker, tmp_path)

    conn.fetchall_result = [
        (-0.01, "chunk-aligned", "s", 1),
        (1.01, "chunk-ortho", "s", 1),
        (1.5, "chunk-anti", "s", 1),
    ]

    results = store.query([1.0] + [0.0] * 383, top_k=3)

    assert len(results) == 3
    for _chunk, similarity in results:
        assert -1.0 <= similarity <= 1.0, f"similarity {similarity} out of [-1, 1] range"


def test_query_selects_distance_column_first(mocker: MockerFixture, tmp_path: Path) -> None:
    """``query`` selects the ``distance`` column (not the ``embedding`` blob).

    ``vec0`` virtual tables compute distance on the fly from the
    ``embedding`` column; selecting ``embedding`` returns the raw
    float32 blob. ``distance`` is the column the ``MATCH`` query
    exposes.
    """
    _, conn, store = _build_constructed_store(mocker, tmp_path)

    conn.fetchall_result = []

    store.query([0.0] * 384, top_k=3)

    selects = [sql for sql, _params in conn.executed if sql.lstrip().upper().startswith("SELECT")]
    assert selects, "no SELECT captured"
    select = selects[0]
    assert "distance" in select, f"distance column missing: {select!r}"
    # Make sure we don't accidentally select the raw embedding column.
    assert "SELECT embedding" not in select and "SELECT\nembedding" not in select, (
        f"query must not select the raw embedding column: {select!r}"
    )


def test_query_opens_fresh_connection(mocker: MockerFixture, tmp_path: Path) -> None:
    """``query`` calls ``sqlite3.connect`` to open a fresh connection.

    Per dev-tools.md §4, the store must open a fresh connection inside
    the worker so a connection opened on the main thread is never
    shared with retrieval. The patched factory counts calls.
    """
    factory, conn, store = _build_constructed_store(mocker, tmp_path)

    # Reset the factory's call list so the constructor's call doesn't
    # pollute the assertion.
    factory.reset_mock()
    conn.fetchall_result = []

    store.query([0.0] * 384, top_k=3)

    assert factory.call_count == 1, (
        f"expected one sqlite3.connect call inside query, got {factory.call_count}"
    )


def test_query_handles_empty_store(mocker: MockerFixture, tmp_path: Path) -> None:
    """``query`` on a fresh store returns ``[]`` rather than raising."""
    _, conn, store = _build_constructed_store(mocker, tmp_path)

    conn.fetchall_result = []

    results = store.query([0.0] * 384, top_k=3)

    assert results == []
