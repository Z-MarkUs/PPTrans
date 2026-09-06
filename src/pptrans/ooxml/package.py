"""Safe, copy-on-write access to PPTX OPC packages."""

from __future__ import annotations

import posixpath
import stat
import zipfile
import zlib
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import unquote

from pptrans.domain.errors import InvalidPresentationError
from pptrans.domain.models import PackageLimits

from .xml import NS, parse_xml


def file_sha256(path: Path) -> str:
    """Return a streaming SHA-256 digest for *path*."""

    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_distinct_package_paths(source: Path, destination: Path) -> None:
    """Reject lexical, resolved, symlink, and hard-link aliases before any write."""

    source_path = Path(source)
    destination_path = Path(destination)
    try:
        resolved_alias = source_path.resolve(strict=False) == destination_path.resolve(strict=False)
    except OSError:
        resolved_alias = source_path.absolute() == destination_path.absolute()
    inode_alias = False
    with suppress(FileNotFoundError, OSError):
        inode_alias = source_path.samefile(destination_path)
    if resolved_alias or inode_alias:
        raise InvalidPresentationError(
            "Source and destination PPTX paths must identify different files."
        )


def ensure_package_destination_available(destination: Path, *, overwrite: bool) -> None:
    """Reject an existing destination unless replacement was explicitly requested."""

    destination_path = Path(destination)
    if destination_path.is_symlink():
        raise InvalidPresentationError("Destination PPTX must not be a symbolic link.")
    if not overwrite and destination_path.exists():
        raise FileExistsError(f"Destination PPTX already exists: {destination_path}")


def _validate_member_name(name: str) -> None:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    has_drive_prefix = bool(path.parts and path.parts[0].endswith(":"))
    if (
        not name
        or "\x00" in name
        or "\\" in name
        or normalized.startswith("/")
        or ".." in path.parts
        or has_drive_prefix
    ):
        raise InvalidPresentationError(f"Unsafe package member path: {name!r}")


def validate_archive(archive: zipfile.ZipFile, limits: PackageLimits) -> None:
    """Validate member paths, encryption flags, duplication, and size bounds."""

    infos = archive.infolist()
    if len(infos) > limits.max_members:
        raise InvalidPresentationError(
            f"PPTX has {len(infos)} members; limit is {limits.max_members}."
        )

    names: set[str] = set()
    total = 0
    for info in infos:
        _validate_member_name(info.filename)
        if info.filename.lower().startswith("_xmlsignatures/"):
            raise InvalidPresentationError(
                "Digitally signed PPTX packages are not supported because translation "
                "would invalidate their signatures."
            )
        if info.filename in names:
            raise InvalidPresentationError(f"Duplicate package member: {info.filename!r}")
        names.add(info.filename)
        if info.flag_bits & 0x1:
            raise InvalidPresentationError("Encrypted PPTX packages are not supported.")
        member_type = (info.external_attr >> 16) & 0o170000
        if member_type == stat.S_IFLNK:
            raise InvalidPresentationError(
                f"Symbolic-link package members are not supported: {info.filename!r}"
            )
        if info.filename.lower().endswith((".xml", ".rels")) and (
            info.file_size > limits.max_xml_bytes
        ):
            raise InvalidPresentationError(
                f"XML package member {info.filename!r} exceeds the XML safety limit."
            )
        if info.file_size > limits.max_member_bytes:
            raise InvalidPresentationError(
                f"Package member {info.filename!r} exceeds the size limit."
            )
        total += info.file_size
        if total > limits.max_total_bytes:
            raise InvalidPresentationError("PPTX uncompressed size exceeds the safety limit.")
        if (
            info.compress_size
            and info.file_size / info.compress_size > limits.max_compression_ratio
        ):
            raise InvalidPresentationError(
                f"Package member {info.filename!r} exceeds the compression-ratio limit."
            )

    missing = limits.required_members.difference(names)
    if missing:
        raise InvalidPresentationError(
            "PPTX is missing required package members: " + ", ".join(sorted(missing))
        )


def validate_archive_payloads(archive: zipfile.ZipFile) -> None:
    """Read every member so corrupt opaque payloads fail before provider work."""

    try:
        invalid_member = archive.testzip()
    except (EOFError, OSError, RuntimeError, zipfile.BadZipFile, zlib.error) as exc:
        raise InvalidPresentationError("PPTX package payload integrity check failed.") from exc
    if invalid_member is not None:
        raise InvalidPresentationError(
            f"PPTX package member failed its CRC check: {invalid_member!r}"
        )


def read_xml_part(
    archive: zipfile.ZipFile,
    part_name: str,
    limits: PackageLimits | None = None,
) -> bytes:
    """Read one XML-bearing part under the XML ceiling, regardless of its suffix."""

    policy = limits or PackageLimits()
    try:
        info = archive.getinfo(part_name)
    except KeyError as exc:
        raise InvalidPresentationError(f"Referenced XML part is missing: {part_name!r}") from exc
    if info.file_size > policy.max_xml_bytes:
        raise InvalidPresentationError(
            f"XML package member {part_name!r} exceeds the XML safety limit."
        )
    try:
        payload = archive.read(info)
    except (OSError, RuntimeError, zipfile.BadZipFile, zlib.error) as exc:
        raise InvalidPresentationError(
            f"XML package member {part_name!r} could not be read safely."
        ) from exc
    if len(payload) > policy.max_xml_bytes:
        raise InvalidPresentationError(
            f"XML package member {part_name!r} exceeds the XML safety limit."
        )
    return payload


