"""Strict schemas for untrusted provider translation output."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from pptrans.domain.models import (
    MAX_TRANSLATABLE_SPANS_PER_UNIT,
    MAX_TRANSLATED_TEXT_CHARACTERS,
)


class TranslatedSpanPayload(BaseModel):
    """Serialized translation for one planned DrawingML text node."""

    model_config = ConfigDict(extra="forbid", strict=True)

    span_id: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=MAX_TRANSLATED_TEXT_CHARACTERS)


class UnitTranslationPayload(BaseModel):
    """Serialized translation for one planned paragraph."""

    model_config = ConfigDict(extra="forbid", strict=True)

    unit_id: str = Field(min_length=1, max_length=160)
    spans: list[TranslatedSpanPayload] = Field(max_length=MAX_TRANSLATABLE_SPANS_PER_UNIT)


class TranslationBatchPayload(BaseModel):
    """Top-level structured provider response."""

    model_config = ConfigDict(extra="forbid", strict=True)

    translations: list[UnitTranslationPayload] = Field(max_length=2_000)


__all__ = [
    "TranslatedSpanPayload",
    "TranslationBatchPayload",
    "UnitTranslationPayload",
]
