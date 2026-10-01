# DO-06 contracts

## Architectural

- [ ] New modules:
  - `simple_cli_coder_with_rag.domain.embedder` (Protocol + exception)
  - `simple_cli_coder_with_rag.infrastructure.embedders.fastembed_embedder`
- [ ] `import-linter` reports zero violations.
- [ ] `fastembed` is imported **only** in `infrastructure/embedders/fastembed_embedder.py`.

## Behavioral

- [ ] `FastembedEmbedder()` constructor returns immediately; `_ready` is `False`.
- [ ] The background thread eventually sets `_ready = True`.
- [ ] Calling `embed_query` before `_ready` raises `EmbedderNotReady`.
- [ ] After `_ready`, `embed_query("hello")` returns a list of 384 floats.
- [ ] After `_ready`, `embed_passages(["a", "b"])` returns a list of 2 lists, each of 384 floats.
- [ ] `warmup()` blocks until `_ready` (or raises `TimeoutError` if a `timeout` is passed and exceeded).
- [ ] The `fastembed.TextEmbedding` constructor is called with `cache_dir` matching `Path(user_cache_dir("simple-cli-coder-with-rag")) / "models"` and `local_files_only=True`.
- [ ] First-run UX: when `cache_dir` does not contain the model, the embedder writes `downloading embedding model (one time only)…` to stderr **once** during the background thread. Subsequent inits do not write it.
- [ ] `Settings(embedding_model=...)` and `Settings(embedding_local_files_only=...)` work; defaults are as documented.

## Schema

- [ ] `class Embedder(Protocol)`:
  - `embed_query(self, text: str) -> list[float]`
  - `embed_passages(self, texts: list[str]) -> list[list[float]]`
  - `warmup(self, *, timeout: float | None = None) -> None`
  - `is_ready(self) -> bool`
- [ ] `class EmbedderNotReady(RuntimeError)` in `domain/embedder.py`.
- [ ] `class FastembedEmbedder`:
  - `__init__(self, *, model_name: str = "BAAI/bge-small-en-v1.5", cache_dir: Path | None = None, local_files_only: bool = True) -> None`
  - `embed_query(self, text: str) -> list[float]`
  - `embed_passages(self, texts: list[str]) -> list[list[float]]`
  - `warmup(self, *, timeout: float | None = None) -> None`
  - `is_ready(self) -> bool`
- [ ] `Settings.embedding_model: str = "BAAI/bge-small-en-v1.5"`.
- [ ] `Settings.embedding_local_files_only: bool = True`.
- [ ] `AppState.embedder: Embedder | None = None`.
