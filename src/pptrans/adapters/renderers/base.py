"""Contracts and shared validation for faithful slide renderers."""

from __future__ import annotations

import hashlib
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from PIL import Image


class RenderFidelity(str, Enum):
    HIGH = "high"
    STRUCTURAL_ONLY = "structural_only"


class RenderError(RuntimeError):
    """A presentation could not be rendered or its output was unsafe."""


class RendererUnavailable(RenderError):  # noqa: N818 - reads naturally at call sites
    """The requested faithful rendering backend is not installed."""


class UnsafeRenderInput(RenderError):  # noqa: N818 - reads naturally at call sites
    """The render request violates an input or resource boundary."""


@dataclass(frozen=True, slots=True)
class RendererAvailability:
    available: bool
    reason: str
    executable: Path | None = None


@dataclass(frozen=True, slots=True)
class RenderRequest:
    presentation_path: Path
    output_dir: Path
    dpi: int = 144
    timeout_seconds: float = 90.0
    max_pages: int = 250
    max_total_pixels: int = 500_000_000
    max_input_bytes: int = 500 * 1024 * 1024
    max_pdf_bytes: int = 500 * 1024 * 1024
    allow_legacy_ppt: bool = False


MAX_RENDER_DPI = 600
MAX_RENDER_TIMEOUT_SECONDS = 600.0


@dataclass(frozen=True, slots=True)
class RenderedSlide:
    slide_number: int
    image_path: Path
    width: int
    height: int
    sha256: str


@dataclass(frozen=True, slots=True)
class RenderResult:
    backend: str
    fidelity: RenderFidelity
    source_sha256: str
    slides: tuple[RenderedSlide, ...]
    warnings: tuple[str, ...] = ()


class PdfRasterizer(Protocol):
    def rasterize(
        self,
        pdf_path: Path,
        output_dir: Path,
        *,
        dpi: int,
        max_pages: int,
        max_total_pixels: int,
    ) -> tuple[Path, ...]: ...


class SlideRenderer(ABC):
    name: str
    fidelity: RenderFidelity

    @abstractmethod
    def availability(self) -> RendererAvailability:
        """Return a diagnostic without running the renderer."""

    @abstractmethod
    def render(self, request: RenderRequest) -> RenderResult:
        """Render every static slide without overwriting an existing render."""


def validate_render_request(request: RenderRequest) -> tuple[Path, Path]:
    """Validate local paths and resource limits before opening a document."""

    if not isinstance(request.presentation_path, Path) or not isinstance(request.output_dir, Path):
        raise TypeError("presentation_path and output_dir must be pathlib.Path values")
    if request.presentation_path.is_symlink():
        raise UnsafeRenderInput("symlinked presentation inputs are not accepted")
    source = request.presentation_path.resolve()
    if not source.is_file():
        raise UnsafeRenderInput(f"presentation is not a regular file: {source}")
    allowed_suffixes = {".pptx"}
    if request.allow_legacy_ppt:
        allowed_suffixes.add(".ppt")
    if source.suffix.lower() not in allowed_suffixes:
        raise UnsafeRenderInput(
            "only .pptx filename extensions are accepted by default; "
            "legacy .ppt requires allow_legacy_ppt=True"
        )
    if source.stat().st_size > request.max_input_bytes:
        raise UnsafeRenderInput("presentation exceeds the configured input-size limit")

    if request.output_dir.exists() and request.output_dir.is_symlink():
        raise UnsafeRenderInput("symlinked render output directories are not accepted")
    if request.output_dir.exists() and not request.output_dir.is_dir():
        raise UnsafeRenderInput("render output path must be a directory")
    output_dir = request.output_dir.resolve()

    integer_limits = {
        "dpi": request.dpi,
        "max_pages": request.max_pages,
        "max_total_pixels": request.max_total_pixels,
        "max_input_bytes": request.max_input_bytes,
        "max_pdf_bytes": request.max_pdf_bytes,
    }
    for name, value in integer_limits.items():
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise UnsafeRenderInput(f"{name} must be a positive integer")
    if request.dpi > MAX_RENDER_DPI:
        raise UnsafeRenderInput(f"dpi may not exceed {MAX_RENDER_DPI}")
    if (
        isinstance(request.timeout_seconds, bool)
        or not isinstance(request.timeout_seconds, (int, float))
        or not 0 < float(request.timeout_seconds) <= MAX_RENDER_TIMEOUT_SECONDS
    ):
        raise UnsafeRenderInput("timeout_seconds must be greater than zero and at most 600")
    return source, output_dir


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_png(path: Path, *, max_pixels: int) -> tuple[int, int]:
    """Decode a PNG under Pillow's bomb guard and return its dimensions."""

    if path.is_symlink() or not path.is_file():
        raise RenderError(f"rasterizer did not produce a regular image: {path}")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                image_format = image.format
                width, height = image.size
                image.verify()
    except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise RenderError(f"invalid rendered PNG '{path.name}': {exc}") from exc
    if image_format != "PNG":
        raise RenderError(f"rendered page is not PNG: {path.name}")
    if width <= 0 or height <= 0 or width * height > max_pixels:
        raise RenderError("rendered page dimensions exceed the configured limit")
    return width, height


__all__ = [
    "PdfRasterizer",
    "RenderError",
    "RenderFidelity",
    "RenderRequest",
    "RenderResult",
    "RenderedSlide",
    "RendererAvailability",
    "RendererUnavailable",
    "SlideRenderer",
    "UnsafeRenderInput",
    "sha256_file",
    "validate_png",
    "validate_render_request",
]
