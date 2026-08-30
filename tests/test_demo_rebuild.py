"""Prove the public OOXML source rebuilds the showcase deck exactly and safely."""

from __future__ import annotations

import errno
import hashlib
import importlib.util
import json
import shutil
import sys
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).parents[1]
SOURCE_DIR = REPO_ROOT / "examples" / "pptrans-demo.source"
COMMITTED_DEMO = REPO_ROOT / "examples" / "pptrans-demo.en.pptx"


def _load_builder() -> ModuleType:
    path = REPO_ROOT / "scripts" / "rebuild_demo.py"
    spec = importlib.util.spec_from_file_location("test_rebuild_demo_script", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_public_source_rebuilds_the_committed_demo_byte_for_byte(tmp_path: Path) -> None:
    builder = _load_builder()
    rebuilt = tmp_path / "pptrans-demo.en.pptx"

    builder.build_demo(SOURCE_DIR, rebuilt)

    assert rebuilt.read_bytes() == COMMITTED_DEMO.read_bytes()
    manifest = builder.load_manifest(SOURCE_DIR)
    with zipfile.ZipFile(rebuilt) as archive:
        infos = archive.infolist()
        assert archive.comment == b""
        assert [info.filename for info in infos] == [entry.path for entry in manifest.entries]
        assert all(info.compress_type == zipfile.ZIP_STORED for info in infos)
        assert all(info.date_time == manifest.timestamp for info in infos)
        assert all(info.create_system == builder.ZIP_CREATE_SYSTEM for info in infos)
        assert all(info.create_version == builder.ZIP_CREATE_VERSION for info in infos)
        assert all(info.extract_version == builder.ZIP_EXTRACT_VERSION for info in infos)
        assert all(info.flag_bits == 0 for info in infos)
        assert all(info.external_attr == builder.ZIP_EXTERNAL_ATTR for info in infos)
        assert all(info.internal_attr == 0 for info in infos)
        assert all(info.reserved == 0 for info in infos)
        assert all(info.volume == 0 for info in infos)
        assert all(info.extra == b"" for info in infos)
        assert all(info.comment == b"" for info in infos)
        assert [info.file_size for info in infos] == [entry.size for entry in manifest.entries]
        assert [hashlib.sha256(archive.read(info)).hexdigest() for info in infos] == [
            entry.sha256 for entry in manifest.entries
        ]
        assert archive.testzip() is None


def test_public_rebuild_refuses_existing_and_symlink_destinations(tmp_path: Path) -> None:
    builder = _load_builder()
    existing = tmp_path / "existing.pptx"
    existing.write_bytes(b"preserve")

    with pytest.raises(FileExistsError):
        builder.build_demo(SOURCE_DIR, existing)
    assert existing.read_bytes() == b"preserve"

    existing_directory = tmp_path / "directory.pptx"
    existing_directory.mkdir()
    with pytest.raises(FileExistsError):
        builder.build_demo(SOURCE_DIR, existing_directory)
    assert existing_directory.is_dir()

    sentinel = tmp_path / "sentinel.pptx"
    sentinel.write_bytes(b"sentinel")
    symlink = tmp_path / "symlink.pptx"
    try:
        symlink.symlink_to(sentinel)
    except OSError as exc:
        pytest.skip(f"symbolic links unavailable on this filesystem: {exc}")
    with pytest.raises(ValueError, match="symbolic link"):
        builder.build_demo(SOURCE_DIR, symlink, overwrite=True)
    assert sentinel.read_bytes() == b"sentinel"


def test_public_rebuild_overwrites_only_after_a_verified_stage(tmp_path: Path) -> None:
    builder = _load_builder()
    output = tmp_path / "replace.pptx"
    output.write_bytes(b"old")

    builder.build_demo(SOURCE_DIR, output, overwrite=True)

    assert output.read_bytes() == COMMITTED_DEMO.read_bytes()
    assert not tuple(tmp_path.glob(".replace.pptx.*.tmp"))


def test_public_rebuild_preserves_existing_output_when_staged_verification_fails(
    tmp_path: Path,
) -> None:
    builder = _load_builder()
    copied_source = tmp_path / "source"
    shutil.copytree(SOURCE_DIR, copied_source)
    manifest_path = copied_source / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["expected_package"]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "preserve.pptx"
    output.write_bytes(b"old")

    with pytest.raises(ValueError, match="rebuilt package does not match"):
        builder.build_demo(copied_source, output, overwrite=True)

    assert output.read_bytes() == b"old"
    assert not tuple(tmp_path.glob(".preserve.pptx.*.tmp"))


def test_public_rebuild_preserves_existing_output_when_verified_stage_is_swapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = _load_builder()
    output = tmp_path / "stage-swap.pptx"
    output.write_bytes(b"old")
    verify = builder._verify_built_package

    def verify_then_swap_stage(path: Path, manifest: object) -> None:
        verify(path, manifest)
        if path != output:
            path.unlink()
            path.write_bytes(b"foreign-stage")

    monkeypatch.setattr(builder, "_verify_built_package", verify_then_swap_stage)

    with pytest.raises(RuntimeError, match="foreign staging replacement was preserved"):
        builder.build_demo(SOURCE_DIR, output, overwrite=True)

    assert output.read_bytes() == b"old"
    foreign_stages = tuple(tmp_path.glob(".stage-swap.pptx.*.tmp"))
    assert len(foreign_stages) == 1
    assert foreign_stages[0].read_bytes() == b"foreign-stage"
    foreign_stages[0].unlink()


def test_public_rebuild_detects_foreign_swap_after_published_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = _load_builder()
    output = tmp_path / "published-swap.pptx"
    verify = builder._verify_built_package

    def verify_then_swap_published(path: Path, manifest: object) -> None:
        verify(path, manifest)
        if path == output:
            path.unlink()
            path.write_bytes(b"foreign-after-verify")

    monkeypatch.setattr(builder, "_verify_built_package", verify_then_swap_published)

    with pytest.raises(RuntimeError, match="foreign destination replacement was preserved"):
        builder.build_demo(SOURCE_DIR, output)

    assert output.read_bytes() == b"foreign-after-verify"
    assert not tuple(tmp_path.glob(".published-swap.pptx.*.tmp"))


def test_public_rebuild_preserves_destination_created_after_precheck(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = _load_builder()
    output = tmp_path / "raced.pptx"
    verify = builder._verify_built_package

    def verify_then_create_racer(path: Path, manifest: object) -> None:
        verify(path, manifest)
        output.write_bytes(b"racer")

    monkeypatch.setattr(builder, "_verify_built_package", verify_then_create_racer)

    with pytest.raises(FileExistsError):
        builder.build_demo(SOURCE_DIR, output)

    assert output.read_bytes() == b"racer"
    assert not tuple(tmp_path.glob(".raced.pptx.*.tmp"))


def test_public_rebuild_retries_transient_postpublication_stage_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = _load_builder()
    output = tmp_path / "cleanup.pptx"
    unlink = Path.unlink
    attempts = 0

    def fail_once(path: Path, *, missing_ok: bool = False) -> None:
        nonlocal attempts
        if path.parent == tmp_path and path.name.startswith(".cleanup.pptx."):
            attempts += 1
            if attempts == 1:
                raise PermissionError(errno.EACCES, "transient stage lock")
        unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_once)
    monkeypatch.setattr(builder.time, "sleep", lambda _delay: None)

    builder.build_demo(SOURCE_DIR, output)

    assert output.read_bytes() == COMMITTED_DEMO.read_bytes()
    assert attempts >= 2
    assert not tuple(tmp_path.glob(".cleanup.pptx.*.tmp"))


def test_public_rebuild_rolls_back_after_exhausted_postpublication_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = _load_builder()
    output = tmp_path / "rollback.pptx"
    unlink = Path.unlink
    failures_remaining = len(builder.UNLINK_RETRY_DELAYS_SECONDS) + 1

    def exhaust_first_cleanup(path: Path, *, missing_ok: bool = False) -> None:
        nonlocal failures_remaining
        if (
            path.parent == tmp_path
            and path.name.startswith(".rollback.pptx.")
            and failures_remaining
        ):
            failures_remaining -= 1
            raise PermissionError(errno.EACCES, "persistent stage lock")
        unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", exhaust_first_cleanup)
    monkeypatch.setattr(builder.time, "sleep", lambda _delay: None)

    with pytest.raises(RuntimeError, match="owned destination was rolled back"):
        builder.build_demo(SOURCE_DIR, output)

    assert not output.exists()
    assert not tuple(tmp_path.glob(".rollback.pptx.*.tmp"))


def test_public_rebuild_preserves_foreign_destination_during_cleanup_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = _load_builder()
    output = tmp_path / "foreign.pptx"
    unlink = Path.unlink
    stage_failures = len(builder.UNLINK_RETRY_DELAYS_SECONDS) + 1
    destination_replaced = False

    def replace_during_rollback(path: Path, *, missing_ok: bool = False) -> None:
        nonlocal destination_replaced, stage_failures
        if path.parent == tmp_path and path.name.startswith(".foreign.pptx.") and stage_failures:
            stage_failures -= 1
            raise PermissionError(errno.EACCES, "persistent stage lock")
        if path == output and not destination_replaced:
            unlink(path, missing_ok=missing_ok)
            output.write_bytes(b"foreign")
            destination_replaced = True
            raise PermissionError(errno.EACCES, "destination replaced")
        unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", replace_during_rollback)
    monkeypatch.setattr(builder.time, "sleep", lambda _delay: None)

    with pytest.raises(RuntimeError, match="foreign destination replacement was preserved"):
        builder.build_demo(SOURCE_DIR, output)

    assert output.read_bytes() == b"foreign"
    assert not tuple(tmp_path.glob(".foreign.pptx.*.tmp"))


@pytest.mark.parametrize("mutation", ["payload", "inventory", "nested_manifest", "path"])
def test_public_rebuild_rejects_tampered_source(
    tmp_path: Path,
    mutation: str,
) -> None:
    builder = _load_builder()
    copied_source = tmp_path / "source"
    shutil.copytree(SOURCE_DIR, copied_source)
    manifest_path = copied_source / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    first_path = copied_source.joinpath(*Path(manifest["entries"][0]["path"]).parts)
    if mutation == "payload":
        first_path.write_bytes(first_path.read_bytes()[:-1] + b"tampered\n")
    elif mutation == "inventory":
        (copied_source / "unlisted.xml").write_text("<unlisted/>\n", encoding="utf-8")
    elif mutation == "nested_manifest":
        nested_manifest = copied_source / "ppt" / "manifest.json"
        nested_manifest.write_text("{}\n", encoding="utf-8")
    else:
        manifest["entries"][0]["path"] = "../escape.xml"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError):
        builder.build_demo(copied_source, tmp_path / f"{mutation}.pptx")
    assert not (tmp_path / f"{mutation}.pptx").exists()


def test_public_rebuild_rejects_destination_inside_source_tree(tmp_path: Path) -> None:
    builder = _load_builder()
    copied_source = tmp_path / "source"
    shutil.copytree(SOURCE_DIR, copied_source)
    destination = copied_source / "generated.pptx"

    with pytest.raises(ValueError, match="outside the canonical source"):
        builder.build_demo(copied_source, destination)

    assert not destination.exists()
