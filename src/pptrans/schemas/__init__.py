"""Strict schemas for all untrusted model output."""

from .translation import (
    TranslatedSpanPayload,
    TranslationBatchPayload,
    UnitTranslationPayload,
)

__all__ = [
    "TranslatedSpanPayload",
    "TranslationBatchPayload",
    "UnitTranslationPayload",
]
