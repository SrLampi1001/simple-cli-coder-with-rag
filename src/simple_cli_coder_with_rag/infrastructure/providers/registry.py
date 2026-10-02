"""JSON-backed provider registry (``providers.json``).

Owns all file I/O: first-run seeding of the five pre-populated providers,
atomic writes (temp file + ``Path.replace``), and CRUD over entries.
"""

from __future__ import annotations

from pathlib import Path

from simple_cli_coder_with_rag.infrastructure.providers.default_providers import (
    DEFAULT_PROVIDERS,
)
from simple_cli_coder_with_rag.infrastructure.providers.errors import (
    NoActiveProviderError,
    UnknownProviderError,
)
from simple_cli_coder_with_rag.infrastructure.providers.models import (
    ProviderConfig,
    ProvidersFile,
)


class ProviderRegistry:
    """Read/write access to the on-disk ``providers.json`` document."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        if self._path.exists():
            self._data = ProvidersFile.model_validate_json(self._path.read_text(encoding="utf-8"))
            self.was_seeded = False
        else:
            self._data = ProvidersFile(providers=dict(DEFAULT_PROVIDERS))
            self._write()
            self.was_seeded = True

    @property
    def path(self) -> Path:
        return self._path

    def get(self, provider_id: str) -> ProviderConfig:
        try:
            return self._data.providers[provider_id]
        except KeyError:
            raise UnknownProviderError(provider_id) from None

    def list(self) -> list[tuple[str, ProviderConfig]]:
        return sorted(self._data.providers.items(), key=lambda item: item[0])

    def active(self) -> ProviderConfig:
        if not self._data.active_provider_id:
            raise NoActiveProviderError("no active provider selected")
        return self.get(self._data.active_provider_id)

    @property
    def active_provider_id(self) -> str:
        return self._data.active_provider_id

    def set_active(self, provider_id: str) -> None:
        # Validate first so an unknown id never touches the file.
        self.get(provider_id)
        self._data.active_provider_id = provider_id
        self._write()

    def upsert(self, provider_id: str, config: ProviderConfig) -> None:
        self._data.providers[provider_id] = config
        self._write()

    def remove(self, provider_id: str) -> None:
        if provider_id in self._data.providers:
            del self._data.providers[provider_id]
            self._write()

    def _write(self) -> None:
        tmp = self._path.with_name(self._path.name + ".tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(self._data.model_dump_json(indent=2), encoding="utf-8")
            tmp.replace(self._path)
        finally:
            tmp.unlink(missing_ok=True)


__all__ = ["ProviderRegistry"]
