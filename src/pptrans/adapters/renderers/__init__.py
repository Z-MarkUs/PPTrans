"""Faithful presentation-rendering adapters."""

from .base import (
    PdfRasterizer,
    RenderedSlide,
    RendererAvailability,
    RenderError,
    RendererUnavailable,
    RenderFidelity,
    RenderRequest,
    RenderResult,
    SlideRenderer,
    UnsafeRenderInput,
)
from .libreoffice import LibreOfficeRenderer, PyMuPdfRasterizer

__all__ = [
    "LibreOfficeRenderer",
    "PdfRasterizer",
    "PyMuPdfRasterizer",
    "RenderError",
    "RenderFidelity",
    "RenderRequest",
    "RenderResult",
    "RenderedSlide",
    "RendererAvailability",
    "RendererUnavailable",
    "SlideRenderer",
    "UnsafeRenderInput",
]
