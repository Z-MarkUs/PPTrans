"""Expected failures at provider and orchestration boundaries."""

from __future__ import annotations

from pptrans.domain.errors import PPTransError


class ProviderConfigurationError(PPTransError):
    """Raised when a provider cannot be configured safely."""


class ProviderRequestError(PPTransError):
    """Raised when an SDK request fails."""


class ProviderResponseError(PPTransError):
    """Raised when untrusted provider output fails schema validation."""


class TranslationValidationError(PPTransError):
    """Raised when a provider result does not match the requested batch."""


class TranslationMemoryError(PPTransError):
    """Raised when the local translation memory cannot be accessed safely."""


__all__ = [
    "ProviderConfigurationError",
    "ProviderRequestError",
    "ProviderResponseError",
    "TranslationMemoryError",
    "TranslationValidationError",
]