@contextmanager
def open_package(path: Path, limits: PackageLimits | None = None) -> Iterator[zipfile.ZipFile]:
    """Open and validate a supported PPTX package."""

    path = Path(path)
    if path.suffix.lower() != ".pptx":
        raise InvalidPresentationError(
            f"Only .pptx files are supported by the formatting-safe engine: {path.name!r}."
        )
    if not path.is_file():
        raise InvalidPresentationError(f"PPTX file does not exist: {path}")

    try:
        archive = zipfile.ZipFile(path, mode="r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise InvalidPresentationError(f"Not a readable PPTX package: {path}") from exc

    try:
        validate_archive(archive, limits or PackageLimits())
        yield archive
    finally:
        archive.close()


def _resolve_part(base_part: str, target: str) -> str:
    decoded = unquote(target).replace("\\", "/")
    if decoded.startswith("/"):
        candidate = decoded.lstrip("/")
    else:
        candidate = posixpath.normpath(posixpath.join(posixpath.dirname(base_part), decoded))
    _validate_member_name(candidate)
    return candidate


def discover_slide_parts(
    archive: zipfile.ZipFile,
    limits: PackageLimits | None = None,
) -> tuple[str, ...]:
    """Return slide part names in presentation order."""

    presentation_name = "ppt/presentation.xml"
    relationships_name = "ppt/_rels/presentation.xml.rels"
    presentation = parse_xml(
        read_xml_part(archive, presentation_name, limits), part_name=presentation_name
    )
    relationships = parse_xml(
        read_xml_part(archive, relationships_name, limits), part_name=relationships_name
    )

    targets: dict[str, str] = {}
    relationship_ids: set[str] = set()
    for relationship in relationships.findall("rel:Relationship", NS):
        rel_id = relationship.get("Id")
        if rel_id is not None:
            if rel_id in relationship_ids:
                raise InvalidPresentationError(
                    f"Presentation relationships repeat relationship ID {rel_id!r}."
                )
            relationship_ids.add(rel_id)
        if relationship.get("TargetMode") == "External":
            continue
        rel_type = relationship.get("Type", "")
        target = relationship.get("Target")
        if rel_id and target and rel_type.rsplit("/", 1)[-1] == "slide":
            targets[rel_id] = _resolve_part(presentation_name, target)

    parts: list[str] = []
    slide_relationship_ids: set[str] = set()
    slide_parts: set[str] = set()
    for slide_id in presentation.findall("./p:sldIdLst/p:sldId", NS):
        rel_id = slide_id.get(f"{{{NS['r']}}}id")
        if not rel_id or rel_id not in targets:
            raise InvalidPresentationError(
                "A presentation slide has no internal slide relationship."
            )
        if rel_id in slide_relationship_ids:
            raise InvalidPresentationError(
                f"Presentation slide list repeats relationship reference {rel_id!r}."
            )
        slide_relationship_ids.add(rel_id)
        part = targets[rel_id]
        if part in slide_parts:
            raise InvalidPresentationError(
                f"Presentation slide list repeats slide part reference {part!r}."
            )
        slide_parts.add(part)
        if part not in archive.namelist():
            raise InvalidPresentationError(f"Referenced slide part is missing: {part!r}")
        parts.append(part)
    return tuple(parts)


def rewrite_package(
    source: Path,
    destination: Path,
    replacements: Mapping[str, bytes],
    *,
    limits: PackageLimits | None = None,
    overwrite: bool = False,
) -> None:
    """Copy package members without replacing an existing destination by default."""

    ensure_distinct_package_paths(source, destination)
    ensure_package_destination_available(destination, overwrite=overwrite)
    limits = limits or PackageLimits()
    with open_package(source, limits) as source_zip:
        source_names = set(source_zip.namelist())
        unknown = set(replacements).difference(source_names)
        if unknown:
            raise InvalidPresentationError(
                "Cannot replace missing package members: " + ", ".join(sorted(unknown))
            )
        try:
            mode: Literal["w", "x"] = "w" if overwrite else "x"
            with zipfile.ZipFile(destination, mode=mode) as output_zip:
                output_zip.comment = source_zip.comment
                for info in source_zip.infolist():
                    payload = replacements.get(info.filename)
                    if payload is None:
                        payload = source_zip.read(info)
                    output_zip.writestr(info, payload)
        except FileExistsError:
            raise
        except (OSError, zipfile.BadZipFile) as exc:
            raise InvalidPresentationError(
                f"Could not stage translated PPTX: {destination}"
            ) from exc


def package_member_hashes(path: Path) -> dict[str, str]:
    """Return uncompressed content hashes for all members of a valid package."""

    with open_package(path) as archive:
        return {name: sha256(archive.read(name)).hexdigest() for name in archive.namelist()}
