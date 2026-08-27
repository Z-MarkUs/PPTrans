"""Transactional application service for one translated PPTX deck."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from pptrans.domain.errors import PatchValidationError, SourceChangedError
from pptrans.domain.models import DeckPlan, DeckResult, PackageLimits, TranslationInput
from pptrans.ooxml.package import file_sha256
from pptrans.ooxml.patch import apply_patch_set, build_patch_set
from pptrans.ooxml.verify import verify_output


def _same_path(left: Path, right: Path) -> bool:
    if os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve())):
        return True
    try:
        return left.samefile(right)
    except (FileNotFoundError, OSError):
        return False


def _absolute_leaf(path: Path) -> Path:
    """Resolve the parent while preserving the destination leaf itself."""

    expanded = Path(path).expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    return expanded.parent.resolve(strict=False) / expanded.name


def preflight_output(
    plan: DeckPlan,
    output_path: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Validate and probe a destination before any potentially paid provider call."""

    source = plan.source_path
    output = _absolute_leaf(output_path)
    if output.is_symlink():
        raise PatchValidationError("Output path must not be a symbolic link.")
    if _same_path(source, output):
        raise PatchValidationError("Output path must not overwrite the source PPTX.")
    if output.suffix.lower() != ".pptx":
        raise PatchValidationError("Formatting-safe output must use the .pptx extension.")
    if output.exists() and output.is_dir():
        raise IsADirectoryError(output)
    if output.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output}")
    if file_sha256(source) != plan.input_sha256:
        raise SourceChangedError("The source PPTX changed after inspection.")

    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, probe_name = tempfile.mkstemp(
        prefix=".pptrans-write-probe-", suffix=".tmp", dir=output.parent
    )
    os.close(descriptor)
    Path(probe_name).unlink()
    return output


def _publish_staged(staged: Path, output: Path, *, overwrite: bool) -> None:
    """Publish a complete staged file atomically without an accidental clobber."""

    if output.is_symlink():
        raise PatchValidationError("Output path became a symbolic link before publish.")
    if overwrite:
        staged.replace(output)
        return
    try:
        os.link(staged, output)
    except FileExistsError as exc:
        raise FileExistsError(f"Output appeared before publish: {output}") from exc
    except OSError as exc:
        raise PatchValidationError(
            "The destination filesystem cannot atomically publish a no-overwrite output."
        ) from exc


def write_translated_deck(
    plan: DeckPlan,
    translations: TranslationInput,
    output_path: Path,
    *,
    overwrite: bool = False,
    require_complete: bool = True,
    limits: PackageLimits | None = None,
) -> DeckResult:
    """Stage, verify, and atomically publish a translated copy of a deck."""

    source = plan.source_path
    output = preflight_output(plan, output_path, overwrite=overwrite)

    patch_set = build_patch_set(plan, translations, require_complete=require_complete)
    descriptor, staged_name = tempfile.mkstemp(
        prefix=f".{output.stem}.pptrans-", suffix=".pptx", dir=output.parent
    )
    os.close(descriptor)
    staged = Path(staged_name)
    try:
        apply_patch_set(source, staged, patch_set, limits=limits, overwrite=True)
        report = verify_output(source, staged, patch_set, limits=limits)
        with staged.open("r+b") as handle:
            os.fsync(handle.fileno())
        _publish_staged(staged, output, overwrite=overwrite)
        return DeckResult(output_path=output, report=report)
    finally:
        if staged.exists():
            staged.unlink()


__all__ = ["preflight_output", "write_translated_deck"]
