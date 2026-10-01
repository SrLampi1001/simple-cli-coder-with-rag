import subprocess


def test_package_imports() -> None:
    import simple_cli_coder_with_rag  # noqa: F401


def test_layers_exist_and_import() -> None:
    import simple_cli_coder_with_rag.application
    import simple_cli_coder_with_rag.domain
    import simple_cli_coder_with_rag.infrastructure
    import simple_cli_coder_with_rag.presentation

    for module in (
        simple_cli_coder_with_rag.application,
        simple_cli_coder_with_rag.domain,
        simple_cli_coder_with_rag.infrastructure,
        simple_cli_coder_with_rag.presentation,
    ):
        assert hasattr(module, "__path__")


def test_cli_script_registered() -> None:
    subprocess.run(["uv", "run", "coder", "--help"], check=True)
