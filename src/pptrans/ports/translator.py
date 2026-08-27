"""Provider-neutral translation contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pptrans.domain.models import TranslatedSpan, TranslationUnit


@dataclass(frozen=True, slots=True)
class GlossaryTerm:
    """One source-to-target terminology constraint."""

    source: str
    target: str
    note: str | None = None


@dataclass(frozen=True, slots=True)
class TranslationBatchRequest:
    """A bounded batch sent to one translation provider."""

    units: tuple[TranslationUnit, ...]
    source_lang: str
    target_lang: str
    glossary: tuple[GlossaryTerm, ...] = ()
    style: str | None = None


@dataclass(frozen=True, slots=True)
class UnitTranslation:
    """A provider result for one translation unit."""

    unit_id: str
    spans: tuple[TranslatedSpan, ...]


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    """Normalized token accounting when the provider exposes it."""

    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class TranslationBatchResult:
    """Validated provider-independent batch output."""

    translations: tuple[UnitTranslation, ...]
    usage: ProviderUsage = ProviderUsage()


class Translator(Protocol):
    """Translate a batch without depending on an SDK response type."""

    provider: str
    model: str

    def translate(self, request: TranslationBatchRequest) -> TranslationBatchResult:
        """Translate every requested unit or raise an explicit error."""


__all__ = [
    "GlossaryTerm",
    "ProviderUsage",
    "TranslationBatchRequest",
    "TranslationBatchResult",
    "Translator",
    "UnitTranslation",
]
