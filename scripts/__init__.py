"""Scripts package — manually-invoked utility scripts.

This package lives outside ``src/`` so the gate does not lint it as
production code; the E2E scripts here are user-invoked and depend on
network access. ``scripts/e2e_file_editing.py`` is the real-API smoke
test for DO-10 (file editing)."""

__all__: list[str] = []
