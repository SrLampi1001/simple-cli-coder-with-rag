"""Strategy implementations of the ``VectorStore`` Protocol.

The default for v1 is :class:`SqliteVecStore` — a persistent store
backed by ``sqlite-vec``'s ``vec0`` virtual table with
``distance_metric=cosine``. The
:class:`NumpyBruteForceStore` fallback is in-memory and activates
when ``sqlite-vec`` cannot load (``SQLITE_OMIT_LOAD_EXTENSION``) or
when the user opts in via ``VECTOR_STORE=brute_force``.

DO-13 adds the ``build_vector_store`` factory (in this package's
``factory`` submodule) — the single composition point that picks the
backend from :class:`Settings`. A future DO will add a
``SupabaseVectorStore`` sibling and extend the factory; the rest of
the codebase is unaware of the choice.

Architectural note: ``sqlite_vec`` may only be imported from this
package. ``import-linter`` enforces this with a ``forbidden_imports``
contract in ``pyproject.toml``; the ``tests/infrastructure/vector_stores/``
test suite is a redundant safeguard against contract regressions.
"""

from simple_cli_coder_with_rag.infrastructure.vector_stores.factory import (
    Strategy,
    build_vector_store,
)
from simple_cli_coder_with_rag.infrastructure.vector_stores.numpy_brute_force_store import (
    NumpyBruteForceStore,
)
from simple_cli_coder_with_rag.infrastructure.vector_stores.sqlite_vec_store import (
    SqliteVecStore,
)

__all__ = [
    "NumpyBruteForceStore",
    "SqliteVecStore",
    "Strategy",
    "build_vector_store",
]
