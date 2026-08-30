"""Reproduce and verify PPTrans's committed native LibreOffice demo evidence.

This command is intentionally exacting: it rebuilds the offline identity output,
renders the English source, identity output, and curated zh-CN target, then compares
every result with the pinned Windows/LibreOffice acceptance records and committed PNGs.
PPTrans makes no provider/API request, but the LibreOffice subprocess is not placed
under an OS-level network sandbox. The command refuses to reuse an existing output.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess  # nosec B404
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from pptrans.adapters.providers.identity import IdentityTranslator
from pptrans.adapters.renderers import LibreOfficeRenderer, RenderRequest, RenderResult
from pptrans.application.deck import write_translated_deck
from pptrans.application.translate import translate_plan
from pptrans.ooxml import inspect_deck

REPO_ROOT = Path(__file__).parents[1]
DEFAULT_SOURCE = REPO_ROOT / "examples" / "pptrans-demo.en.pptx"
DEFAULT_TARGET = REPO_ROOT / "examples" / "pptrans-demo.zh-CN.pptx"
DEFAULT_ASSETS = REPO_ROOT / "docs" / "assets"
NATIVE_QA_PATH = REPO_ROOT / "docs" / "qa" / "2026-08-28-windows-libreoffice.json"
CURATED_QA_PATH = REPO_ROOT / "docs" / "qa" / "2026-08-28-curated-zh-cn.json"

_VERSION_PATTERN = re.compile(r"^LibreOffice (?P<version>\d+(?:\.\d+){3}) (?P<build>[0-9a-f]{40})$")
_SECRET_ENVIRONMENT_KEY = re.compile(
    r"(?:api[_-]?key|authorization|password|secret|token|credential)", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class ExpectedSlide:
    slide_number: int
    width: int
    height: int
    source_sha256: str
    identity_sha256: str
    target_sha256: str
    source_asset: str
    target_asset: str


@dataclass(frozen=True, slots=True)
class NativeEvidenceContract:
    libreoffice_version: str
    libreoffice_build: str
    pymupdf_version: str
    dpi: int
    source_path: str
    source_bytes: int
    source_sha256: str
    target_path: str
    target_bytes: int
    target_sha256: str
    slides: tuple[ExpectedSlide, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"QA record must contain a JSON object: {path}")
    return value


def load_contract(
    native_qa_path: Path = NATIVE_QA_PATH,
    curated_qa_path: Path = CURATED_QA_PATH,
) -> NativeEvidenceContract:
    """Load the two pinned QA records as one strict native-evidence contract."""

    native = _load_json(native_qa_path)
    curated = _load_json(curated_qa_path)
    native_renderer = native["renderer"]
    curated_renderer = curated["renderer"]
    for key in ("libreoffice_version", "libreoffice_build", "pymupdf_version", "dpi"):
        if native_renderer[key] != curated_renderer[key]:
            raise ValueError(f"native QA records disagree on renderer field: {key}")

    native_source = native["presentations"]["source"]
    curated_source = curated["presentations"]["source"]
    if native_source != curated_source:
        raise ValueError("native QA records disagree on the English source deck")
    native_identity = native["presentations"]["identity_output"]
    if not native_identity["byte_identical_to_source"]:
        raise ValueError("identity QA record does not require a byte-identical output")
    if (native_identity["bytes"], native_identity["sha256"]) != (
        native_source["bytes"],
        native_source["sha256"],
    ):
        raise ValueError("identity QA package hash does not match its source")

    native_slides = native["slides"]
    curated_slides = curated["slides"]
    if len(native_slides) != len(curated_slides) or not native_slides:
        raise ValueError("native QA records must contain the same nonzero slide count")

    slides: list[ExpectedSlide] = []
    for identity_slide, target_slide in zip(native_slides, curated_slides, strict=True):
        slide_number = identity_slide["slide_number"]
        if target_slide["slide_number"] != slide_number:
            raise ValueError("native QA slide order differs between records")
        if identity_slide["source_png_sha256"] != target_slide["source_png_sha256"]:
            raise ValueError(f"source render hash differs for slide {slide_number}")
        if identity_slide["source_png_sha256"] != identity_slide["identity_png_sha256"]:
            raise ValueError(f"identity render hash differs for slide {slide_number}")
        if not identity_slide["pixel_equal"] or not target_slide["dimensions_equal"]:
            raise ValueError(f"native QA comparison failed for slide {slide_number}")
        if (identity_slide["width"], identity_slide["height"]) != (
            target_slide["width"],
            target_slide["height"],
        ):
            raise ValueError(f"native QA dimensions differ for slide {slide_number}")
        slides.append(
            ExpectedSlide(
                slide_number=slide_number,
                width=identity_slide["width"],
                height=identity_slide["height"],
                source_sha256=identity_slide["source_png_sha256"],
                identity_sha256=identity_slide["identity_png_sha256"],
                target_sha256=target_slide["target_png_sha256"],
                source_asset=f"pptrans-demo-libreoffice-en-slide-{slide_number:02d}.png",
                target_asset=f"pptrans-demo-libreoffice-zh-CN-slide-{slide_number:02d}.png",
            )
        )

    target = curated["presentations"]["curated_target"]
    return NativeEvidenceContract(
        libreoffice_version=native_renderer["libreoffice_version"],
        libreoffice_build=native_renderer["libreoffice_build"],
        pymupdf_version=native_renderer["pymupdf_version"],
        dpi=native_renderer["dpi"],
        source_path=native_source["path"],
        source_bytes=native_source["bytes"],
        source_sha256=native_source["sha256"],
        target_path=target["path"],
        target_bytes=target["bytes"],
        target_sha256=target["sha256"],
        slides=tuple(slides),
    )


def verify_committed_assets(contract: NativeEvidenceContract, assets_dir: Path) -> None:
    """Require each committed PNG to match the recorded native hash and dimensions."""

    for slide in contract.slides:
        for label, name, expected_sha256 in (
            ("source", slide.source_asset, slide.source_sha256),
            ("target", slide.target_asset, slide.target_sha256),
        ):
            path = assets_dir / name
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"missing regular {label} native asset: {path}")
            if _sha256(path) != expected_sha256:
                raise ValueError(f"{label} native asset hash differs: {path}")
            with Image.open(path) as image:
                if image.format != "PNG" or image.size != (slide.width, slide.height):
                    raise ValueError(f"{label} native asset dimensions differ: {path}")
                image.verify()


def _verify_deck(path: Path, *, expected_bytes: int, expected_sha256: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"presentation must be a regular file: {path}")
    resolved = path.resolve()
    if resolved.stat().st_size != expected_bytes or _sha256(resolved) != expected_sha256:
        raise ValueError(f"presentation does not match its pinned QA record: {resolved}")
    return resolved


def _safe_environment() -> dict[str, str]:
    return {
        key: value for key, value in os.environ.items() if not _SECRET_ENVIRONMENT_KEY.search(key)
    }


def _read_libreoffice_build(executable: Path) -> tuple[Path, str, str]:
    if executable.is_symlink() or not executable.is_file():
        raise ValueError(f"LibreOffice executable must be a regular file: {executable}")
    resolved = executable.resolve()
    version_executable = resolved
    if resolved.suffix.lower() == ".exe":
        console_executable = resolved.with_suffix(".com")
        if console_executable.is_file() and not console_executable.is_symlink():
            version_executable = console_executable
    try:
        completed = subprocess.run(  # noqa: S603  # nosec B603
            [str(version_executable), "--headless", "--version"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            shell=False,
            env=_safe_environment(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"could not read LibreOffice version: {exc}") from exc
    output = (completed.stdout or completed.stderr or "").strip()
    match = _VERSION_PATTERN.fullmatch(output)
    if completed.returncode != 0 or match is None:
        raise ValueError(f"unexpected LibreOffice version response: {output[:200]!r}")
    return resolved, match.group("version"), match.group("build")


def _verify_render(
    label: str,
    result: RenderResult,
    contract: NativeEvidenceContract,
    expected_source_sha256: str,
) -> None:
    if result.backend != "libreoffice" or result.fidelity.value != "high":
        raise ValueError(f"{label} did not use the high-fidelity LibreOffice renderer")
    if result.source_sha256 != expected_source_sha256:
        raise ValueError(f"{label} package digest differs from the QA record")
    if len(result.slides) != len(contract.slides):
        raise ValueError(f"{label} rendered an unexpected number of slides")
    for actual, expected in zip(result.slides, contract.slides, strict=True):
        expected_hash = {
            "source": expected.source_sha256,
            "identity": expected.identity_sha256,
            "curated_target": expected.target_sha256,
        }[label]
        if actual.slide_number != expected.slide_number:
            raise ValueError(f"{label} slide order differs from the QA record")
        if (actual.width, actual.height, actual.sha256) != (
            expected.width,
            expected.height,
            expected_hash,
        ):
            raise ValueError(f"{label} native render differs for slide {actual.slide_number}")


def reproduce(
    *,
    libreoffice: Path,
    source: Path,
    target: Path,
    output_dir: Path,
    assets_dir: Path,
) -> Path:
    """Rebuild and verify the complete native demo bundle, returning its manifest."""

    contract = load_contract()
    source = _verify_deck(
        source, expected_bytes=contract.source_bytes, expected_sha256=contract.source_sha256
    )
    target = _verify_deck(
        target, expected_bytes=contract.target_bytes, expected_sha256=contract.target_sha256
    )
    verify_committed_assets(contract, assets_dir)
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    installed_pymupdf = importlib.metadata.version("PyMuPDF")
    if installed_pymupdf != contract.pymupdf_version:
        raise ValueError(
            "PyMuPDF version differs from the pinned QA record: "
            f"{installed_pymupdf} != {contract.pymupdf_version}"
        )
    executable, version, build = _read_libreoffice_build(libreoffice)
    if (version, build) != (contract.libreoffice_version, contract.libreoffice_build):
        raise ValueError(
            "LibreOffice build differs from the pinned QA record: "
            f"{version} {build} != {contract.libreoffice_version} {contract.libreoffice_build}"
        )

    output_dir.mkdir(parents=True)
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise ValueError("output directory changed during creation")
    output_dir = output_dir.resolve()

    identity_path = output_dir / "pptrans-demo.identity.pptx"
    plan = inspect_deck(source, source_lang="en", target_lang="en")
    run = translate_plan(plan, IdentityTranslator())
    identity = write_translated_deck(plan, run.translations, identity_path)
    if identity_path.read_bytes() != source.read_bytes():
        raise ValueError("rebuilt identity output is not byte-identical to the source")

    renderer = LibreOfficeRenderer(executable=executable)
    rendered = {
        "source": renderer.render(
            RenderRequest(
                source,
                output_dir / "source",
                dpi=contract.dpi,
                timeout_seconds=180,
            )
        ),
        "identity": renderer.render(
            RenderRequest(
                identity_path,
                output_dir / "identity",
                dpi=contract.dpi,
                timeout_seconds=180,
            )
        ),
        "curated_target": renderer.render(
            RenderRequest(
                target,
                output_dir / "curated-target",
                dpi=contract.dpi,
                timeout_seconds=180,
            )
        ),
    }
    _verify_render("source", rendered["source"], contract, contract.source_sha256)
    _verify_render("identity", rendered["identity"], contract, contract.source_sha256)
    _verify_render("curated_target", rendered["curated_target"], contract, contract.target_sha256)

    slide_evidence = []
    for expected, source_slide, identity_slide, target_slide in zip(
        contract.slides,
        rendered["source"].slides,
        rendered["identity"].slides,
        rendered["curated_target"].slides,
        strict=True,
    ):
        slide_evidence.append(
            {
                "slide_number": expected.slide_number,
                "width": expected.width,
                "height": expected.height,
                "source": {
                    "path": source_slide.image_path.relative_to(output_dir).as_posix(),
                    "sha256": source_slide.sha256,
                    "committed_asset": f"docs/assets/{expected.source_asset}",
                },
                "identity": {
                    "path": identity_slide.image_path.relative_to(output_dir).as_posix(),
                    "sha256": identity_slide.sha256,
                    "pixel_equal_to_source": identity_slide.sha256 == source_slide.sha256,
                },
                "curated_target": {
                    "path": target_slide.image_path.relative_to(output_dir).as_posix(),
                    "sha256": target_slide.sha256,
                    "committed_asset": f"docs/assets/{expected.target_asset}",
                },
            }
        )

    manifest = {
        "schema_version": 1,
        "renderer": {
            "libreoffice_version": version,
            "libreoffice_build": build,
            "pymupdf_version": installed_pymupdf,
            "dpi": contract.dpi,
        },
        "source": {
            "path": contract.source_path,
            "bytes": contract.source_bytes,
            "sha256": contract.source_sha256,
        },
        "identity": {
            "path": identity_path.relative_to(output_dir).as_posix(),
            "bytes": identity_path.stat().st_size,
            "sha256": identity.report.output_sha256,
            "byte_identical_to_source": True,
            "provider_calls": run.stats.provider_calls,
        },
        "curated_target": {
            "path": contract.target_path,
            "bytes": contract.target_bytes,
            "sha256": contract.target_sha256,
        },
        "slides": slide_evidence,
        "qa_records": {
            "identity": {
                "path": NATIVE_QA_PATH.relative_to(REPO_ROOT).as_posix(),
                "sha256": _sha256(NATIVE_QA_PATH),
            },
            "curated_target": {
                "path": CURATED_QA_PATH.relative_to(REPO_ROOT).as_posix(),
                "sha256": _sha256(CURATED_QA_PATH),
            },
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--libreoffice",
        type=Path,
        required=True,
        help="Explicit path to the pinned soffice executable",
    )
    parser.add_argument("--output-dir", type=Path, required=True, help="New evidence directory")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--assets-dir", type=Path, default=DEFAULT_ASSETS)
    args = parser.parse_args()
    manifest_path = reproduce(
        libreoffice=args.libreoffice,
        source=args.source,
        target=args.target,
        output_dir=args.output_dir,
        assets_dir=args.assets_dir,
    )
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "status": "native demo evidence reproduced",
            },
            ensure_ascii=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
