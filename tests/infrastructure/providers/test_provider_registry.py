"""File-level contract tests for ``ProviderRegistry``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_cli_coder_with_rag.infrastructure.providers import (
    NoActiveProviderError,
    ProviderConfig,
    ProviderRegistry,
    UnknownProviderError,
)


def test_registry_seeds_five_providers_when_missing(tmp_path: Path) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    ids = [pid for pid, _ in registry.list()]
    assert ids == ["anthropic", "minimax", "mistral", "nvidia", "openai"]
    for _, config in registry.list():
        assert config.api_key.get_secret_value() == ""
    data = json.loads((tmp_path / "providers.json").read_text())
    assert data["active_provider_id"] == ""


def test_registry_seeding_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "providers.json"
    ProviderRegistry(path)
    first = path.read_text()
    ProviderRegistry(path)
    assert path.read_text() == first


def test_registry_get_known_id(tmp_path: Path) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    assert registry.get("openai").adapter == "openai"


def test_registry_get_unknown_raises(tmp_path: Path) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    with pytest.raises(UnknownProviderError):
        registry.get("nope")


def test_registry_active_empty_raises(tmp_path: Path) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    with pytest.raises(NoActiveProviderError):
        registry.active()


def test_registry_set_active_persists(tmp_path: Path) -> None:
    path = tmp_path / "providers.json"
    registry = ProviderRegistry(path)
    registry.set_active("openai")
    assert json.loads(path.read_text())["active_provider_id"] == "openai"
    assert ProviderRegistry(path).active().default_model == "gpt-4o-mini"


def test_registry_set_active_unknown_raises(tmp_path: Path) -> None:
    path = tmp_path / "providers.json"
    registry = ProviderRegistry(path)
    before = path.read_text()
    with pytest.raises(UnknownProviderError):
        registry.set_active("nope")
    assert path.read_text() == before


def test_registry_list_sorted(tmp_path: Path) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    assert [pid for pid, _ in registry.list()] == [
        "anthropic",
        "minimax",
        "mistral",
        "nvidia",
        "openai",
    ]


def test_registry_upsert_merges_single_entry(tmp_path: Path) -> None:
    path = tmp_path / "providers.json"
    registry = ProviderRegistry(path)
    original = registry.get("mistral")
    registry.upsert(
        "openai",
        ProviderConfig(
            adapter="openai", base_url="https://api.openai.com/v1", default_model="gpt-4o"
        ),
    )
    assert registry.get("openai").default_model == "gpt-4o"
    assert registry.get("mistral") == original
    # Re-read from disk to confirm persistence of the other entries.
    reloaded = ProviderRegistry(path)
    assert reloaded.get("mistral") == original
    assert reloaded.get("openai").default_model == "gpt-4o"


def test_registry_upsert_creates_new_entry(tmp_path: Path) -> None:
    path = tmp_path / "providers.json"
    registry = ProviderRegistry(path)
    registry.upsert(
        "myproxy",
        ProviderConfig(adapter="openai", base_url="https://x", default_model="m"),
    )
    data = json.loads(path.read_text())
    assert "myproxy" in data["providers"]
    assert len(data["providers"]) == 6


def test_registry_remove_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "providers.json"
    registry = ProviderRegistry(path)
    registry.remove("nope")  # no-op, no write
    registry.remove("minimax")
    assert [pid for pid, _ in registry.list()] == ["anthropic", "mistral", "nvidia", "openai"]
    registry.remove("minimax")  # idempotent


def test_registry_atomic_write_does_not_corrupt_on_failure(tmp_path: Path, mocker) -> None:
    path = tmp_path / "providers.json"
    registry = ProviderRegistry(path)
    before = path.read_text()
    mocker.patch.object(Path, "write_text", side_effect=OSError("disk full"))
    with pytest.raises(OSError):
        registry.upsert(
            "x", ProviderConfig(adapter="openai", base_url="https://x", default_model="m")
        )
    assert path.read_text() == before


def test_registry_default_providers_have_https_base_urls(tmp_path: Path) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    for _, config in registry.list():
        assert config.base_url.startswith("https://")


def test_registry_default_provider_anthropic_targets_official_endpoint(tmp_path: Path) -> None:
    registry = ProviderRegistry(tmp_path / "providers.json")
    assert registry.get("anthropic").base_url == "https://api.anthropic.com"


def test_registry_was_seeded_true_on_first_run(tmp_path: Path) -> None:
    assert ProviderRegistry(tmp_path / "providers.json").was_seeded is True


def test_registry_was_seeded_false_on_second_run(tmp_path: Path) -> None:
    path = tmp_path / "providers.json"
    ProviderRegistry(path)
    assert ProviderRegistry(path).was_seeded is False
