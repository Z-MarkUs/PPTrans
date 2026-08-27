"""Stable interfaces between PPTrans application code and external systems."""

from .memory import TranslationMemory
from .translator import (
    GlossaryTerm,
    ProviderUsage,
    TranslationBatchRequest,
    TranslationBatchResult,
    Translator,
    UnitTranslation,
)

__all__ = [
    "GlossaryTerm",
    "ProviderUsage",
    "TranslationBatchRequest",
    "TranslationBatchResult",
    "TranslationMemory",
    "Translator",
    "UnitTranslation",
]
