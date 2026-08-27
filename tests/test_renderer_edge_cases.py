"""Deterministic boundary and failure tests for faithful render adapters."""

from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from pptrans.adapters.renderers import (
    LibreOfficeRenderer,
    PyMuPdfRasterizer,
    RendererAvailability,
    RenderError,
    RendererUnavailable,
    RenderRequest,
    UnsafeRenderInput,
    base,
    libreoffice,
)


class _AvailableRasterizer:
    @staticmethod
    def available() -> bool:
        return True

    def rasterize(
        self,
        _pdf_path: Path,
        output_dir: Path,
        **_limits: int,
    ) -> tuple[Path, ...]:
        output_path = output_dir / "page.png"
        Image.new("RGB", (12, 8), "white").save(output_path, "PNG")
        return (output_path,)


class _UnavailableRasterizer(_AvailableRasterizer):
    @staticmethod
    def available() -> bool:
        return False


def _request(tmp_path: Path, **changes: object) -> RenderRequest:
    source = tmp_path / "deck.pptx"
    source.write_bytes(b"")
    return replace(RenderRequest(source, tmp_path / "renders"), **changes)


def test_render_request_requires_path_objects(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match=r"pathlib\.Path"):
        base.validate_render_request(RenderRequest("deck.pptx", tmp_path))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match=r"pathlib\.Path"):
        base.validate_render_request(RenderRequest(tmp_path, "renders"))  # type: ignore[arg-type]


def test_render_request_rejects_a_symlinked_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request(tmp_path)
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == request.presentation_path)

    with pytest.raises(UnsafeRenderInput, match="symlinked presentation"):
        base.validate_render_request(request)


def test_render_request_rejects_missing_source(tmp_path: Path) -> None:
    request = RenderRequest(tmp_path / "missing.pptx", tmp_path / "renders")

    with pytest.raises(UnsafeRenderInput, match="not a regular file"):
        base.validate_render_request(request)


def test_render_request_accepts_explicit_legacy_ppt(tmp_path: Path) -> None:
    source = tmp_path / "legacy.ppt"
    source.write_bytes(b"legacy")
    output = tmp_path / "renders"

    assert base.validate_render_request(RenderRequest(source, output, allow_legacy_ppt=True)) == (
        source.resolve(),
        output.resolve(),
    )


def test_render_request_enforces_input_size(tmp_path: Path) -> None:
    request = _request(tmp_path, max_input_bytes=1)
    request.presentation_path.write_bytes(b"too large")

    with pytest.raises(UnsafeRenderInput, match="input-size"):
        base.validate_render_request(request)


def test_render_request_rejects_a_symlinked_output_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request(tmp_path)
    request.output_dir.mkdir()
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == request.output_dir)

    with pytest.raises(UnsafeRenderInput, match="symlinked render output"):
        base.validate_render_request(request)


