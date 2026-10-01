from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = ROOT / ".env.example"


def test_env_example_exists() -> None:
    assert ENV_EXAMPLE.is_file()


def test_env_example_has_provider_keys() -> None:
    text = ENV_EXAMPLE.read_text()
    for key in ("NVIDIA_API_KEY=", "MISTRAL_API_KEY=", "MINIMAX_API_KEY="):
        assert key in text, f"{key} missing from .env.example"


def test_env_example_has_no_real_secret() -> None:
    allowed_values = {""}
    for line in ENV_EXAMPLE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        _, _, value = line.partition("=")
        assert value.strip() in allowed_values, f"unexpected value in .env.example: {value!r}"


def test_env_example_does_not_override_actual_env() -> None:
    class _Settings(BaseSettings):
        model_config = SettingsConfigDict(env_file=str(ENV_EXAMPLE), extra="ignore")
        nvidia_api_key: str = ""
        mistral_api_key: str = ""
        minimax_api_key: str = ""

    settings = _Settings()
    assert settings.nvidia_api_key == ""
    assert settings.mistral_api_key == ""
    assert settings.minimax_api_key == ""
