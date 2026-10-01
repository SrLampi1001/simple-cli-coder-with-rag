"""Tests for the ``coder`` CLI entry point."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    pass


def _populate_data_dir(data_dir: Path) -> tuple[Path, Path]:
    """Create ``db.sqlite`` and ``sessions/a.jsonl`` inside ``data_dir``.

    Returns the two paths so tests can assert on them.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir = data_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    db = data_dir / "db.sqlite"
    db.write_text("not-a-real-sqlite-file-just-a-stub")
    session = sessions_dir / "a.jsonl"
    session.write_text('{"msg": "hi"}\n')
    return db, session


@pytest.fixture
def isolated_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point ``LocalPaths`` at a fresh temp directory."""
    from simple_cli_coder_with_rag.infrastructure import local_paths

    monkeypatch.setattr(local_paths.LocalPaths, "data_dir", classmethod(lambda cls: tmp_path))
    return tmp_path


def test_cli_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    from simple_cli_coder_with_rag import cli

    exit_code = cli.main(["--version"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "0.1.0" in captured.out


def test_cli_help_flag(capsys: pytest.CaptureFixture[str]) -> None:
    from simple_cli_coder_with_rag import cli

    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])

    # argparse exits with 0 on --help.
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "usage" in captured.out.lower()


def test_cli_runs_repl_when_no_args(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from simple_cli_coder_with_rag import cli
    from simple_cli_coder_with_rag.presentation import repl as repl_module

    called = {"n": 0}

    def fake_run(self: object) -> None:
        called["n"] += 1

    monkeypatch.setattr(repl_module.Repl, "run", fake_run)

    # The REPL must be a no-op for this test; the prompt must not block.
    # We mock ``PromptSession.prompt`` to raise EOF immediately so the loop
    # terminates.
    from prompt_toolkit import PromptSession

    def raise_eof(self: object, *args: object, **kwargs: object) -> str:
        raise EOFError

    monkeypatch.setattr(PromptSession, "prompt", raise_eof)

    exit_code = cli.main([])

    assert exit_code == 0
    assert called["n"] == 1


def test_cli_reset_deletes_data_on_yes(
    isolated_data_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, session = _populate_data_dir(isolated_data_dir)
    assert db.is_file()
    assert session.is_file()

    monkeypatch.setattr("sys.stdin", _FakeStdin(["y\n"]))
    from simple_cli_coder_with_rag import cli

    exit_code = cli.main(["--reset"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Reset complete." in captured.out
    assert not db.exists(), "db.sqlite should be removed"
    assert not session.exists(), "sessions/a.jsonl should be removed"


def test_cli_reset_aborts_on_default_input(
    isolated_data_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, session = _populate_data_dir(isolated_data_dir)

    monkeypatch.setattr("sys.stdin", _FakeStdin(["\n"]))
    from simple_cli_coder_with_rag import cli

    exit_code = cli.main(["--reset"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Aborted." in captured.out
    assert db.is_file()
    assert session.is_file()


def test_cli_reset_aborts_on_uppercase_y(
    isolated_data_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, session = _populate_data_dir(isolated_data_dir)

    monkeypatch.setattr("sys.stdin", _FakeStdin(["Y\n"]))
    from simple_cli_coder_with_rag import cli

    exit_code = cli.main(["--reset"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Aborted." in captured.out
    assert db.is_file()
    assert session.is_file()


def test_cli_reset_prints_paths_before_prompt(
    isolated_data_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, _session = _populate_data_dir(isolated_data_dir)

    monkeypatch.setattr("sys.stdin", _FakeStdin(["y\n"]))
    from simple_cli_coder_with_rag import cli

    cli.main(["--reset"])

    captured = capsys.readouterr().out
    data_dir_line = next(
        (line for line in captured.splitlines() if str(isolated_data_dir) in line),
        None,
    )
    assert data_dir_line is not None, "data dir path missing from output"

    # The data-dir line must appear before the prompt line.
    prompt_line_idx = next(i for i, line in enumerate(captured.splitlines()) if "Continue?" in line)
    data_dir_line_idx = captured.splitlines().index(data_dir_line)
    assert data_dir_line_idx < prompt_line_idx

    # At least one concrete filename is shown before the prompt.
    file_lines_before_prompt = [
        line for line in captured.splitlines()[:prompt_line_idx] if db.name in line
    ]
    assert file_lines_before_prompt, "no filename printed before the prompt"


def test_cli_reset_handles_missing_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from simple_cli_coder_with_rag.infrastructure import local_paths

    missing = tmp_path / "does-not-exist"
    monkeypatch.setattr(local_paths.LocalPaths, "data_dir", classmethod(lambda cls: missing))

    monkeypatch.setattr("sys.stdin", _FakeStdin(["y\n"]))
    from simple_cli_coder_with_rag import cli

    exit_code = cli.main(["--reset"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Reset complete." in captured.out


def test_cli_reset_skips_repl_and_logger(
    isolated_data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _populate_data_dir(isolated_data_dir)

    from loguru import logger as _logger

    from simple_cli_coder_with_rag.presentation import repl as repl_module

    repl_run_calls = {"n": 0}
    logger_add_calls = {"n": 0}

    def fake_repl_run(self: object) -> None:
        repl_run_calls["n"] += 1

    def fake_logger_add(*_args: object, **_kwargs: object) -> int:
        logger_add_calls["n"] += 1
        return 1

    monkeypatch.setattr(repl_module.Repl, "run", fake_repl_run)
    monkeypatch.setattr(_logger, "add", fake_logger_add)
    monkeypatch.setattr("sys.stdin", _FakeStdin(["y\n"]))

    from simple_cli_coder_with_rag import cli

    exit_code = cli.main(["--reset"])

    assert exit_code == 0
    assert repl_run_calls["n"] == 0, "Repl.run was called on --reset path"
    assert logger_add_calls["n"] == 0, "logger.add was called on --reset path"


def test_cli_reset_wins_over_version(
    isolated_data_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, session = _populate_data_dir(isolated_data_dir)

    monkeypatch.setattr("sys.stdin", _FakeStdin(["y\n"]))
    from simple_cli_coder_with_rag import cli

    exit_code = cli.main(["--reset", "--version"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Reset complete." in captured.out
    assert "0.1.0" not in captured.out, "version flag must not fire when --reset wins"
    assert not session.exists()


class _FakeStdin:
    """Minimal stdin stand-in that yields pre-canned lines."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)

    def readline(self) -> str:
        if not self._lines:
            return ""
        return self._lines.pop(0)