def test_render_request_rejects_output_file(tmp_path: Path) -> None:
    request = _request(tmp_path)
    request.output_dir.write_bytes(b"not a directory")

    with pytest.raises(UnsafeRenderInput, match="must be a directory"):
        base.validate_render_request(request)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dpi", 0),
        ("max_pages", True),
        ("max_total_pixels", "many"),
        ("max_input_bytes", 0),
        ("max_pdf_bytes", -1),
    ],
)
def test_render_request_requires_positive_integer_limits(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    request = _request(tmp_path, **{field: value})

    with pytest.raises(UnsafeRenderInput, match=f"{field} must be a positive integer"):
        base.validate_render_request(request)


def test_render_request_caps_dpi(tmp_path: Path) -> None:
    request = _request(tmp_path, dpi=base.MAX_RENDER_DPI + 1)

    with pytest.raises(UnsafeRenderInput, match="dpi may not exceed"):
        base.validate_render_request(request)


@pytest.mark.parametrize("timeout", [True, "slow", 0, 601])
def test_render_request_bounds_timeout(tmp_path: Path, timeout: object) -> None:
    request = _request(tmp_path, timeout_seconds=timeout)

    with pytest.raises(UnsafeRenderInput, match="timeout_seconds"):
        base.validate_render_request(request)


def test_validate_png_rejects_missing_symlink_invalid_non_png_and_large_images(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = tmp_path / "missing.png"
    with pytest.raises(RenderError, match="regular image"):
        base.validate_png(missing, max_pixels=100)

    linked = tmp_path / "linked.png"
    linked.write_bytes(b"placeholder")
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == linked)
    with pytest.raises(RenderError, match="regular image"):
        base.validate_png(linked, max_pixels=100)
    monkeypatch.setattr(Path, "is_symlink", original_is_symlink)

    invalid = tmp_path / "invalid.png"
    invalid.write_bytes(b"not an image")
    with pytest.raises(RenderError, match="invalid rendered PNG"):
        base.validate_png(invalid, max_pixels=100)

    jpeg = tmp_path / "page.jpg"
    Image.new("RGB", (2, 2), "white").save(jpeg, "JPEG")
    with pytest.raises(RenderError, match="not PNG"):
        base.validate_png(jpeg, max_pixels=100)

    large = tmp_path / "large.png"
    Image.new("RGB", (11, 10), "white").save(large, "PNG")
    with pytest.raises(RenderError, match="dimensions"):
        base.validate_png(large, max_pixels=100)


def test_sanitized_environment_defaults_to_process_and_filters_secret_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PPTRANS_RENDER_SAFE", "visible")
    monkeypatch.setenv("PPTRANS_RENDER_AUTHORIZATION", "opaque")

    environment = libreoffice._sanitized_environment()

    assert environment["PPTRANS_RENDER_SAFE"] == "visible"
    assert "PPTRANS_RENDER_AUTHORIZATION" not in environment


@pytest.mark.parametrize(
    ("page_count", "max_pages", "message"),
    [(0, 5, "empty PDF"), (6, 5, "page limit")],
)
def test_page_count_validation_rejects_invalid_counts(
    page_count: int,
    max_pages: int,
    message: str,
) -> None:
    with pytest.raises(RenderError, match=message):
        libreoffice._validate_page_count(page_count, max_pages)


def test_page_and_pixel_helpers_accept_limits_and_reject_overflow() -> None:
    libreoffice._validate_page_count(2, 2)
    assert libreoffice._add_page_pixels(4, 2, 3, 10) == 10
    with pytest.raises(RenderError, match="total-pixel"):
        libreoffice._add_page_pixels(5, 2, 3, 10)


def test_pymupdf_availability_uses_module_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(libreoffice.importlib.util, "find_spec", lambda _name: None)
    assert PyMuPdfRasterizer.available() is False
    monkeypatch.setattr(libreoffice.importlib.util, "find_spec", lambda _name: object())
    assert PyMuPdfRasterizer.available() is True


def test_pymupdf_rasterizer_fails_closed_when_extra_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rasterizer = PyMuPdfRasterizer()
    monkeypatch.setattr(rasterizer, "available", lambda: False)

    with pytest.raises(RendererUnavailable, match=r"pptrans\[review\]"):
        rasterizer.rasterize(
            tmp_path / "deck.pdf",
            tmp_path / "pages",
            dpi=144,
            max_pages=5,
            max_total_pixels=1_000,
        )


class _FakePixmap:
    def __init__(self, size: tuple[int, int]) -> None:
        self._size = size

    def save(self, path: str) -> None:
        Image.new("RGB", self._size, "white").save(path, "PNG")


class _FakePage:
    def __init__(self, width: float, height: float) -> None:
        self.rect = SimpleNamespace(width=width, height=height)

    def get_pixmap(self, *, matrix: object, alpha: bool) -> _FakePixmap:
        assert matrix == (2.0, 2.0)
        assert alpha is False
        return _FakePixmap((20, 12))


class _FakeDocument:
    def __init__(self, pages: tuple[_FakePage, ...], *, page_count: int | None = None) -> None:
        self._pages = pages
        self.page_count = len(pages) if page_count is None else page_count

    def __enter__(self) -> _FakeDocument:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def __iter__(self) -> object:
        return iter(self._pages)


def _fake_fitz(document: _FakeDocument) -> SimpleNamespace:
    return SimpleNamespace(
        open=lambda _path: document,
        Matrix=lambda x, y: (x, y),
    )


def test_pymupdf_rasterizer_writes_numbered_pages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rasterizer = PyMuPdfRasterizer()
    document = _FakeDocument((_FakePage(10, 6), _FakePage(10, 6)))
    monkeypatch.setattr(rasterizer, "available", lambda: True)
    monkeypatch.setattr(libreoffice.importlib, "import_module", lambda _name: _fake_fitz(document))

    paths = rasterizer.rasterize(
        tmp_path / "deck.pdf",
        tmp_path / "pages",
        dpi=144,
        max_pages=2,
        max_total_pixels=1_000,
    )

    assert [path.name for path in paths] == ["page-0001.png", "page-0002.png"]
    assert all(path.is_file() for path in paths)


def test_pymupdf_rasterizer_preserves_policy_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rasterizer = PyMuPdfRasterizer()
    document = _FakeDocument((), page_count=0)
    monkeypatch.setattr(rasterizer, "available", lambda: True)
    monkeypatch.setattr(libreoffice.importlib, "import_module", lambda _name: _fake_fitz(document))

    with pytest.raises(RenderError, match="empty PDF") as raised:
        rasterizer.rasterize(
            tmp_path / "deck.pdf",
            tmp_path / "pages",
            dpi=144,
            max_pages=2,
            max_total_pixels=1_000,
        )

    assert raised.value.__cause__ is None


def test_pymupdf_rasterizer_wraps_backend_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rasterizer = PyMuPdfRasterizer()
    backend = SimpleNamespace(
        open=lambda _path: (_ for _ in ()).throw(RuntimeError("broken PDF")),
        Matrix=lambda x, y: (x, y),
    )
    monkeypatch.setattr(rasterizer, "available", lambda: True)
    monkeypatch.setattr(libreoffice.importlib, "import_module", lambda _name: backend)

    with pytest.raises(RenderError, match="could not rasterize") as raised:
        rasterizer.rasterize(
            tmp_path / "deck.pdf",
            tmp_path / "pages",
            dpi=144,
            max_pages=2,
            max_total_pixels=1_000,
        )

    assert isinstance(raised.value.__cause__, RuntimeError)


def test_executable_discovery_checks_both_standard_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovered = tmp_path / "libreoffice"
    calls: list[str] = []

    def which(name: str) -> str | None:
        calls.append(name)
        return str(discovered) if name == "libreoffice" else None

    monkeypatch.setattr(libreoffice.shutil, "which", which)
    renderer = LibreOfficeRenderer(rasterizer=_AvailableRasterizer())

    assert renderer._find_executable() == discovered.resolve()
    assert calls == ["soffice", "libreoffice"]

    monkeypatch.setattr(libreoffice.shutil, "which", lambda _name: None)
    assert renderer._find_executable() is None


def test_availability_checks_optional_rasterizer(tmp_path: Path) -> None:
    executable = tmp_path / "soffice"
    executable.write_bytes(b"executable")

    unavailable = LibreOfficeRenderer(
        executable=executable,
        rasterizer=_UnavailableRasterizer(),
    ).availability()

    assert unavailable.available is False
    assert unavailable.executable == executable.resolve()
    assert "rasterizer" in unavailable.reason

    rasterizer_without_probe = SimpleNamespace(rasterize=lambda *_args, **_kwargs: ())
    available = LibreOfficeRenderer(
        executable=executable,
        rasterizer=rasterizer_without_probe,
    ).availability()
    assert available.available is True


def _conversion_arguments(
    tmp_path: Path,
    runner: Any,
    **request_changes: object,
) -> tuple[LibreOfficeRenderer, dict[str, object]]:
    executable = tmp_path / "soffice"
    executable.write_bytes(b"executable")
    source = tmp_path / "deck.pptx"
    source.write_bytes(b"deck")
    temp_root = tmp_path / "temp"
    conversion_dir = temp_root / "converted"
    profile_dir = temp_root / "profile"
    conversion_dir.mkdir(parents=True)
    profile_dir.mkdir()
    request = replace(RenderRequest(source, tmp_path / "renders"), **request_changes)
    renderer = LibreOfficeRenderer(
        executable=executable,
        rasterizer=_AvailableRasterizer(),
        runner=runner,
        slide_counter=lambda _source: 1,
    )
    arguments: dict[str, object] = {
        "executable": executable,
        "source": source,
        "conversion_dir": conversion_dir,
        "profile_dir": profile_dir,
        "temp_root": temp_root,
        "request": request,
    }
    return renderer, arguments


@pytest.mark.parametrize("failure", ["timeout", "oserror"])
def test_convert_to_pdf_wraps_process_start_failures(tmp_path: Path, failure: str) -> None:
    def runner(*_args: object, **_kwargs: object) -> object:
        if failure == "timeout":
            raise subprocess.TimeoutExpired(cmd="soffice", timeout=1)
        raise OSError("cannot execute")

    renderer, arguments = _conversion_arguments(tmp_path, runner)
    expected = "timed out" if failure == "timeout" else "could not start"

    with pytest.raises(RenderError, match=expected):
        renderer._convert_to_pdf(**arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize("stderr", ["first line\nsecond line", None])
def test_convert_to_pdf_reports_nonzero_status(
    tmp_path: Path,
    stderr: str | None,
) -> None:
    def runner(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 17, "", stderr)

    renderer, arguments = _conversion_arguments(tmp_path, runner)

    with pytest.raises(RenderError, match="status 17") as raised:
        renderer._convert_to_pdf(**arguments)  # type: ignore[arg-type]

    assert "\n" not in str(raised.value)


def test_convert_to_pdf_requires_exactly_one_fallback_file(tmp_path: Path) -> None:
    def no_output(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, "", "")

    renderer, arguments = _conversion_arguments(tmp_path, no_output)
    with pytest.raises(RenderError, match="exactly one PDF"):
        renderer._convert_to_pdf(**arguments)  # type: ignore[arg-type]

    conversion_dir = arguments["conversion_dir"]
    assert isinstance(conversion_dir, Path)
    (conversion_dir / "one.pdf").write_bytes(b"pdf")
    (conversion_dir / "two.pdf").write_bytes(b"pdf")
    with pytest.raises(RenderError, match="exactly one PDF"):
        renderer._convert_to_pdf(**arguments)  # type: ignore[arg-type]


def test_convert_to_pdf_accepts_single_renamed_fallback(tmp_path: Path) -> None:
    def renamed(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        output_dir = Path(args[args.index("--outdir") + 1])
        (output_dir / "converted-name.pdf").write_bytes(b"pdf")
        return subprocess.CompletedProcess(args, 0, "", "")

    renderer, arguments = _conversion_arguments(tmp_path, renamed)

    result = renderer._convert_to_pdf(**arguments)  # type: ignore[arg-type]

    assert result.name == "converted-name.pdf"


def test_convert_to_pdf_enforces_output_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def expected(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        output_dir = Path(args[args.index("--outdir") + 1])
        source = Path(args[-1])
        (output_dir / f"{source.stem}.pdf").write_bytes(b"oversized")
        return subprocess.CompletedProcess(args, 0, "", "")

    renderer, arguments = _conversion_arguments(tmp_path, expected, max_pdf_bytes=1)
    with pytest.raises(RenderError, match="size boundary"):
        renderer._convert_to_pdf(**arguments)  # type: ignore[arg-type]

    arguments["request"] = replace(arguments["request"], max_pdf_bytes=100)  # type: ignore[arg-type]
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: self.suffix == ".pdf")
    with pytest.raises(RenderError, match="size boundary"):
        renderer._convert_to_pdf(**arguments)  # type: ignore[arg-type]
    monkeypatch.setattr(Path, "is_symlink", original_is_symlink)


def test_validate_images_enforces_page_and_cumulative_pixel_limits(tmp_path: Path) -> None:
    request = RenderRequest(tmp_path / "deck.pptx", tmp_path / "renders", max_pages=1)
    with pytest.raises(RenderError, match="page limit"):
        LibreOfficeRenderer._validate_images((tmp_path / "a", tmp_path / "b"), request)

    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("RGB", (8, 8), "white").save(first, "PNG")
    Image.new("RGB", (8, 8), "white").save(second, "PNG")
    request = replace(request, max_pages=2, max_total_pixels=100)
    with pytest.raises(RenderError, match="total-pixel"):
        LibreOfficeRenderer._validate_images((first, second), request)


def test_render_rejects_inconsistent_available_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "deck.pptx"
    source.write_bytes(b"deck")
    renderer = LibreOfficeRenderer(rasterizer=_AvailableRasterizer())
    monkeypatch.setattr(
        renderer,
        "availability",
        lambda: RendererAvailability(available=True, reason="inconsistent", executable=None),
    )

    with pytest.raises(RendererUnavailable, match="inconsistent"):
        renderer.render(RenderRequest(source, tmp_path / "renders"))


def test_render_uses_safe_fallback_name_for_non_ascii_stem(tmp_path: Path) -> None:
    executable = tmp_path / "soffice"
    executable.write_bytes(b"executable")
    source = tmp_path / "漢字.pptx"
    source.write_bytes(b"deck")

    def runner(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        output_dir = Path(args[args.index("--outdir") + 1])
        (output_dir / f"{source.stem}.pdf").write_bytes(b"pdf")
        return subprocess.CompletedProcess(args, 0, "", "")

    renderer = LibreOfficeRenderer(
        executable=executable,
        rasterizer=_AvailableRasterizer(),
        runner=runner,
        slide_counter=lambda _source: 1,
    )

    result = renderer.render(RenderRequest(source, tmp_path / "renders"))

    assert len(result.slides) == 1
    assert result.slides[0].image_path.name.startswith("deck-")
