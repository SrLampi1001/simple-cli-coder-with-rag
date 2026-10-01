# DO-06 workflow

## Subagent delegation

**One subagent.** The Protocol, the embedder, the settings field, the `AppState` field, and the composition-root wiring are tightly coupled.

### Context passed to the subagent

- `agent-development/README.md`.
- The four files in this folder.
- `docs/development-tools.md` §5 in full (the embedder section).
- Nothing else.

## Web-search verification

Before pinning anything embedder-related:

1. `websearch "fastembed pypi latest version 2026"` — confirm the version in dev-tools.md §1 is still current.
2. `websearch "BAAI bge-small-en-v1.5 model card huggingface"` — confirm the model ID is unchanged. (It has been stable for years; a rename is the only thing that would break us.)
3. `websearch "fastembed TextEmbedding query_embed passage_embed 2026"` — confirm the two-method API is still the supported one.

If `fastembed` has moved across a minor, update `pyproject.toml` and add a `bump:` line to the commit body. If it has moved across a major, stop and ask the user.

## Steps

1. **Pre-flight.** `git status` clean.

2. **Write the test files** from `tests.md` first. Confirm they fail.

3. **Write `src/simple_cli_coder_with_rag/domain/embedder.py`** with `Embedder` Protocol and `EmbedderNotReady`.

4. **Write `src/simple_cli_coder_with_rag/infrastructure/embedders/__init__.py`** (empty) and `fastembed_embedder.py` with `FastembedEmbedder`. Implementation notes:

   - Use `from fastembed import TextEmbedding` at the top of the module.
   - `_load` runs on a `threading.Thread(daemon=True, target=self._load)`. `_load` constructs `TextEmbedding(model_name=self.model_name, cache_dir=str(self.cache_dir), local_files_only=self.local_files_only)` and assigns to `self._model`. Then sets `self._ready = True` and `self._ready_event.set()`.
   - On first run, before constructing `TextEmbedding`, check whether the model files exist in `cache_dir`. If not, `print("downloading embedding model (one time only)…", file=sys.stderr)` once. Use a class-level flag to ensure the message is printed only once per process even with multiple embedders.
   - `embed_query` calls `next(self._model.query_embed([text]))` and returns `list(vec)`.
   - `embed_passages` calls `list(self._model.passage_embed(texts))` and maps each to `list(v)`.
   - `warmup(timeout=None)`: blocks on `self._ready_event.wait(timeout=timeout)`; if timeout and not ready, raise `TimeoutError`.

5. **Add `forbidden_imports` contract** to `pyproject.toml`:
   ```toml
   [[tool.importlinter.contracts]]
   type = "forbidden_imports"
   source_modules = ["simple_cli_coder_with_rag.application", "simple_cli_coder_with_rag.domain", "simple_cli_coder_with_rag.presentation"]
   forbidden_modules = ["fastembed"]
   ```
   This is a regression guard: `fastembed` must not leak out of `infrastructure/embedders/`.

6. **Update `Settings`** in `infrastructure/settings.py`:
   ```python
   embedding_model: str = "BAAI/bge-small-en-v1.5"
   embedding_local_files_only: bool = True
   ```

7. **Update `AppState`** to add `embedder: Embedder | None = None`.

8. **Update composition root** in `cli.py`:
   - `cache_dir = Path(user_cache_dir("simple-cli-coder-with-rag")) / "models"`.
   - `embedder = FastembedEmbedder(model_name=settings.embedding_model, cache_dir=cache_dir, local_files_only=settings.embedding_local_files_only)`.
   - Assign to `app_state.embedder`.
   - Do **not** call `embedder.warmup()` here; the background thread runs. DO-09 will use `is_ready()` to decide whether to retrieve.

9. **Run the gate.** All exit 0.

10. **Manual smoke test** (separate terminal, not committed): delete `~/.cache/simple-cli-coder-with-rag/models/` to force a download, run `uv run coder`, observe the `downloading embedding model (one time only)…` message on stderr, type `/exit`. Second run: no message.

11. **Commit:**
    ```bash
    git add src/simple_cli_coder_with_rag/domain/embedder.py \
            src/simple_cli_coder_with_rag/infrastructure/embedders \
            src/simple_cli_coder_with_rag/infrastructure/settings.py \
            src/simple_cli_coder_with_rag/presentation/commands/__init__.py \
            src/simple_cli_coder_with_rag/cli.py \
            pyproject.toml uv.lock \
            tests/domain/test_embedder.py \
            tests/infrastructure/embedders
    git status
    git commit -m "feat(embed): fastembed BGE-small behind Embedder Protocol with warm-up thread

    - domain/embedder.py: Embedder Protocol (embed_query, embed_passages, warmup,
      is_ready) + EmbedderNotReady.
    - infrastructure/embedders/fastembed_embedder.py: FastembedEmbedder with
      cache_dir under platformdirs user_cache_dir/models, local_files_only=True,
      daemon background thread for warm-up, one-time stderr 'downloading…' message
      on cold cache.
    - infrastructure/settings.py: embedding_model + embedding_local_files_only.
    - pyproject.toml: import-linter forbidden_imports contract pins fastembed to
      infrastructure/embedders/ only.
    - composition root builds the embedder and assigns to AppState; does not block
      on warm-up.

    Satisfies README bullet 3: 'The embedding model works'."
    ```

12. **Post-flight.** `git status` clean.

## Failure modes

- **`fastembed.TextEmbedding` takes different kwargs in a newer version:** check the constructor signature before pinning. The kwargs in this deliverable are stable across 0.7.x and 0.8.x.
- **Tests block on the real model download:** `pytest-mock` patches `TextEmbedding`, so the real download is never triggered. If a test ever hits the network, the patch is missing.
- **Warm-up thread outlives the process and prints `downloading…` after `prompt_toolkit` starts:** the print happens in `_load`, which runs on the daemon thread. If `prompt_toolkit` is already running, the message will corrupt the prompt. Mitigate by checking `app_state.repl_active` (set in DO-09) and writing to the log file instead.
