"""Domain errors raised by the PPTrans v2 core."""

from __future__ import annotations


class PPTransError(Exception):
    """Base class for expected PPTrans failures."""


class InvalidPresentationError(PPTransError):
    """Raised when an input is not a safe, supported PPTX package."""


class SourceChangedError(PPTransError):
    """Raised when a deck changed after its translation plan was created."""


class LocatorResolutionError(PPTransError):
    """Raised when a planned paragraph cannot be resolved in the source deck."""


class PatchValidationError(PPTransError):
    """Raised when translations do not match their planned text spans."""


class VerificationError(PPTransError):
    """Raised when a generated deck violates structural preservation rules."""
