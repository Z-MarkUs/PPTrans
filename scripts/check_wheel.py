"""Fail if PPTrans distributions omit evidence or contain private artifacts."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

REQUIRED_SUFFIXES = {
    "pptrans/__init__.py",
    "pptrans/cli.py",
    "pptrans/py.typed",
}
DEMO_SOURCE_PREFIX = "examples/pptrans-demo.source/"
DEMO_MANIFEST_SUFFIX = DEMO_SOURCE_PREFIX + "manifest.json"
DEMO_SOURCE_DECK_SUFFIX = "examples/pptrans-demo.en.pptx"
SHA256_HEX_LENGTH = 64
DEMO_FIXED_TIMESTAMP = [2026, 8, 28, 0, 34, 0]
CURRENT_QA_SUFFIX = "docs/qa/2026-08-31-exact-rebuild.json"
CURRENT_QA_CANONICAL_SHA256 = "cfbc19be0c3d7beaddbdf63574db21a9e79314702183b9a9b227131ca1162462"
PNG_HEADER_BYTES = 24
SDIST_REQUIRED_SUFFIXES = {
    ".agents/skills/pptrans-engineering/agents/openai.yaml",
    ".agents/skills/pptrans-engineering/references/architecture.md",
    ".agents/skills/pptrans-engineering/references/release.md",
    ".agents/skills/pptrans-engineering/references/verification.md",
    ".agents/skills/pptrans-engineering/SKILL.md",
    ".claude/skills/pptrans-engineering/agents/openai.yaml",
    ".claude/skills/pptrans-engineering/references/architecture.md",
    ".claude/skills/pptrans-engineering/references/release.md",
    ".claude/skills/pptrans-engineering/references/verification.md",
    ".claude/skills/pptrans-engineering/SKILL.md",
    "README.md",
    "README.zh-CN.md",
    "benchmarks/README.md",
    "benchmarks/results/2026-08-28-windows-python312.json",
    "benchmarks/results/2026-08-31-windows-python312.json",
    "benchmarks/results/2026-08-31-stored-ooxml-windows-python312.json",
    "docs/ARCHITECTURE.md",
    "docs/DEMO.md",
    "docs/assets/pptrans-demo-libreoffice-en-slide-01.png",
    "docs/assets/pptrans-demo-libreoffice-en-slide-02.png",
    "docs/assets/pptrans-demo-libreoffice-en-slide-03.png",
    "docs/assets/pptrans-demo-libreoffice-zh-CN-slide-01.png",
    "docs/assets/pptrans-demo-libreoffice-zh-CN-slide-02.png",
    "docs/assets/pptrans-demo-libreoffice-zh-CN-slide-03.png",
    "docs/qa/2026-08-28-curated-zh-cn.json",
    "docs/qa/2026-08-28-windows-libreoffice.json",
    CURRENT_QA_SUFFIX,
    "examples/pptrans-demo.source/manifest.json",
    "examples/pptrans-demo.en.pptx",
    "examples/pptrans-demo.zh-CN.pptx",
    "scripts/build_curated_demo.py",
    "scripts/check_doc_links.py",
    "scripts/check_installed_version.py",
    "scripts/check_minimal_install.py",
    "scripts/check_release_policy.py",
    "scripts/rebuild_demo.py",
    "scripts/reproduce_native_demo.py",
    "tests/test_demo_rebuild.py",
    "tests/test_provider_sdk_wire_contracts.py",
    "tests/test_public_demo.py",
    "tests/typecheck_provider_exports.py",
}
FORBIDDEN_FRAGMENTS = {
    ".env",
    ".ppt",
    ".pptx",
    ".pyc",
    ".sqlite3",
    "ppt_translator/",
    "tests/",
}
SDIST_FORBIDDEN_PATHS = {
    ".env",
    "scripts/build_demo.mjs",
    "scripts/render_demo_comparison.mjs",
    "scripts/sanitize_demo_metadata.py",
    "docs/assets/pptrans-demo-preview.webp",
    "docs/assets/pptrans-demo-source-slide-01.webp",
    "docs/assets/pptrans-demo-source-slide-02.webp",
    "docs/assets/pptrans-demo-source-slide-03.webp",
    "docs/assets/pptrans-demo-zh-CN-slide-01.webp",
    "docs/assets/pptrans-demo-zh-CN-slide-02.webp",
    "docs/assets/pptrans-demo-zh-CN-slide-03.webp",
}
SDIST_FORBIDDEN_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "ppt_translator",
}
SQLITE_SUFFIXES = (".db", ".sqlite", ".sqlite3")
SQLITE_SIDECARS = ("-journal", "-shm", "-wal")
PACKAGED_REBUILD_TIMEOUT_SECONDS = 60


def inspect_wheel(path: Path) -> tuple[str, ...]:
    """Return validation failures for one wheel."""

    if not path.is_file() or path.suffix != ".whl":
        return (f"not a wheel: {path}",)
    with zipfile.ZipFile(path) as archive:
        infos = tuple(archive.infolist())
        members = tuple(info.orig_filename for info in infos)
    failures = [
        f"missing required wheel member: {required}"
        for required in sorted(REQUIRED_SUFFIXES)
        if not any(info.orig_filename == required and not info.is_dir() for info in infos)
    ]
    failures.extend(
        f"unsafe wheel member: {member}"
        for member in members
        if "\\" in member
        or PurePosixPath(member).is_absolute()
        or ".." in PurePosixPath(member).parts
    )
    if len(set(members)) != len(members):
        failures.append("wheel contains duplicate member names")
    failures.extend(
        f"forbidden wheel member: {member}"
        for member in members
        if any(fragment in member.casefold() for fragment in FORBIDDEN_FRAGMENTS)
    )
    return tuple(failures)


def _forbidden_sdist_path(relative: str) -> bool:
    path = PurePosixPath(relative)
    folded_relative = relative.casefold()
    folded_parts = tuple(part.casefold() for part in path.parts)
    filename = path.name.casefold()
    dotenv = filename.startswith(".env") and folded_relative != ".env.example"
    sqlite = any(
        filename.endswith(suffix)
        or any(filename.endswith(suffix + sidecar) for sidecar in SQLITE_SIDECARS)
        for suffix in SQLITE_SUFFIXES
    )
    return (
        folded_relative in SDIST_FORBIDDEN_PATHS
        or any(part in SDIST_FORBIDDEN_PARTS or part.startswith(".tmp-") for part in folded_parts)
        or path.suffix.lower() in {".pyc", ".pyo"}
        or dotenv
        or sqlite
    )


def _read_tar_member(archive: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    handle = archive.extractfile(member)
    if handle is None:
        raise ValueError(f"source-distribution member is not readable: {member.name}")
    return handle.read()


def _validate_demo_archive_contract(value: object) -> None:
    if not isinstance(value, dict):
        raise TypeError("source distribution demo archive contract must be an object")
    string_fields = {
        "compression": "stored",
        "comment": "",
        "extra": "",
        "member_comment": "",
        "external_attributes_octal": "100644",
    }
    for string_field, string_expected in string_fields.items():
        if value.get(string_field) != string_expected:
            raise ValueError(
                f"source distribution demo archive.{string_field} must be {string_expected!r}"
            )
    integer_fields = {
        "create_system": 3,
        "create_version": 20,
        "extract_version": 20,
        "flag_bits": 0,
        "internal_attributes": 0,
        "reserved": 0,
        "volume": 0,
    }
    for integer_field, integer_expected in integer_fields.items():
        observed = value.get(integer_field)
        if (
            not isinstance(observed, int)
            or isinstance(observed, bool)
            or observed != integer_expected
        ):
            raise ValueError(
                f"source distribution demo archive.{integer_field} must be {integer_expected}"
            )
    timestamp = value.get("timestamp")
    if (
        not isinstance(timestamp, list)
        or any(not isinstance(part, int) or isinstance(part, bool) for part in timestamp)
        or timestamp != DEMO_FIXED_TIMESTAMP
    ):
        raise ValueError(
            f"source distribution demo archive.timestamp must be {DEMO_FIXED_TIMESTAMP!r}"
        )


def _manifest_object(manifest_payload: bytes) -> dict[str, object]:
    try:
        loaded: object = json.loads(manifest_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"source distribution demo manifest is invalid: {exc}") from exc
    if not isinstance(loaded, dict) or not all(isinstance(key, str) for key in loaded):
        raise TypeError("source distribution demo manifest must be an object with string keys")
    return loaded


def _demo_entries(entries_value: object) -> tuple[tuple[str, int, str], ...]:
    if not isinstance(entries_value, list) or not entries_value:
        raise ValueError("source distribution demo manifest entries must be a non-empty array")
    entries: list[tuple[str, int, str]] = []
    seen: set[str] = set()
    for index, value in enumerate(entries_value):
        if not isinstance(value, dict):
            raise TypeError(f"source distribution demo entry {index} must be an object")
        member_path = value.get("path")
        size = value.get("bytes")
        digest = value.get("sha256")
        pure = PurePosixPath(member_path) if isinstance(member_path, str) else None
        if (
            pure is None
            or not member_path
            or not member_path.isascii()
            or "\\" in member_path
            or pure.is_absolute()
            or any(part in {"", ".", ".."} for part in pure.parts)
        ):
            raise ValueError(f"source distribution demo entry {index} has an unsafe path")
        normalized = pure.as_posix()
        if normalized in seen:
            raise ValueError(f"source distribution demo manifest duplicates {normalized}")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ValueError(f"source distribution demo entry {index} has an invalid size")
        if (
            not isinstance(digest, str)
            or len(digest) != SHA256_HEX_LENGTH
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError(f"source distribution demo entry {index} has an invalid SHA-256")
        seen.add(normalized)
        entries.append((normalized, size, digest))
    return tuple(entries)


def _demo_package(value: object) -> tuple[int, str]:
    package = value
    if not isinstance(package, dict) or package.get("path") != DEMO_SOURCE_DECK_SUFFIX:
        raise ValueError("source distribution demo manifest has an invalid package path")
    package_size = package.get("bytes")
    package_digest = package.get("sha256")
    if not isinstance(package_size, int) or isinstance(package_size, bool) or package_size <= 0:
        raise ValueError("source distribution demo manifest has an invalid package size")
    if (
        not isinstance(package_digest, str)
        or len(package_digest) != SHA256_HEX_LENGTH
        or any(character not in "0123456789abcdef" for character in package_digest)
    ):
        raise ValueError("source distribution demo manifest has an invalid package SHA-256")
    return package_size, package_digest


def _demo_contract(manifest_payload: bytes) -> tuple[tuple[tuple[str, int, str], ...], int, str]:
    manifest = _manifest_object(manifest_payload)
    try:
        entries_value = manifest["entries"]
        package_value = manifest["expected_package"]
        archive_contract = manifest["archive"]
    except KeyError as exc:
        raise ValueError(f"source distribution demo manifest is missing {exc}") from exc
    schema_version = manifest.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != 1
    ):
        raise ValueError("source distribution demo schema_version must be 1")
    _validate_demo_archive_contract(archive_contract)
    entries = _demo_entries(entries_value)
    package_size, package_digest = _demo_package(package_value)
    return entries, package_size, package_digest


def _source_payload_failures(
    archive: tarfile.TarFile,
    source_members: dict[str, tarfile.TarInfo],
    entries: tuple[tuple[str, int, str], ...],
) -> list[str]:
    failures: list[str] = []
    for member_path, expected_size, expected_digest in entries:
        source_member = source_members.get(member_path)
        if source_member is None:
            continue
        payload_with_newline = _read_tar_member(archive, source_member)
        if not payload_with_newline.endswith(b"\n") or payload_with_newline[:-1].endswith(
            (b"\n", b"\r")
        ):
            failures.append(
                f"source distribution demo member has invalid LF framing: {member_path}"
            )
            continue
        payload = payload_with_newline[:-1]
        try:
            payload.decode("utf-8")
        except UnicodeDecodeError:
            failures.append(f"source distribution demo member is not UTF-8: {member_path}")
            continue
        digest = hashlib.sha256(payload).hexdigest()
        if (len(payload), digest) != (expected_size, expected_digest):
            failures.append(f"source distribution demo member differs from manifest: {member_path}")
    return failures


def _source_deck_failures(
    archive: tarfile.TarFile,
    archive_members: tuple[tarfile.TarInfo, ...],
    members: tuple[str, ...],
    expected_member_name: str,
    expected_package: tuple[int, str],
) -> list[str]:
    deck_members = [
        member
        for member, normalized in zip(archive_members, members, strict=True)
        if member.isfile() and normalized == expected_member_name
    ]
    if len(deck_members) != 1:
        return ["source distribution must contain exactly one regular English demo deck"]
    deck = _read_tar_member(archive, deck_members[0])
    if (len(deck), hashlib.sha256(deck).hexdigest()) != expected_package:
        return ["source distribution English demo deck differs from its manifest"]
    return []


def _demo_source_failures(
    archive: tarfile.TarFile,
    archive_members: tuple[tarfile.TarInfo, ...],
    members: tuple[str, ...],
) -> tuple[str, ...]:
    manifest_members = [
        (member, normalized)
        for member, normalized in zip(archive_members, members, strict=True)
        if member.isfile() and normalized.endswith(DEMO_MANIFEST_SUFFIX)
    ]
    if len(manifest_members) != 1:
        return ("source distribution must contain exactly one regular demo manifest",)
    manifest_member, manifest_name = manifest_members[0]
    distribution_root = manifest_name[: -len(DEMO_MANIFEST_SUFFIX)]
    expected_source_prefix = distribution_root + DEMO_SOURCE_PREFIX
    expected_deck_name = distribution_root + DEMO_SOURCE_DECK_SUFFIX
    try:
        entries, package_size, package_digest = _demo_contract(
            _read_tar_member(archive, manifest_member)
        )
    except (TypeError, ValueError) as exc:
        return (str(exc),)

    failures: list[str] = []
    misrooted_demo_members = [
        normalized
        for member, normalized in zip(archive_members, members, strict=True)
        if member.isfile()
        and (DEMO_SOURCE_PREFIX in normalized or normalized.endswith(DEMO_SOURCE_DECK_SUFFIX))
        and not (normalized.startswith(expected_source_prefix) or normalized == expected_deck_name)
    ]
    if misrooted_demo_members:
        failures.append("source distribution demo members do not share one distribution root")
    source_members: dict[str, tarfile.TarInfo] = {}
    for member, normalized in zip(archive_members, members, strict=True):
        if not member.isfile() or not normalized.startswith(expected_source_prefix):
            continue
        relative = normalized[len(expected_source_prefix) :]
        if relative in source_members:
            failures.append(f"duplicate source-distribution demo member: {relative}")
        else:
            source_members[relative] = member
    expected_source_files = {"manifest.json", *(path for path, _, _ in entries)}
    if set(source_members) != expected_source_files:
        failures.append("source distribution demo source inventory differs from its manifest")

    failures.extend(_source_payload_failures(archive, source_members, entries))
    failures.extend(
        _source_deck_failures(
            archive,
            archive_members,
            members,
            expected_deck_name,
            (package_size, package_digest),
        )
    )
    return tuple(failures)


def _qa_artifacts(record: dict[str, object]) -> tuple[tuple[str, int, str, int, int], ...]:
    presentations = record["presentations"]
    exact_rebuild = record["exact_rebuild"]
    pipeline = record["pipeline"]
    renderer = record["renderer"]
    slides = record["slides"]
    if (
        not isinstance(presentations, dict)
        or not isinstance(exact_rebuild, dict)
        or not isinstance(pipeline, dict)
        or not isinstance(renderer, dict)
        or not isinstance(slides, list)
    ):
        raise TypeError(
            "exact-rebuild QA presentations/pipeline/renderer/slides contract is invalid"
        )
    source = presentations["source"]
    target = presentations["curated_target"]
    curated_pipeline = pipeline["curated_target"]
    if (
        not isinstance(source, dict)
        or not isinstance(target, dict)
        or not isinstance(curated_pipeline, dict)
    ):
        raise TypeError("exact-rebuild QA presentation contract is invalid")
    artifacts: list[tuple[str, int, str, int, int]] = [
        (
            exact_rebuild["builder_path"],
            exact_rebuild["builder_bytes"],
            exact_rebuild["builder_sha256"],
            0,
            0,
        ),
        (
            curated_pipeline["builder_path"],
            curated_pipeline["builder_bytes"],
            curated_pipeline["builder_sha256"],
            0,
            0,
        ),
        (
            renderer["replay_script_path"],
            renderer["replay_script_bytes"],
            renderer["replay_script_sha256"],
            0,
            0,
        ),
        (
            exact_rebuild["manifest_path"],
            exact_rebuild["manifest_bytes"],
            exact_rebuild["manifest_sha256"],
            0,
            0,
        ),
        (source["path"], source["bytes"], source["sha256"], 0, 0),
        (target["path"], target["bytes"], target["sha256"], 0, 0),
    ]
    for slide in slides:
        if not isinstance(slide, dict):
            raise TypeError("exact-rebuild QA slide contract is invalid")
        number = slide["slide_number"]
        width = slide["width"]
        height = slide["height"]
        artifacts.extend(
            (
                (
                    f"docs/assets/pptrans-demo-libreoffice-en-slide-{number:02d}.png",
                    slide["source_png_bytes"],
                    slide["source_png_sha256"],
                    width,
                    height,
                ),
                (
                    f"docs/assets/pptrans-demo-libreoffice-zh-CN-slide-{number:02d}.png",
                    slide["target_png_bytes"],
                    slide["target_png_sha256"],
                    width,
                    height,
                ),
            )
        )
    if not all(
        isinstance(path, str)
        and isinstance(size, int)
        and not isinstance(size, bool)
        and isinstance(digest, str)
        and isinstance(width, int)
        and not isinstance(width, bool)
        and isinstance(height, int)
        and not isinstance(height, bool)
        for path, size, digest, width, height in artifacts
    ):
        raise TypeError("exact-rebuild QA artifact contract has invalid field types")
    return tuple(artifacts)


def _png_dimensions(payload: bytes) -> tuple[int, int] | None:
    if (
        len(payload) < PNG_HEADER_BYTES
        or payload[:8] != b"\x89PNG\r\n\x1a\n"
        or payload[12:16] != b"IHDR"
    ):
        return None
    return int.from_bytes(payload[16:20], "big"), int.from_bytes(payload[20:24], "big")


def _qa_evidence_failures(
    archive: tarfile.TarFile,
    archive_members: tuple[tarfile.TarInfo, ...],
    members: tuple[str, ...],
) -> tuple[str, ...]:
    qa_members = [
        (member, normalized)
        for member, normalized in zip(archive_members, members, strict=True)
        if member.isfile() and normalized.endswith(CURRENT_QA_SUFFIX)
    ]
    if len(qa_members) != 1:
        return ("source distribution must contain exactly one current QA record",)
    qa_member, qa_name = qa_members[0]
    distribution_root = qa_name[: -len(CURRENT_QA_SUFFIX)]
    try:
        record = json.loads(_read_tar_member(archive, qa_member).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return (f"source distribution exact-rebuild QA record is invalid: {exc}",)
    if not isinstance(record, dict):
        return ("source distribution exact-rebuild QA record must be an object",)
    canonical = json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    if hashlib.sha256(canonical.encode()).hexdigest() != CURRENT_QA_CANONICAL_SHA256:
        return ("source distribution exact-rebuild QA record differs from the pinned contract",)
    try:
        artifacts = _qa_artifacts(record)
    except (KeyError, TypeError, ValueError) as exc:
        return (f"source distribution exact-rebuild QA contract is invalid: {exc}",)

    failures: list[str] = []
    for relative_path, expected_size, expected_digest, width, height in artifacts:
        expected_name = distribution_root + relative_path
        artifact_members = [
            member
            for member, normalized in zip(archive_members, members, strict=True)
            if member.isfile() and normalized == expected_name
        ]
        if len(artifact_members) != 1:
            failures.append(f"source distribution must contain one QA artifact: {relative_path}")
            continue
        payload = _read_tar_member(archive, artifact_members[0])
        if (len(payload), hashlib.sha256(payload).hexdigest()) != (
            expected_size,
            expected_digest,
        ):
            failures.append(f"source distribution QA artifact differs from record: {relative_path}")
        if width and height and _png_dimensions(payload) != (width, height):
            failures.append(f"source distribution QA image dimensions differ: {relative_path}")
    return tuple(failures)


def _inspect_sdist_snapshot(snapshot: bytes) -> tuple[str, ...]:
    """Return validation failures for one immutable source-distribution snapshot."""

    with tarfile.open(fileobj=io.BytesIO(snapshot), mode="r:gz") as archive:
        archive_members = tuple(archive.getmembers())
        members = tuple(member.name for member in archive_members)
        demo_failures = _demo_source_failures(archive, archive_members, members)
        qa_failures = _qa_evidence_failures(archive, archive_members, members)
    failures = [
        f"unsafe source-distribution member: {member}"
        for member in members
        if "\\" in member
        or PurePosixPath(member).is_absolute()
        or ".." in PurePosixPath(member).parts
    ]
    failures.extend(
        f"unsupported source-distribution member type: {member.name}"
        for member in archive_members
        if not member.isfile() and not member.isdir()
    )
    if len(set(members)) != len(members):
        failures.append("source distribution contains duplicate member names")
    distribution_roots = {
        PurePosixPath(member).parts[0] for member in members if PurePosixPath(member).parts
    }
    distribution_root = next(iter(distribution_roots)) if len(distribution_roots) == 1 else None
    if distribution_root is None:
        failures.append("source distribution must contain exactly one top-level project directory")
    else:
        regular_files = {member.name for member in archive_members if member.isfile()}
        relative_members = {
            member.name.removeprefix(f"{distribution_root}/").rstrip("/")
            for member in archive_members
            if member.name.startswith(f"{distribution_root}/")
        }
        failures.extend(
            f"missing source-distribution member: {required}"
            for required in sorted(SDIST_REQUIRED_SUFFIXES)
            if f"{distribution_root}/{required}" not in regular_files
        )
        failures.extend(
            f"forbidden source-distribution artifact: {relative}"
            for relative in sorted(relative_members)
            if _forbidden_sdist_path(relative)
        )
    failures.extend(demo_failures)
    failures.extend(qa_failures)
    expected_pptx_members = {
        "examples/pptrans-demo.en.pptx",
        "examples/pptrans-demo.zh-CN.pptx",
    }
    actual_pptx_members = {
        member.name.removeprefix(f"{distribution_root}/")
        for member in archive_members
        if distribution_root is not None
        and member.isfile()
        and member.name.lower().endswith(".pptx")
    }
    if actual_pptx_members != expected_pptx_members:
        failures.append(
            "source distribution must contain only the English and curated zh-CN demo PPTX files"
        )
    return tuple(failures)


def inspect_sdist(path: Path) -> tuple[str, ...]:
    """Return validation failures for one gzip-compressed source distribution."""

    if not path.is_file() or not path.name.endswith(".tar.gz"):
        return (f"not a gzip source distribution: {path}",)
    try:
        snapshot = path.read_bytes()
    except OSError as exc:
        return (f"could not read source distribution: {exc}",)
    return _inspect_sdist_snapshot(snapshot)


def _pinned_packaged_rebuild_inputs(
    selected: dict[str, bytes],
) -> tuple[dict[str, object], dict[str, object]]:
    qa_payload = selected.get(CURRENT_QA_SUFFIX)
    if qa_payload is None:
        raise ValueError("source distribution is missing the pinned exact-rebuild QA record")
    try:
        record = json.loads(qa_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"source distribution exact-rebuild QA record is invalid: {exc}") from exc
    if not isinstance(record, dict):
        raise TypeError("source distribution exact-rebuild QA record must be an object")
    canonical = json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    if hashlib.sha256(canonical.encode()).hexdigest() != CURRENT_QA_CANONICAL_SHA256:
        raise ValueError(
            "source distribution exact-rebuild QA record differs from the pinned contract"
        )

    exact_rebuild = record.get("exact_rebuild")
    if not isinstance(exact_rebuild, dict):
        raise TypeError("source distribution exact-rebuild builder contract must be an object")
    builder_path = exact_rebuild.get("builder_path")
    builder_size = exact_rebuild.get("builder_bytes")
    builder_digest = exact_rebuild.get("builder_sha256")
    if (
        builder_path != "scripts/rebuild_demo.py"
        or not isinstance(builder_size, int)
        or isinstance(builder_size, bool)
        or not isinstance(builder_digest, str)
    ):
        raise ValueError("source distribution exact-rebuild builder contract is invalid")
    builder_payload = selected.get(builder_path)
    if builder_payload is None or (
        len(builder_payload),
        hashlib.sha256(builder_payload).hexdigest(),
    ) != (builder_size, builder_digest):
        raise ValueError("refusing to execute an unpinned packaged demo builder")
    return record, exact_rebuild


def _packaged_rebuild_payloads(snapshot: bytes) -> dict[str, bytes]:
    with tarfile.open(fileobj=io.BytesIO(snapshot), mode="r:gz") as archive:
        members = tuple(archive.getmembers())
        roots = {
            PurePosixPath(member.name).parts[0]
            for member in members
            if PurePosixPath(member.name).parts
        }
        if len(roots) != 1:
            raise ValueError("packaged demo rebuild requires one source-distribution root")
        distribution_root = next(iter(roots))
        selected: dict[str, bytes] = {}
        for member in members:
            if not member.isfile() or not member.name.startswith(f"{distribution_root}/"):
                continue
            relative = member.name.removeprefix(f"{distribution_root}/")
            if relative in {
                "scripts/rebuild_demo.py",
                DEMO_SOURCE_DECK_SUFFIX,
                CURRENT_QA_SUFFIX,
            } or relative.startswith(DEMO_SOURCE_PREFIX):
                pure = PurePosixPath(relative)
                if pure.is_absolute() or ".." in pure.parts or "\\" in relative:
                    raise ValueError(f"unsafe packaged demo rebuild member: {relative}")
                if relative in selected:
                    raise ValueError(f"duplicate packaged demo rebuild member: {relative}")
                selected[relative] = _read_tar_member(archive, member)

    required = {
        "scripts/rebuild_demo.py",
        DEMO_MANIFEST_SUFFIX,
        DEMO_SOURCE_DECK_SUFFIX,
        CURRENT_QA_SUFFIX,
    }
    if not required <= selected.keys():
        raise ValueError("source distribution is missing packaged demo rebuild inputs")
    return selected


def verify_packaged_demo_builder(snapshot: bytes) -> tuple[str, ...]:
    """Run the hash-pinned builder against only its extracted sdist inputs."""

    try:
        selected = _packaged_rebuild_payloads(snapshot)
        _pinned_packaged_rebuild_inputs(selected)
    except (OSError, tarfile.TarError) as exc:
        return (f"could not read packaged demo rebuild inputs: {exc}",)
    except (TypeError, ValueError) as exc:
        return (str(exc),)

    with tempfile.TemporaryDirectory(prefix="pptrans-sdist-rebuild-") as directory:
        project = Path(directory) / "project"
        for relative, payload in selected.items():
            destination = project.joinpath(*PurePosixPath(relative).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        manifest = json.loads((project / DEMO_MANIFEST_SUFFIX).read_bytes())
        package = manifest["expected_package"]
        environment = {
            key: value for key, value in os.environ.items() if not key.upper().startswith("PYTHON")
        }
        try:
            result = subprocess.run(  # noqa: S603
                [
                    sys.executable,
                    "-I",
                    "-X",
                    "utf8",
                    str(project / "scripts" / "rebuild_demo.py"),
                    "--check",
                ],
                cwd=project,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=PACKAGED_REBUILD_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return (f"packaged demo rebuild could not run: {exc}",)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-500:]
        return (f"packaged demo rebuild failed with status {result.returncode}: {detail}",)
    try:
        output = json.loads(result.stdout.strip())
    except json.JSONDecodeError as exc:
        return (f"packaged demo rebuild returned invalid JSON: {exc}",)
    expected_output = {
        "bytes": package["bytes"],
        "entries": len(manifest["entries"]),
        "result": "byte-identical",
        "sha256": package["sha256"],
    }
    if not isinstance(output, dict) or any(
        output.get(key) != value for key, value in expected_output.items()
    ):
        return ("packaged demo rebuild returned an unexpected result",)
    return ()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=Path("dist"),
        help="Directory containing exactly one PPTrans wheel and source distribution.",
    )
    args = parser.parse_args(argv)
    wheels = tuple(args.dist_dir.glob("*.whl"))
    sdists = tuple(args.dist_dir.glob("*.tar.gz"))
    if len(wheels) != 1:
        print(f"expected exactly one wheel in {args.dist_dir}, found {len(wheels)}")
        return 1
    if len(sdists) != 1:
        print(f"expected exactly one source distribution in {args.dist_dir}, found {len(sdists)}")
        return 1
    wheel_failures = inspect_wheel(wheels[0])
    try:
        sdist_snapshot = sdists[0].read_bytes()
    except OSError as exc:
        print(f"could not read source distribution: {exc}")
        return 1
    sdist_failures = _inspect_sdist_snapshot(sdist_snapshot)
    if not sdist_failures:
        sdist_failures = verify_packaged_demo_builder(sdist_snapshot)
    failures = (*wheel_failures, *sdist_failures)
    if failures:
        print("\n".join(failures))
        return 1
    print(f"distribution contents verified: {wheels[0].name}, {sdists[0].name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
