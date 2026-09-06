"""Rebuild the committed English demo from its inspectable canonical OOXML source.

The builder intentionally uses only the Python standard library.  Every package
member, its order, and every ZIP header field are pinned so the resulting PPTX is
byte-identical across PPTrans's supported Python and operating-system matrix.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import time
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = REPO_ROOT / "examples" / "pptrans-demo.source"
DEFAULT_COMMITTED_DEMO = REPO_ROOT / "examples" / "pptrans-demo.en.pptx"
EXPECTED_PACKAGE_PATH = "examples/pptrans-demo.en.pptx"
MANIFEST_NAME = "manifest.json"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
ZIP_CREATE_SYSTEM = 3
ZIP_CREATE_VERSION = 20
ZIP_EXTRACT_VERSION = 20
ZIP_EXTERNAL_ATTR = 0o100644 << 16
TIMESTAMP_COMPONENT_COUNT = 6
FIXED_TIMESTAMP = (2026, 8, 28, 0, 34, 0)
UNLINK_RETRY_DELAYS_SECONDS = (0.0, 0.01, 0.05)
TRANSIENT_UNLINK_ERRNOS = frozenset({errno.EACCES, errno.EBUSY, errno.EPERM})
TRANSIENT_UNLINK_WINERRORS = frozenset({5, 32, 33})


@dataclass(frozen=True, slots=True)
class SourceEntry:
    """One ordered OOXML package member declared by the source manifest."""

    path: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class DemoManifest:
    """Validated deterministic archive contract."""

    timestamp: tuple[int, int, int, int, int, int]
    expected_size: int
    expected_sha256: str
    entries: tuple[SourceEntry, ...]


@dataclass(frozen=True, slots=True)
class FileIdentity:
    """Filesystem identity used to preserve foreign path replacements."""

    device: int
    inode: int


def _mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be a JSON object with string keys")
    return value


def _sequence(value: object, *, field: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise TypeError(f"{field} must be a JSON array")
    return value


def _string(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    return value


def _integer(value: object, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field} must be an integer")
    return value


def _sha256(value: object, *, field: str) -> str:
    digest = _string(value, field=field)
    if SHA256_PATTERN.fullmatch(digest) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return digest


def _member_path(value: object, *, field: str) -> str:
    path = _string(value, field=field)
    pure = PurePosixPath(path)
    if (
        not path
        or not path.isascii()
        or "\\" in path
        or path.startswith("/")
        or pure.is_absolute()
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise ValueError(f"{field} is not a safe relative OOXML member path: {path!r}")
    return pure.as_posix()


def _archive_contract(value: object) -> tuple[int, int, int, int, int, int]:
    archive = _mapping(value, field="archive")
    string_fields = {
        "compression": "stored",
        "comment": "",
        "extra": "",
        "member_comment": "",
        "external_attributes_octal": "100644",
    }
    for string_field, string_expected in string_fields.items():
        if _string(archive.get(string_field), field=f"archive.{string_field}") != string_expected:
            raise ValueError(f"archive.{string_field} must be {string_expected!r}")
    integer_fields = {
        "create_system": ZIP_CREATE_SYSTEM,
        "create_version": ZIP_CREATE_VERSION,
        "extract_version": ZIP_EXTRACT_VERSION,
        "flag_bits": 0,
        "internal_attributes": 0,
        "reserved": 0,
        "volume": 0,
    }
    for integer_field, integer_expected in integer_fields.items():
        if (
            _integer(archive.get(integer_field), field=f"archive.{integer_field}")
            != integer_expected
        ):
            raise ValueError(f"archive.{integer_field} must be {integer_expected}")

    timestamp_values = _sequence(archive.get("timestamp"), field="archive.timestamp")
    if len(timestamp_values) != TIMESTAMP_COMPONENT_COUNT:
        raise ValueError("archive.timestamp must contain six integers")
    values = tuple(
        _integer(component, field=f"archive.timestamp[{index}]")
        for index, component in enumerate(timestamp_values)
    )
    timestamp = (values[0], values[1], values[2], values[3], values[4], values[5])
    if timestamp != FIXED_TIMESTAMP:
        raise ValueError(f"archive.timestamp must be {FIXED_TIMESTAMP!r}")
    return timestamp


def _expected_package(value: object) -> tuple[int, str]:
    package = _mapping(value, field="expected_package")
    if _string(package.get("path"), field="expected_package.path") != EXPECTED_PACKAGE_PATH:
        raise ValueError(f"expected_package.path must be {EXPECTED_PACKAGE_PATH!r}")
    expected_size = _integer(package.get("bytes"), field="expected_package.bytes")
    if expected_size <= 0:
        raise ValueError("expected_package.bytes must be positive")
    return expected_size, _sha256(package.get("sha256"), field="expected_package.sha256")


def _source_entries(value: object) -> tuple[SourceEntry, ...]:
    entry_values = _sequence(value, field="entries")
    if not entry_values:
        raise ValueError("entries must not be empty")
    entries: list[SourceEntry] = []
    names: set[str] = set()
    for index, entry_value in enumerate(entry_values):
        item = _mapping(entry_value, field=f"entries[{index}]")
        path = _member_path(item.get("path"), field=f"entries[{index}].path")
        if path in names:
            raise ValueError(f"duplicate manifest member: {path}")
        names.add(path)
        size = _integer(item.get("bytes"), field=f"entries[{index}].bytes")
        if size < 0:
            raise ValueError(f"entries[{index}].bytes must not be negative")
        entries.append(
            SourceEntry(
                path=path,
                size=size,
                sha256=_sha256(item.get("sha256"), field=f"entries[{index}].sha256"),
            )
        )
    return tuple(entries)


def load_manifest(source_dir: Path = DEFAULT_SOURCE_DIR) -> DemoManifest:
    """Load and strictly validate the canonical source manifest."""

    manifest_path = Path(source_dir) / MANIFEST_NAME
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError(f"manifest must be a regular file: {manifest_path}")
    loaded: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = _mapping(loaded, field="manifest")
    if _integer(root.get("schema_version"), field="schema_version") != 1:
        raise ValueError("schema_version must be 1")

    timestamp = _archive_contract(root.get("archive"))
    expected_size, expected_sha256 = _expected_package(root.get("expected_package"))
    entries = _source_entries(root.get("entries"))
    return DemoManifest(
        timestamp=timestamp,
        expected_size=expected_size,
        expected_sha256=expected_sha256,
        entries=entries,
    )


def _canonical_payload(source_root: Path, entry: SourceEntry) -> bytes:
    root = source_root.resolve(strict=True)
    candidate = source_root.joinpath(*PurePosixPath(entry.path).parts)
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError(f"canonical source member must be a regular file: {entry.path}")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError(f"canonical source member escapes the source directory: {entry.path}")
    payload_with_newline = resolved.read_bytes()
    if not payload_with_newline.endswith(b"\n") or payload_with_newline[:-1].endswith(
        (b"\n", b"\r")
    ):
        raise ValueError(
            f"canonical source member must end in exactly one repository newline: {entry.path}"
        )
    payload = payload_with_newline[:-1]
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"canonical source member is not UTF-8 text: {entry.path}") from exc
    if len(payload) != entry.size:
        raise ValueError(
            f"canonical source size mismatch for {entry.path}: {len(payload)} != {entry.size}"
        )
    digest = hashlib.sha256(payload).hexdigest()
    if digest != entry.sha256:
        raise ValueError(
            f"canonical source digest mismatch for {entry.path}: {digest} != {entry.sha256}"
        )
    return payload


def _validate_source_inventory(source_dir: Path, manifest: DemoManifest) -> None:
    if source_dir.is_symlink() or not source_dir.is_dir():
        raise ValueError(f"canonical source directory must be a regular directory: {source_dir}")
    expected = {entry.path for entry in manifest.entries}
    observed = {
        path.relative_to(source_dir).as_posix()
        for path in source_dir.rglob("*")
        if path.is_file() and path.relative_to(source_dir).as_posix() != MANIFEST_NAME
    }
    if observed != expected:
        raise ValueError(
            "canonical source inventory mismatch: "
            f"missing={sorted(expected - observed)!r}, extra={sorted(observed - expected)!r}"
        )


def _write_archive(source_dir: Path, destination: BinaryIO, manifest: DemoManifest) -> None:
    with zipfile.ZipFile(
        destination,
        mode="w",
        compression=zipfile.ZIP_STORED,
        allowZip64=False,
        strict_timestamps=True,
    ) as archive:
        archive.comment = b""
        for entry in manifest.entries:
            info = zipfile.ZipInfo(entry.path, date_time=manifest.timestamp)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = ZIP_CREATE_SYSTEM
            info.create_version = ZIP_CREATE_VERSION
            info.extract_version = ZIP_EXTRACT_VERSION
            info.flag_bits = 0
            info.external_attr = ZIP_EXTERNAL_ATTR
            info.internal_attr = 0
            info.reserved = 0
            info.volume = 0
            info.extra = b""
            info.comment = b""
            archive.writestr(info, _canonical_payload(source_dir, entry))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_built_package(path: Path, manifest: DemoManifest) -> None:
    size = path.stat().st_size
    digest = _file_sha256(path)
    if (size, digest) != (manifest.expected_size, manifest.expected_sha256):
        raise ValueError(
            "rebuilt package does not match the manifest: "
            f"bytes={size}, sha256={digest}, expected_bytes={manifest.expected_size}, "
            f"expected_sha256={manifest.expected_sha256}"
        )


def _ownership(path: Path, identity: FileIdentity) -> str:
    if not os.path.lexists(path):
        return "absent"
    try:
        details = path.lstat()
    except FileNotFoundError:
        return "absent"
    if not stat.S_ISREG(details.st_mode):
        return "foreign"
    if (details.st_dev, details.st_ino) == (identity.device, identity.inode):
        return "owned"
    return "foreign"


def _require_owned(path: Path, identity: FileIdentity, *, operation: str) -> None:
    if _ownership(path, identity) != "owned":
        raise RuntimeError(f"demo staging path changed before {operation}")


def _is_transient_unlink_error(error: OSError) -> bool:
    return (
        error.errno in TRANSIENT_UNLINK_ERRNOS
        or getattr(error, "winerror", None) in TRANSIENT_UNLINK_WINERRORS
    )


def _unlink_owned_with_retry(path: Path, identity: FileIdentity) -> str:
    attempts = len(UNLINK_RETRY_DELAYS_SECONDS) + 1
    for attempt in range(attempts):
        ownership = _ownership(path, identity)
        if ownership != "owned":
            return ownership
        try:
            path.unlink()
        except FileNotFoundError:
            return "absent"
        except OSError as error:
            if not _is_transient_unlink_error(error) or attempt == attempts - 1:
                raise
            time.sleep(UNLINK_RETRY_DELAYS_SECONDS[attempt])
            continue
        ownership = _ownership(path, identity)
        if ownership != "owned":
            return ownership
        if attempt == attempts - 1:
            raise OSError(errno.EBUSY, "owned path reappeared during cleanup", str(path))
        time.sleep(UNLINK_RETRY_DELAYS_SECONDS[attempt])
    raise AssertionError("unreachable unlink retry state")


def _raise_publication_cleanup_error(
    stage: Path,
    destination: Path,
    identity: FileIdentity,
    stage_error: OSError | None,
) -> None:
    failures: list[str] = []
    try:
        output_cleanup_state = _unlink_owned_with_retry(destination, identity)
    except OSError as rollback_error:
        output_cleanup_state = _ownership(destination, identity)
        failures.append(f"destination rollback failed: {rollback_error}")
    try:
        stage_cleanup_state = _unlink_owned_with_retry(stage, identity)
    except OSError as cleanup_error:
        stage_cleanup_state = _ownership(stage, identity)
        failures.append(f"staging cleanup failed: {cleanup_error}")
    if output_cleanup_state == "foreign":
        failures.append("foreign destination replacement was preserved")
    elif output_cleanup_state == "owned":
        failures.append("owned destination remains")
    else:
        failures.append("owned destination was rolled back")
    if stage_cleanup_state == "foreign":
        failures.append("foreign staging replacement was preserved")
    elif stage_cleanup_state == "owned":
        failures.append("owned staging file remains")
    else:
        failures.append("staging file is absent")
    cause = stage_error
    raise RuntimeError("demo publication cleanup was incomplete; " + "; ".join(failures)) from cause


def _publish_no_clobber(stage: Path, destination: Path, identity: FileIdentity) -> None:
    _require_owned(stage, identity, operation="publication")
    os.link(stage, destination)
    if _ownership(destination, identity) != "owned":
        _raise_publication_cleanup_error(stage, destination, identity, None)
    try:
        stage_state = _unlink_owned_with_retry(stage, identity)
    except OSError as cleanup_error:
        _raise_publication_cleanup_error(stage, destination, identity, cleanup_error)
    if stage_state != "absent" or _ownership(destination, identity) != "owned":
        _raise_publication_cleanup_error(stage, destination, identity, None)


def _verify_published_package(
    destination: Path,
    manifest: DemoManifest,
    identity: FileIdentity,
) -> None:
    if _ownership(destination, identity) != "owned":
        raise RuntimeError("foreign destination replacement was preserved after publication")
    try:
        _verify_built_package(destination, manifest)
    except BaseException:
        try:
            cleanup_state = _unlink_owned_with_retry(destination, identity)
        except OSError as cleanup_error:
            raise RuntimeError(
                f"published demo verification failed and cleanup was incomplete: {destination}"
            ) from cleanup_error
        if cleanup_state == "foreign":
            raise RuntimeError(
                f"published demo verification failed; a foreign replacement was preserved: "
                f"{destination}"
            ) from None
        raise
    if _ownership(destination, identity) != "owned":
        raise RuntimeError("foreign destination replacement was preserved after verification")


def build_demo(
    source_dir: Path,
    destination: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Build and verify the canonical demo without leaving a partial output."""

    source_dir = Path(source_dir)
    destination = Path(destination)
    if destination.suffix.lower() != ".pptx":
        raise ValueError("demo destination must use the .pptx extension")
    if destination.is_symlink():
        raise ValueError("demo destination must not be a symbolic link")
    manifest = load_manifest(source_dir)
    _validate_source_inventory(source_dir, manifest)
    source_root = source_dir.resolve(strict=True)
    if destination.resolve(strict=False).is_relative_to(source_root):
        raise ValueError("demo destination must be outside the canonical source directory")
    destination.parent.mkdir(parents=True, exist_ok=True)

    if not overwrite and (destination.exists() or destination.is_symlink()):
        raise FileExistsError(f"demo destination already exists: {destination}")

    descriptor, stage_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    stage = Path(stage_name)
    stage_details = os.fstat(descriptor)
    stage_identity = FileIdentity(device=stage_details.st_dev, inode=stage_details.st_ino)
    try:
        with os.fdopen(descriptor, mode="w+b") as staging_handle:
            _write_archive(source_dir, staging_handle, manifest)
            staging_handle.flush()
            os.fsync(staging_handle.fileno())
        _require_owned(stage, stage_identity, operation="verification")
        _verify_built_package(stage, manifest)
        _require_owned(stage, stage_identity, operation="publication")
        if overwrite:
            stage.replace(destination)
        else:
            _publish_no_clobber(stage, destination, stage_identity)
        _verify_published_package(destination, manifest, stage_identity)
    except BaseException:
        try:
            cleanup_state = _unlink_owned_with_retry(stage, stage_identity)
        except OSError as cleanup_error:
            raise RuntimeError(
                f"demo rebuild failed and staging cleanup was incomplete: {stage}"
            ) from cleanup_error
        if cleanup_state == "foreign":
            raise RuntimeError(
                f"demo rebuild failed; a foreign staging replacement was preserved: {stage}"
            ) from None
        raise
    cleanup_state = _unlink_owned_with_retry(stage, stage_identity)
    if cleanup_state == "foreign":
        raise RuntimeError(f"foreign staging replacement was preserved after success: {stage}")
    return destination


