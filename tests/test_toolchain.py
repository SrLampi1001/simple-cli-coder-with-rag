import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, cwd=ROOT)


def test_ruff_check_passes() -> None:
    _run(["uv", "run", "ruff", "check", "."])


def test_ruff_format_check_passes() -> None:
    _run(["uv", "run", "ruff", "format", "--check", "."])


def test_mypy_passes() -> None:
    _run(["uv", "run", "mypy", "src"])


def test_import_linter_passes() -> None:
    _run(["uv", "run", "lint-imports"])


def test_pytest_collects() -> None:
    _run(["uv", "run", "pytest", "--collect-only", "-q"])


def test_uv_lock_reproducible() -> None:
    lock = ROOT / "uv.lock"
    if not lock.exists():
        pytest.skip("uv.lock is not in the working tree")
    backup = lock.read_bytes()
    lock.unlink()
    try:
        _run(["uv", "lock"])
        subprocess.run(["git", "diff", "--exit-code", "uv.lock"], check=True, cwd=ROOT)
    finally:
        lock.write_bytes(backup)
