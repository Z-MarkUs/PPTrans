"""Public domain model for the PPTrans v2 core."""

from .errors import (
    InvalidPresentationError,
    LocatorResolutionError,
    PatchValidationError,
    PPTransError,
    SourceChangedError,
    VerificationError,
)
from .models import (
    DeckPlan,
    DeckResult,
    Diagnostic,
    PackageLimits,
    ParagraphLocator,
    PatchSet,
    SpanKind,
    TextContainer,
    TextSpan,
    TranslatedSpan,
    TranslationInput,
    TranslationPatch,
    TranslationUnit,
    VerificationReport,
)

__all__ = [
    "DeckPlan",
    "DeckResult",
    "Diagnostic",
    "InvalidPresentationError",
    "LocatorResolutionError",
    "PPTransError",
    "PackageLimits",
    "ParagraphLocator",
    "PatchSet",
    "PatchValidationError",
    "SourceChangedError",
    "SpanKind",
    "TextContainer",
    "TextSpan",
    "TranslatedSpan",
    "TranslationInput",
    "TranslationPatch",
    "TranslationUnit",
    "VerificationError",
    "VerificationReport",
]
