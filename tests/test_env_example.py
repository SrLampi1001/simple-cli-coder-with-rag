from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = ROOT / ".env.example"


def test_env_example_exists() -> None:
    assert ENV_EXAMPLE.is_file()


def test_env_example_has_no_provider_credentials() -> None:
    text = ENV_EXAMPLE.read_text()
    for removed in ("NVIDIA_API_KEY", "MISTRAL_API_KEY", "MINIMAX_API_KEY", "DEFAULT_PROVIDER"):
        assert removed not in text, f"{removed} must be gone from .env.example"
    for removed_model in (
        "NVIDIA_MODEL",
        "MISTRAL_MODEL",
        "MINIMAX_MODEL",
        "CHAT_MODEL",
        "COMPACTOR_MODEL",
    ):
        assert removed_model not in text
    for removed_url in ("NVIDIA_BASE_URL", "MISTRAL_BASE_URL", "MINIMAX_BASE_URL"):
        assert removed_url not in text


def test_env_example_points_at_provider_registry_comment() -> None:
    text = ENV_EXAMPLE.read_text()
    assert "providers.json" in text
    assert "/connect" in text
    assert "docs/providers.md" in text


def test_env_example_keeps_non_provider_knobs() -> None:
    text = ENV_EXAMPLE.read_text()
    for kept in ("CHUNKER_STRATEGY", "VECTOR_STORE", "DB_PATH", "RECALL_TOP_K", "EDITOR_ROOT"):
        assert kept in text


def test_env_example_does_not_override_actual_env() -> None:
    class _Settings(BaseSettings):
        model_config = SettingsConfigDict(env_file=str(ENV_EXAMPLE), extra="ignore")
        chunker_strategy: str = "fixed"
        vector_store: str = "sqlite_vec"

    settings = _Settings()
    assert settings.chunker_strategy == "fixed"
    assert settings.vector_store == "sqlite_vec"
