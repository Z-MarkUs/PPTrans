"""Faithful full-deck rendering through isolated LibreOffice and PDF rasterization."""

from __future__ import annotations

import errno
import importlib
import importlib.util
import math
import os
import re
import shutil
import stat

# Required for a fixed argv with shell=False and the sanitized environment built below.
import subprocess  # nosec B404
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
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
TreeCleaner = Callable[[Path], None]

_CLEANUP_RETRY_DELAYS_SECONDS = (0.05, 0.1, 0.2, 0.4, 0.8)
_CLEANUP_SETTLE_SECONDS = 0.05
_TRANSIENT_CLEANUP_ERRNOS = frozenset({errno.EACCES, errno.EBUSY, errno.ENOTEMPTY, errno.EPERM})
_TRANSIENT_CLEANUP_WINERRORS = frozenset({5, 32, 33, 145})


@dataclass(frozen=True, slots=True)
class _StagedSlide:
    staged_output: Path
    final_output: Path
    rendered_slide: RenderedSlide
    device: int
    inode: int


@dataclass(slots=True)
class _RenderTransaction:
    private_root: Path
    publication_root: Path
    staged: tuple[_StagedSlide, ...] = ()
    private_cleaned: bool = False
    publication_cleaned: bool = False
    published: bool = False


def _is_transient_cleanup_error(error: OSError) -> bool:
    winerror = getattr(error, "winerror", None)
    return error.errno in _TRANSIENT_CLEANUP_ERRNOS or winerror in _TRANSIENT_CLEANUP_WINERRORS


def _remove_tree_with_retry(
    path: Path,
    *,
    remover: Callable[[Path], None] = shutil.rmtree,
    sleeper: Callable[[float], None] = time.sleep,
    retry_delays: tuple[float, ...] = _CLEANUP_RETRY_DELAYS_SECONDS,
    settle_seconds: float = _CLEANUP_SETTLE_SECONDS,
) -> None:
    """Remove a workspace with bounded retries for short-lived Windows file races."""

    attempts = len(retry_delays) + 1
    last_error: OSError | None = None
    for attempt in range(attempts):
        try:
            remover(path)
        except FileNotFoundError:
            pass
        except OSError as error:
            last_error = error
            if not _is_transient_cleanup_error(error) or attempt == attempts - 1:
                raise RenderError(f"could not remove temporary render workspace: {path}") from error
            sleeper(retry_delays[attempt])
            continue

        if settle_seconds > 0:
            sleeper(settle_seconds)
        if not os.path.lexists(path):
            return

        last_error = OSError(
            errno.ENOTEMPTY,
            "temporary render workspace reappeared during cleanup",
            str(path),
        )
        if attempt == attempts - 1:
            raise RenderError(
                f"could not remove temporary render workspace: {path}"
            ) from last_error
        sleeper(retry_delays[attempt])

    raise RenderError(f"could not remove temporary render workspace: {path}") from last_error


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


def _remove_published_link(staged: _StagedSlide) -> str | None:
    """Remove only a final path that still has the staged file's identity."""

    try:
        if not os.path.lexists(staged.final_output):
            return None
        final_stat = staged.final_output.lstat()
        owned = (
            stat.S_ISREG(final_stat.st_mode)
            and final_stat.st_dev == staged.device
            and final_stat.st_ino == staged.inode
        )
        if not owned and os.path.lexists(staged.staged_output):
            owned = staged.final_output.samefile(staged.staged_output)
        if owned:
            staged.final_output.unlink()
    except OSError:
        return staged.final_output.name
    return None


