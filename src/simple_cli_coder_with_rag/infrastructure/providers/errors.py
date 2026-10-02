"""Exceptions raised by the provider registry."""

from __future__ import annotations


class UnknownProviderError(KeyError):
    """Raised when a provider id is not in the registry."""


class NoActiveProviderError(Exception):
    """Raised when ``active()`` is called with no active provider selected."""


__all__ = ["NoActiveProviderError", "UnknownProviderError"]
