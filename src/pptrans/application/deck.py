"""Transactional application service for one translated PPTX deck."""

from __future__ import annotations

import errno
import os
import stat
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NoReturn

from pptrans.domain.errors import PatchValidationError, SourceChangedError
from pptrans.domain.models import DeckPlan, DeckResult, PackageLimits, TranslationInput
from pptrans.ooxml.package import file_sha256
from pptrans.ooxml.patch import apply_patch_set, build_patch_set
from pptrans.ooxml.verify import verify_output

_UNLINK_RETRY_DELAYS_SECONDS = (0.05, 0.1, 0.2, 0.4, 0.8)
_TRANSIENT_UNLINK_ERRNOS = frozenset({errno.EACCES, errno.EBUSY, errno.EPERM})
_TRANSIENT_UNLINK_WINERRORS = frozenset({5, 32, 33})

_Ownership = Literal["absent", "owned", "foreign"]


@dataclass(frozen=True, slots=True)
class _FileIdentity:
    device: int
    inode: int


def _regular_file_identity(path: Path) -> _FileIdentity:
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode):
        raise PatchValidationError(f"Private staging path is not a regular file: {path}")
    return _FileIdentity(device=details.st_dev, inode=details.st_ino)


def _ownership(path: Path, identity: _FileIdentity) -> _Ownership:
    if not os.path.lexists(path):
        return "absent"
    try:
        details = path.lstat()
    except FileNotFoundError:
        return "absent"
    if not stat.S_ISREG(details.st_mode):
        return "foreign"
    if details.st_dev == identity.device and details.st_ino == identity.inode:
        return "owned"
    return "foreign"


def _is_transient_unlink_error(error: OSError) -> bool:
    winerror = getattr(error, "winerror", None)
    return error.errno in _TRANSIENT_UNLINK_ERRNOS or winerror in _TRANSIENT_UNLINK_WINERRORS


def _unlink_path(path: Path) -> None:
    path.unlink()


def _require_owned_staging(path: Path, identity: _FileIdentity) -> None:
    if _ownership(path, identity) != "owned":
        raise PatchValidationError("Private staging path changed before publication.")


def _unlink_owned_with_retry(
    path: Path,
    identity: _FileIdentity,
    *,
    retry_delays: tuple[float, ...] = _UNLINK_RETRY_DELAYS_SECONDS,
) -> _Ownership:
    """Remove one owned path while preserving absent or foreign replacements."""

    attempts = len(retry_delays) + 1
    for attempt in range(attempts):
        ownership = _ownership(path, identity)
        if ownership != "owned":
            return ownership
        try:
            _unlink_path(path)
        except FileNotFoundError:
            return "absent"
        except OSError as error:
            if not _is_transient_unlink_error(error) or attempt == attempts - 1:
                raise
            time.sleep(retry_delays[attempt])
            continue

        ownership = _ownership(path, identity)
        if ownership != "owned":
            return ownership
        if attempt == attempts - 1:
            raise OSError(errno.EBUSY, "owned path reappeared during cleanup", str(path))
        time.sleep(retry_delays[attempt])

    raise AssertionError("unreachable unlink retry state")


def _cleanup_prepublication_failure(
    staged: Path,
    identity: _FileIdentity,
    primary_error: BaseException,
) -> None:
    try:
        ownership = _unlink_owned_with_retry(staged, identity)
    except OSError:
        ownership = _ownership(staged, identity)
        raise PatchValidationError(
            "Translated deck creation failed and private staging cleanup was incomplete; "
            f"staging state={ownership}: {staged}"
        ) from primary_error
    if ownership == "foreign":
        raise PatchValidationError(
            "Translated deck creation failed; a foreign replacement at the private staging "
            f"path was preserved: {staged}"
        ) from primary_error


def _raise_postpublication_cleanup_error(
    *,
    staged: Path,
    output: Path,
    identity: _FileIdentity,
    stage_error: OSError | None,
) -> NoReturn:
    rollback_error: OSError | None = None
    output_before_rollback = _ownership(output, identity)
    try:
        _unlink_owned_with_retry(output, identity)
    except OSError as error:
        rollback_error = error

    output_state = _ownership(output, identity)
    staged_state = _ownership(staged, identity)
    details: list[str] = []
    if output_state == "owned":
        details.append(f"owned final output remains: {output}")
    elif output_state == "foreign":
        details.append(f"foreign replacement at final output was preserved: {output}")
    elif output_before_rollback == "owned":
        details.append("owned final output was rolled back")
    else:
        details.append("final output is absent")
    if staged_state == "owned":
        details.append(f"private staging remains: {staged}")
    elif staged_state == "foreign":
        details.append(f"foreign replacement at private staging was preserved: {staged}")
    else:
        details.append("private staging is absent")

    cause = rollback_error or stage_error
    raise PatchValidationError(
        "Translated deck publication cleanup was incomplete; " + "; ".join(details)
    ) from cause


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
        raise FileExistsError(
            f"Output already exists: {output}. Choose another destination or explicitly enable "
            "overwrite."
        )
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
    staged_identity = _regular_file_identity(staged)
    try:
        apply_patch_set(source, staged, patch_set, limits=limits, overwrite=True)
        report = verify_output(source, staged, patch_set, limits=limits)
        with staged.open("r+b") as handle:
            os.fsync(handle.fileno())
        _require_owned_staging(staged, staged_identity)
        _publish_staged(staged, output, overwrite=overwrite)
    except BaseException as error:
        _cleanup_prepublication_failure(staged, staged_identity, error)
        raise

    if overwrite:
        output_state = _ownership(output, staged_identity)
        if output_state != "owned":
            raise PatchValidationError(
                "Translated deck replacement did not leave the verified staged file at the "
                f"destination; output state={output_state}: {output}"
            )
        return DeckResult(output_path=output, report=report)

    try:
        staged_state = _unlink_owned_with_retry(staged, staged_identity)
    except OSError as stage_error:
        _raise_postpublication_cleanup_error(
            staged=staged,
            output=output,
            identity=staged_identity,
            stage_error=stage_error,
        )
    if staged_state != "absent":
        _raise_postpublication_cleanup_error(
            staged=staged,
            output=output,
            identity=staged_identity,
            stage_error=None,
        )

    output_state = _ownership(output, staged_identity)
    if output_state == "foreign":
        raise PatchValidationError(
            f"Translated deck output was replaced before success; foreign path preserved: {output}"
        )
    if output_state == "absent":
        raise PatchValidationError("Translated deck output disappeared before success.")
    return DeckResult(output_path=output, report=report)


__all__ = ["preflight_output", "write_translated_deck"]