class PyMuPdfRasterizer:
    """Optional high-fidelity PDF rasterizer provided by the ``review`` extra."""

    @staticmethod
    def available() -> bool:
        return importlib.util.find_spec("pymupdf") is not None

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
        pymupdf = importlib.import_module("pymupdf")

        output_dir.mkdir(parents=True, exist_ok=True)
        rendered: list[Path] = []
        total_pixels = 0
        scale = dpi / 72.0
        try:
            with pymupdf.open(pdf_path) as document:
                _validate_page_count(document.page_count, max_pages)
                for index, page in enumerate(document):
                    width = max(1, math.ceil(page.rect.width * scale))
                    height = max(1, math.ceil(page.rect.height * scale))
                    total_pixels = _add_page_pixels(total_pixels, width, height, max_total_pixels)
                    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
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
        tree_cleaner: TreeCleaner = _remove_tree_with_retry,
    ) -> None:
        self._explicit_executable = executable
        self._rasterizer = rasterizer or PyMuPdfRasterizer()
        self._runner = runner
        self._environment = environment
        self._slide_counter = slide_counter
        self._linker = linker
        self._tree_cleaner = tree_cleaner

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

    @staticmethod
    def _stage_images(
        *,
        validated: list[tuple[Path, int, int]],
        publication_root: Path,
        output_dir: Path,
        safe_stem: str,
        source_digest: str,
        max_total_pixels: int,
    ) -> tuple[_StagedSlide, ...]:
        """Copy validated PNGs into same-filesystem publication staging."""

        staged: list[_StagedSlide] = []
        for slide_number, (image_path, width, height) in enumerate(validated, start=1):
            output_name = f"{safe_stem}-{source_digest[:12]}-slide-{slide_number:04d}.png"
            staged_output = publication_root / output_name
            try:
                with (
                    image_path.open("rb") as source_handle,
                    staged_output.open("xb") as staged_handle,
                ):
                    shutil.copyfileobj(source_handle, staged_handle, length=1024 * 1024)
            except OSError as error:
                raise RenderError(
                    f"could not stage rendered slide safely: {output_name}"
                ) from error
            staged_width, staged_height = validate_png(staged_output, max_pixels=max_total_pixels)
            if (staged_width, staged_height) != (width, height):
                raise RenderError("staged render dimensions changed during publication")
            final_output = output_dir / output_name
            staged_stat = staged_output.stat()
            staged.append(
                _StagedSlide(
                    staged_output=staged_output,
                    final_output=final_output,
                    rendered_slide=RenderedSlide(
                        slide_number=slide_number,
                        image_path=final_output,
                        width=staged_width,
                        height=staged_height,
                        sha256=sha256_file(staged_output),
                    ),
                    device=staged_stat.st_dev,
                    inode=staged_stat.st_ino,
                )
            )
        return tuple(staged)

    @staticmethod
    def _rollback_published_images(staged: tuple[_StagedSlide, ...]) -> list[str]:
        return [
            failure
            for item in reversed(staged)
            if (failure := _remove_published_link(item)) is not None
        ]

    def _publish_images(
        self,
        staged: tuple[_StagedSlide, ...],
    ) -> tuple[RenderedSlide, ...]:
        """No-clobber link every staged image with rollback on failure."""

        collisions = [item.final_output for item in staged if os.path.lexists(item.final_output)]
        if collisions:
            names = ", ".join(path.name for path in collisions)
            raise RenderError(f"render output already exists; refusing to overwrite: {names}")

        published: list[_StagedSlide] = []
        try:
            for item in staged:
                published.append(item)
                self._linker(item.staged_output, item.final_output)
        except OSError as exc:
            cleanup_failures = self._rollback_published_images(tuple(published))
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

        return tuple(item.rendered_slide for item in staged)

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

    def _create_transaction(self, output_dir: Path) -> _RenderTransaction:
        private_root: Path | None = None
        try:
            private_root = Path(tempfile.mkdtemp(prefix=".pptrans-render-"))
            publication_root = Path(tempfile.mkdtemp(prefix=".pptrans-publish-", dir=output_dir))
        except OSError as error:
            if private_root is not None:
                try:
                    self._tree_cleaner(private_root)
                except RenderError as cleanup_error:
                    raise RenderError(
                        "could not create render workspaces and private cleanup was incomplete"
                    ) from cleanup_error
            raise RenderError(f"could not create render workspaces safely: {error}") from error
        return _RenderTransaction(
            private_root=private_root,
            publication_root=publication_root,
        )

    @staticmethod
    def _snapshot_source(source: Path, private_root: Path, request: RenderRequest) -> Path:
        staged_source = private_root / f"input{source.suffix.lower()}"
        try:
            with (
                source.open("rb") as source_handle,
                staged_source.open("xb") as staged_handle,
            ):
                shutil.copyfileobj(source_handle, staged_handle, length=1024 * 1024)
            snapshot_size = staged_source.stat().st_size
        except OSError as error:
            raise RenderError(f"could not snapshot render input safely: {error}") from error
        if snapshot_size > request.max_input_bytes:
            raise UnsafeRenderInput("render input exceeds the configured byte limit")
        return staged_source

    def _prepare_staging(
        self,
        *,
        transaction: _RenderTransaction,
        executable: Path,
        source: Path,
        output_dir: Path,
        safe_stem: str,
        request: RenderRequest,
    ) -> tuple[str, tuple[_StagedSlide, ...]]:
        conversion_dir = transaction.private_root / "converted"
        profile_dir = transaction.private_root / "profile"
        raster_dir = transaction.private_root / "raster"
        try:
            conversion_dir.mkdir()
            profile_dir.mkdir()
            raster_dir.mkdir()
        except OSError as error:
            raise RenderError(f"could not initialize render workspace: {error}") from error
        staged_source = self._snapshot_source(source, transaction.private_root, request)

        # Hash, inspect, and render one private snapshot so a concurrent source-path
        # replacement cannot make the reported digest describe a different deck.
        source_digest = sha256_file(staged_source)
        expected_slide_count = self._expected_slide_count(staged_source, request)
        expected_pdf = self._convert_to_pdf(
            executable=executable,
            source=staged_source,
            conversion_dir=conversion_dir,
            profile_dir=profile_dir,
            temp_root=transaction.private_root,
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
        staged = self._stage_images(
            validated=validated,
            publication_root=transaction.publication_root,
            output_dir=output_dir,
            safe_stem=safe_stem,
            source_digest=source_digest,
            max_total_pixels=request.max_total_pixels,
        )
        return source_digest, staged

    def _cleanup_failed_transaction(
        self,
        transaction: _RenderTransaction,
        error: Exception,
    ) -> None:
        rollback_failures = (
            self._rollback_published_images(transaction.staged) if transaction.published else []
        )
        cleanup_failures: list[tuple[str, RenderError]] = []
        workspaces = (
            (
                "private render workspace",
                transaction.private_root,
                transaction.private_cleaned,
            ),
            (
                "publication staging",
                transaction.publication_root,
                transaction.publication_cleaned,
            ),
        )
        for label, path, cleaned in workspaces:
            if cleaned:
                continue
            try:
                self._tree_cleaner(path)
            except RenderError as cleanup_error:
                cleanup_failures.append((label, cleanup_error))

        if not rollback_failures and not cleanup_failures:
            return
        details: list[str] = []
        if rollback_failures:
            details.append(
                "final outputs could not be rolled back: " + ", ".join(rollback_failures)
            )
        if cleanup_failures:
            details.append(
                "temporary paths could not be removed: "
                + ", ".join(label for label, _failure in cleanup_failures)
            )
        cause: Exception = cleanup_failures[-1][1] if cleanup_failures else error
        raise RenderError(
            "render transaction failed and cleanup was incomplete; " + "; ".join(details)
        ) from cause

    def render(self, request: RenderRequest) -> RenderResult:
        source, output_dir = validate_render_request(request)
        availability = self.availability()
        if not availability.available or availability.executable is None:
            raise RendererUnavailable(availability.reason)

        output_dir.mkdir(parents=True, exist_ok=True)
        if output_dir.is_symlink() or not output_dir.is_dir():
            raise UnsafeRenderInput("render output directory changed during validation")
        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", source.stem).strip(".-") or "deck"

        transaction = self._create_transaction(output_dir)
        try:
            source_digest, transaction.staged = self._prepare_staging(
                transaction=transaction,
                executable=availability.executable,
                source=source,
                output_dir=output_dir,
                safe_stem=safe_stem,
                request=request,
            )

            # This is the transaction's commit barrier: no final image is visible until
            # the source snapshot, PDF, raster workspace, and LibreOffice profile are gone.
            self._tree_cleaner(transaction.private_root)
            transaction.private_cleaned = True

            slides = self._publish_images(transaction.staged)
            transaction.published = True
            self._tree_cleaner(transaction.publication_root)
            transaction.publication_cleaned = True

            return RenderResult(
                backend=self.name,
                fidelity=self.fidelity,
                source_sha256=source_digest,
                slides=slides,
            )
        except Exception as error:
            self._cleanup_failed_transaction(transaction, error)
            raise


__all__ = ["LibreOfficeRenderer", "PyMuPdfRasterizer"]
