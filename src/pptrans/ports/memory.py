"""Translation-memory contract."""

from __future__ import annotations

from typing import Protocol

from pptrans.domain.models import TranslatedSpan


class TranslationMemory(Protocol):
    """Cache exact, schema-validated translations by a deterministic key."""

    def get(self, key: str) -> tuple[TranslatedSpan, ...] | None:
        """Return a cached translation, or ``None`` on a miss."""

    def put(self, key: str, spans: tuple[TranslatedSpan, ...]) -> None:
        """Store a validated translation."""


__all__ = ["TranslationMemory"]
