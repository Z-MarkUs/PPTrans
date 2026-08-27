"""Faithful full-deck rendering through isolated LibreOffice and PDF rasterization."""

from __future__ import annotations

import importlib
import importlib.util
import math
import os
import re
import shutil

# Required for a fixed argv with shell=False and the sanitized environment built below.
import subprocess  # nosec B404
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path

from pptrans.domain.errors import InvalidPresentationError
from pptrans.ooxml.package import (
    discover_slide_parts,
    open_package,
    validate_archive_payloads,
)

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
    sha256_file,
    validate_png,
    validate_render_request,
)

PDF_EXPORT_FILTER = (
    'pdf:impress_pdf_Export:{"ExportHiddenSlides":{"type":"boolean","value":"true"}}'
)

_SECRET_ENVIRONMENT_KEY = re.compile(
    r"(?:api[_-]?key|authorization|password|secret|token|credential)", re.IGNORECASE
)

SlideCounter = Callable[[Path], int]
Linker = Callable[[Path, Path], None]


def _sanitized_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Avoid exposing API credentials to the document-conversion child process."""

    values = source if source is not None else os.environ
    return {key: value for key, value in values.items() if not _SECRET_ENVIRONMENT_KEY.search(key)}


def _validate_page_count(page_count: int, max_pages: int) -> None:
    if page_count < 1:
        raise RenderError("LibreOffice produced an empty PDF")
    if page_count > max_pages:
        raise RenderError("rendered PDF exceeds the configured page limit")


def _add_page_pixels(current: int, width: int, height: int, maximum: int) -> int:
    total = current + width * height
    if total > maximum:
        raise RenderError("rendered PDF exceeds the configured total-pixel limit")
    return total


def _count_pptx_slides(source: Path) -> int:
    """Count presentation-ordered slides through the defensive OOXML reader."""

    try:
        with open_package(source) as archive:
            validate_archive_payloads(archive)
            count = len(discover_slide_parts(archive))
    except InvalidPresentationError as exc:
        raise RenderError(f"could not inspect PPTX slide count safely: {exc}") from exc
    if count < 1:
        raise RenderError("PPTX contains no slides to render")
    return count


def _remove_published_link(staged_output: Path, final_output: Path) -> str | None:
    """Remove only a final path that is still the hard link this renderer created."""

    try:
        if final_output.exists() and final_output.samefile(staged_output):
            final_output.unlink()
    except OSError:
        return final_output.name
    return None


class PyMuPdfRasterizer:
    """Optional high-fidelity PDF rasterizer provided by the ``review`` extra."""

    @staticmethod
    def available() -> bool:
        return importlib.util.find_spec("fitz") is not None

    def rasterize(
        self,
        pdf_path: Path,
        output_dir: Path,
        *,
        dpi: int,
        max_pages: int,
        max_total_pixels: int,
    ) -> tuple[Path, ...]:
        if not self.available():
            raise RendererUnavailable(
                "PyMuPDF is required to rasterize LibreOffice PDF output; install pptrans[review]"
            )
        fitz = importlib.import_module("fitz")

        output_dir.mkdir(parents=True, exist_ok=True)
        rendered: list[Path] = []
        total_pixels = 0
        scale = dpi / 72.0
        try:
            with fitz.open(pdf_path) as document:
                _validate_page_count(document.page_count, max_pages)
                for index, page in enumerate(document):
                    width = max(1, math.ceil(page.rect.width * scale))
                    height = max(1, math.ceil(page.rect.height * scale))
                    total_pixels = _add_page_pixels(total_pixels, width, height, max_total_pixels)
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                    output_path = output_dir / f"page-{index + 1:04d}.png"
                    pixmap.save(str(output_path))
                    rendered.append(output_path)
        except RenderError:
            raise
        except Exception as exc:
            raise RenderError(f"could not rasterize LibreOffice PDF output: {exc}") from exc
        return tuple(rendered)


Runner = Callable[..., subprocess.CompletedProcess[str]]


class LibreOfficeRenderer(SlideRenderer):
    """Render a complete deck and publish verified PNGs without clobbering files.

    PPTX page counts are checked through PPTrans's defensive OOXML reader. Final images
    are created as same-filesystem hard links, so unsupported filesystems fail closed.
    """

    name = "libreoffice"
    fidelity = RenderFidelity.HIGH

    def __init__(
        self,
        *,
        executable: Path | None = None,
        rasterizer: PdfRasterizer | None = None,
        runner: Runner = subprocess.run,
        environment: Mapping[str, str] | None = None,
        slide_counter: SlideCounter = _count_pptx_slides,
        linker: Linker = os.link,
    ) -> None:
        self._explicit_executable = executable
        self._rasterizer = rasterizer or PyMuPdfRasterizer()
        self._runner = runner
        self._environment = environment
        self._slide_counter = slide_counter
        self._linker = linker

    def _find_executable(self) -> Path | None:
        if self._explicit_executable is not None:
            candidate = self._explicit_executable.resolve()
            return candidate if candidate.is_file() else None
        discovered = shutil.which("soffice") or shutil.which("libreoffice")
        return Path(discovered).resolve() if discovered else None

    def availability(self) -> RendererAvailability:
        executable = self._find_executable()
        if executable is None:
            return RendererAvailability(
                available=False, reason="LibreOffice executable was not found"
            )
        available_method = getattr(self._rasterizer, "available", None)
        if callable(available_method) and not available_method():
            return RendererAvailability(
                available=False,
                reason="a PDF rasterizer is not installed",
                executable=executable,
            )
        return RendererAvailability(
            available=True,
            reason="LibreOffice and PDF rasterizer are available",
            executable=executable,
        )

    def _convert_to_pdf(
        self,
        *,
        executable: Path,
        source: Path,
        conversion_dir: Path,
        profile_dir: Path,
        temp_root: Path,
        request: RenderRequest,
    ) -> Path:
        command = [
            str(executable),
            "--headless",
            "--nologo",
            "--nodefault",
            "--norestore",
            "--nolockcheck",
            f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
            "--convert-to",
            PDF_EXPORT_FILTER,
            "--outdir",
            str(conversion_dir),
            str(source),
        ]
        try:
            completed = self._runner(
                command,
                capture_output=True,
                text=True,
                timeout=float(request.timeout_seconds),
                check=False,
                shell=False,
                cwd=str(temp_root),
                env=_sanitized_environment(self._environment),
            )
        except subprocess.TimeoutExpired as exc:
            raise RenderError("LibreOffice rendering timed out") from exc
        except OSError as exc:
            raise RenderError(f"LibreOffice could not start: {exc}") from exc

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip().replace("\n", " ")[:500]
            raise RenderError(
                f"LibreOffice conversion failed with status {completed.returncode}: {stderr}"
            )

        expected_pdf = conversion_dir / f"{source.stem}.pdf"
        if not expected_pdf.is_file():
            candidates = tuple(conversion_dir.glob("*.pdf"))
            if len(candidates) != 1:
                raise RenderError("LibreOffice did not produce exactly one PDF")
            expected_pdf = candidates[0]
        if expected_pdf.is_symlink() or expected_pdf.stat().st_size > request.max_pdf_bytes:
            raise RenderError("LibreOffice PDF output violates the configured size boundary")
        return expected_pdf

    @staticmethod
    def _validate_images(
        image_paths: tuple[Path, ...],
        request: RenderRequest,
        *,
        expected_slide_count: int | None = None,
    ) -> list[tuple[Path, int, int]]:
        if not image_paths:
            raise RenderError("PDF rasterizer produced no slide images")
        if len(image_paths) > request.max_pages:
            raise RenderError("PDF rasterizer exceeded the configured page limit")
        if expected_slide_count is not None and len(image_paths) != expected_slide_count:
            raise RenderError(
                "PDF rasterizer page count does not match the source PPTX slide count "
                f"({len(image_paths)} != {expected_slide_count})"
            )
        validated: list[tuple[Path, int, int]] = []
        total_pixels = 0
        for image_path in image_paths:
            width, height = validate_png(image_path, max_pixels=request.max_total_pixels)
            total_pixels += width * height
            if total_pixels > request.max_total_pixels:
                raise RenderError("slide images exceed the configured total-pixel limit")
            validated.append((image_path, width, height))
        return validated

    def _publish_images(
        self,
        *,
        validated: list[tuple[Path, int, int]],
        temp_root: Path,
        output_dir: Path,
        safe_stem: str,
        source_digest: str,
    ) -> tuple[RenderedSlide, ...]:
        """Stage all images, then no-clobber link them with rollback on failure."""

        staged: list[tuple[Path, Path, RenderedSlide]] = []
        for slide_number, (image_path, width, height) in enumerate(validated, start=1):
            output_name = f"{safe_stem}-{source_digest[:12]}-slide-{slide_number:04d}.png"
            staged_output = temp_root / output_name
            shutil.copyfile(image_path, staged_output)
            final_output = output_dir / output_name
            staged.append(
                (
                    staged_output,
                    final_output,
                    RenderedSlide(
                        slide_number=slide_number,
                        image_path=final_output,
                        width=width,
                        height=height,
                        sha256=sha256_file(staged_output),
                    ),
                )
            )

        collisions = [final for _staged, final, _slide in staged if os.path.lexists(final)]
        if collisions:
            names = ", ".join(path.name for path in collisions)
            raise RenderError(f"render output already exists; refusing to overwrite: {names}")

        published: list[tuple[Path, Path]] = []
        try:
            for staged_output, final_output, _slide in staged:
                published.append((staged_output, final_output))
                self._linker(staged_output, final_output)
        except OSError as exc:
            cleanup_failures = [
                failure
                for staged_output, final_output in reversed(published)
                if (failure := _remove_published_link(staged_output, final_output)) is not None
            ]
            if cleanup_failures:
                names = ", ".join(cleanup_failures)
                raise RenderError(
                    "safe render publication failed and cleanup could not remove: " + names
                ) from exc
            if isinstance(exc, FileExistsError):
                raise RenderError(
                    "render output appeared during publication; no files published"
                ) from exc
            raise RenderError(
                "filesystem does not support safe no-clobber render publication; no files published"
            ) from exc

        return tuple(slide for _staged, _final, slide in staged)

    def _expected_slide_count(self, source: Path, request: RenderRequest) -> int | None:
        if source.suffix.lower() != ".pptx":
            return None
        try:
            count = self._slide_counter(source)
        except RenderError:
            raise
        except Exception as exc:
            raise RenderError(f"could not inspect PPTX slide count safely: {exc}") from exc
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise RenderError("PPTX slide counter returned an invalid slide count")
        if count > request.max_pages:
            raise RenderError("PPTX slide count exceeds the configured page limit")
        return count

    def render(self, request: RenderRequest) -> RenderResult:
        source, output_dir = validate_render_request(request)
        availability = self.availability()
        if not availability.available or availability.executable is None:
            raise RendererUnavailable(availability.reason)

        output_dir.mkdir(parents=True, exist_ok=True)
        if output_dir.is_symlink() or not output_dir.is_dir():
            raise UnsafeRenderInput("render output directory changed during validation")
        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", source.stem).strip(".-") or "deck"

        with tempfile.TemporaryDirectory(prefix=".pptrans-render-", dir=output_dir) as temp_name:
            temp_root = Path(temp_name)
            conversion_dir = temp_root / "converted"
            profile_dir = temp_root / "profile"
            raster_dir = temp_root / "raster"
            staged_source = temp_root / source.name
            conversion_dir.mkdir()
            profile_dir.mkdir()
            raster_dir.mkdir()
            try:
                with source.open("rb") as source_handle, staged_source.open("xb") as staged_handle:
                    shutil.copyfileobj(source_handle, staged_handle, length=1024 * 1024)
            except OSError as exc:
                raise RenderError(f"could not snapshot render input safely: {exc}") from exc
            if staged_source.stat().st_size > request.max_input_bytes:
                raise UnsafeRenderInput("render input exceeds the configured byte limit")

            # Hash, inspect, and render one private snapshot so a concurrent source-path
            # replacement cannot make the reported digest describe a different deck.
            source_digest = sha256_file(staged_source)
            expected_slide_count = self._expected_slide_count(staged_source, request)

            expected_pdf = self._convert_to_pdf(
                executable=availability.executable,
                source=staged_source,
                conversion_dir=conversion_dir,
                profile_dir=profile_dir,
                temp_root=temp_root,
                request=request,
            )
            image_paths = self._rasterizer.rasterize(
                expected_pdf,
                raster_dir,
                dpi=request.dpi,
                max_pages=request.max_pages,
                max_total_pixels=request.max_total_pixels,
            )
            validated = self._validate_images(
                image_paths,
                request,
                expected_slide_count=expected_slide_count,
            )
            slides = self._publish_images(
                validated=validated,
                temp_root=temp_root,
                output_dir=output_dir,
                safe_stem=safe_stem,
                source_digest=source_digest,
            )

        return RenderResult(
            backend=self.name,
            fidelity=self.fidelity,
            source_sha256=source_digest,
            slides=slides,
        )


__all__ = ["LibreOfficeRenderer", "PyMuPdfRasterizer"]
