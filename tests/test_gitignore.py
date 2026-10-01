import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _gitignore_entries() -> list[str]:
    return [
        line.strip()
        for line in (ROOT / ".gitignore").read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _normalized_entries() -> set[str]:
    return {line.rstrip("/") for line in _gitignore_entries()}


def test_gitignore_exists() -> None:
    assert (ROOT / ".gitignore").is_file()


def test_gitignore_covers_python_artifacts() -> None:
    entries = _normalized_entries()
    for expected in ("__pycache__", "*.py[cod]", ".venv", "dist", "build", "*.egg-info"):
        assert expected in entries, f"missing {expected!r} in .gitignore"


def test_gitignore_covers_secrets() -> None:
    entries = _normalized_entries()
    assert ".env" in entries
    assert "*.sqlite" in entries or "*.db" in entries


def test_gitignore_excludes_env_example() -> None:
    # NOTE: We use the non-verbose form of `git check-ignore` rather than
    # `-v`. With `-v`, git exits 0 whenever *any* pattern in .gitignore
    # matches the path -- including negation patterns like `!.env.example`.
    # That makes `-v` exit 0 even when the path is explicitly un-ignored,
    # so it cannot distinguish "ignored" from "matched a `!` pattern".
    # The non-verbose exit code is 0 only when the path would actually be
    # excluded, which is what we want to assert here.
    result = subprocess.run(
        ["git", "check-ignore", ".env.example"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, ".env.example must not be ignored"


def test_gitignore_would_ignore_dotenv() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "-v", ".env"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