def check_demo(
    source_dir: Path = DEFAULT_SOURCE_DIR,
    committed_demo: Path = DEFAULT_COMMITTED_DEMO,
) -> None:
    """Prove that canonical source rebuilds the committed deck byte for byte."""

    with tempfile.TemporaryDirectory(prefix="pptrans-demo-rebuild-") as directory:
        rebuilt = Path(directory) / committed_demo.name
        build_demo(source_dir, rebuilt)
        if rebuilt.read_bytes() != committed_demo.read_bytes():
            raise ValueError(f"rebuilt demo is not byte-identical to {committed_demo}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", nargs="?", type=Path, help="New .pptx output path")
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help="Canonical OOXML source directory",
    )
    parser.add_argument(
        "--committed-demo",
        type=Path,
        default=DEFAULT_COMMITTED_DEMO,
        help="Committed deck used by --check",
    )
    parser.add_argument("--check", action="store_true", help="Verify an exact canonical rebuild")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing output")
    args = parser.parse_args(argv)
    if args.check:
        if args.destination is not None or args.overwrite:
            parser.error("--check cannot be combined with destination or --overwrite")
        check_demo(args.source_dir, args.committed_demo)
        manifest = load_manifest(args.source_dir)
        print(
            json.dumps(
                {
                    "bytes": manifest.expected_size,
                    "entries": len(manifest.entries),
                    "result": "byte-identical",
                    "sha256": manifest.expected_sha256,
                    "source": str(args.source_dir),
                },
                ensure_ascii=True,
                separators=(",", ":"),
            )
        )
        return 0
    if args.destination is None:
        parser.error("destination is required unless --check is used")
    built = build_demo(args.source_dir, args.destination, overwrite=args.overwrite)
    print(
        json.dumps(
            {
                "bytes": built.stat().st_size,
                "output": str(built),
                "sha256": _file_sha256(built),
            },
            ensure_ascii=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
