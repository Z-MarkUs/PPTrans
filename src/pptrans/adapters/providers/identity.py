"""Offline identity provider for deterministic pipeline verification."""

from __future__ import annotations

from pptrans.domain.models import TranslatedSpan
from pptrans.ports.translator import (
    ProviderUsage,
    TranslationBatchRequest,
    TranslationBatchResult,
    UnitTranslation,
)


class IdentityTranslator:
    """Return source strings unchanged; this is a test adapter, not a translator."""

    provider = "identity"
    model = "identity-v1"

    def translate(self, request: TranslationBatchRequest) -> TranslationBatchResult:
        """Produce a schema-correct offline response in input order."""

        return TranslationBatchResult(
            translations=tuple(
                UnitTranslation(
                    unit_id=unit.id,
                    spans=tuple(
                        TranslatedSpan(span_id=span.id, text=span.source)
                        for span in unit.spans
                        if span.translatable
                    ),
                )
                for unit in request.units
            ),
            usage=ProviderUsage(input_tokens=0, output_tokens=0),
        )


__all__ = ["IdentityTranslator"]
