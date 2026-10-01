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
    """API-key lines must be empty; other config may have defaults.

    DO-02 added non-secret configuration (``DEFAULT_PROVIDER``,
    ``*_MODEL``, ``*_BASE_URL``) to ``.env.example``. Those are not
    secrets, so the rule "only empty values" is too strict. We now
    enforce the empty rule only on the lines that *look* like API keys.
    """
    secret_prefixes = (
        "NVIDIA_API_KEY",
        "MISTRAL_API_KEY",
        "MINIMAX_API_KEY",
    )
    for line in ENV_EXAMPLE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if any(key.startswith(prefix) for prefix in secret_prefixes):
            assert value.strip() == "", f"secret line {key!r} has unexpected value: {value!r}"


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
