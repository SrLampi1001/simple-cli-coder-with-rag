# DO-06 tests

These tests must be written **before** any code in this deliverable.

## Test files

```
tests/domain/
└── test_embedder.py

tests/infrastructure/embedders/
├── __init__.py
└── test_fastembed_embedder.py
```

## Test functions and assertions

### `tests/domain/test_embedder.py`

- `test_protocol_has_required_methods` — Protocol declares all four methods with correct signatures.
- `test_embedder_not_ready_is_runtime_error` — `EmbedderNotReady` is a `RuntimeError` subclass.

### `tests/infrastructure/embedders/test_fastembed_embedder.py`

`fastembed.TextEmbedding` is patched via `pytest-mock`. The patched instance returns deterministic 384-dim lists.

- `test_constructor_does_not_block` — constructing `FastembedEmbedder()` returns within 100 ms (i.e., the model is not loaded eagerly).
- `test_is_ready_false_initially` — right after `__init__`, `is_ready()` is `False`.
- `test_embed_query_before_ready_raises` — calling `embed_query` before the background thread sets `_ready` raises `EmbedderNotReady`.
- `test_embed_passages_before_ready_raises` — same for `embed_passages`.
- `test_warmup_blocks_until_ready` — calling `warmup()` (no timeout) returns only after the patched `TextEmbedding` is constructed and `_ready` is set.
- `test_warmup_timeout_raises` — `warmup(timeout=0.01)` with a `TextEmbedding` patched to sleep 1 s raises `TimeoutError`.
- `test_embed_query_returns_384_dim_list` — after `warmup`, `embed_query("hi")` returns a list of length 384.
- `test_embed_passages_returns_list_of_384_dim_lists` — `embed_passages(["a", "b", "c"])` returns 3 lists of length 384 each.
- `test_text_embedding_constructed_with_cache_dir` — captured `cache_dir` arg equals the platformdirs path under `simple-cli-coder-with-rag/models`.
- `test_text_embedding_constructed_with_local_files_only` — captured `local_files_only` arg equals `True`.
- `test_first_run_prints_message_to_stderr_once` — using a temp cache dir that does not contain the model, patching `sys.stderr`, the message `downloading embedding model (one time only)…` appears exactly once during the background-thread load. A second init does not print it.
- `test_does_not_pollute_other_layers` — `grep -r "import fastembed" src/simple_cli_coder_with_rag/` shows only `infrastructure/embedders/fastembed_embedder.py`. (This is enforced by an `import-linter` `forbidden_imports` contract in `pyproject.toml`; the test is a smoke test to catch regressions.)

## Why these tests

- The "constructor does not block" test pins the warm-up thread requirement — the biggest UX win of this layer.
- The `is_ready` test pins the contract that lets the REPL degrade gracefully when the model is still loading.
- The cache-dir test pins the dev-tools.md §5 "survive reboots" requirement.
- The stderr-once test pins the first-run UX without leaking the message into the prompt.
