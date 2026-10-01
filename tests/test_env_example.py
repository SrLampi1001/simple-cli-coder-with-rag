from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = ROOT / ".env.example"


def test_env_example_exists() -> None:
    assert ENV_EXAMPLE.is_file()


def test_env_example_has_anthropic_key() -> None:
    assert "ANTHROPIC_API_KEY=" in ENV_EXAMPLE.read_text()


def test_env_example_has_no_real_secret() -> None:
    allowed_values = {"", "claude-haiku-4-5", "claude-sonnet-4-5"}
    for line in ENV_EXAMPLE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        _, _, value = line.partition("=")
        assert value.strip() in allowed_values


def test_env_example_does_not_override_actual_env() -> None:
    class _Settings(BaseSettings):
        model_config = SettingsConfigDict(env_file=str(ENV_EXAMPLE), extra="ignore")
        anthropic_api_key: str = ""
        compactor_model: str = "claude-haiku-4-5"
        chat_model: str = "claude-sonnet-4-5"

    settings = _Settings()
    assert settings.anthropic_api_key == ""
    assert settings.compactor_model == "claude-haiku-4-5"
    assert settings.chat_model == "claude-sonnet-4-5"
