"""Regression tests for repository tooling that writes user-selected paths."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tarfile
import zipfile
from pathlib import Path
from types import ModuleType

import pytest
from test_ooxml_helpers import create_complex_deck

REPO_ROOT = Path(__file__).parents[1]
EXPECTED_PACKAGED_SKILL_RESOURCES = {
    f"{root}/skills/pptrans-engineering/{resource}"
    for root in (".agents", ".claude")
    for resource in (
        "SKILL.md",
        "agents/openai.yaml",
        "references/architecture.md",
        "references/release.md",
        "references/verification.md",
    )
}


def _load_script(name: str) -> ModuleType:
    path = REPO_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"test_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _demo_sdist_fixture(tmp_path: Path, mutation: str | None = None) -> Path:
    fixture_root = tmp_path / f"fixture-{mutation or 'valid'}"
    source = fixture_root / "examples" / "pptrans-demo.source"
    shutil.copytree(REPO_ROOT / "examples" / "pptrans-demo.source", source)
    deck = fixture_root / "examples" / "pptrans-demo.en.pptx"
    deck.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / "examples" / "pptrans-demo.en.pptx", deck)

    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if mutation == "payload":
        member = source.joinpath(*Path(manifest["entries"][0]["path"]).parts)
        payload = bytearray(member.read_bytes())
        payload[0] ^= 1
        member.write_bytes(payload)
    elif mutation == "entry":
        manifest["entries"][0] = "not-an-object"
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    elif mutation == "archive":
        manifest["archive"]["compression"] = "deflated"
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    elif mutation == "schema":
        manifest["schema_version"] = True
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

    archive_path = tmp_path / f"pptrans-{mutation or 'valid'}.tar.gz"
    with tarfile.open(archive_path, mode="w:gz") as archive:
        if mutation == "split_root":
            archive.add(
                manifest_path,
                arcname="pptrans-2.0/examples/pptrans-demo.source/manifest.json",
            )
            for member in source.rglob("*"):
                if member.is_file() and member != manifest_path:
                    relative = member.relative_to(source).as_posix()
                    archive.add(
                        member,
                        arcname=f"other-root/examples/pptrans-demo.source/{relative}",
                    )
            archive.add(deck, arcname="other-root/examples/pptrans-demo.en.pptx")
        else:
            archive.add(source, arcname="pptrans-2.0/examples/pptrans-demo.source")
            archive.add(deck, arcname="pptrans-2.0/examples/pptrans-demo.en.pptx")
    return archive_path


def _inspect_demo_fixture(checker: ModuleType, path: Path) -> tuple[str, ...]:
    with tarfile.open(path, mode="r:gz") as archive:
        archive_members = tuple(archive.getmembers())
        members = tuple(member.name.replace("\\", "/") for member in archive_members)
        return checker._demo_source_failures(archive, archive_members, members)


def _qa_sdist_fixture(tmp_path: Path, mutation: str | None = None) -> Path:
    fixture_root = tmp_path / f"qa-fixture-{mutation or 'valid'}"
    qa_relative = Path("docs/qa/2026-08-31-exact-rebuild.json")
    qa_path = fixture_root / qa_relative
    qa_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / qa_relative, qa_path)
    record = json.loads(qa_path.read_text(encoding="utf-8"))
    artifact_paths = {
        record["exact_rebuild"]["builder_path"],
        record["exact_rebuild"]["manifest_path"],
        record["pipeline"]["curated_target"]["builder_path"],
        record["renderer"]["replay_script_path"],
        record["presentations"]["source"]["path"],
        record["presentations"]["curated_target"]["path"],
    }
    for slide in record["slides"]:
        number = slide["slide_number"]
        artifact_paths.update(
            {
                f"docs/assets/pptrans-demo-libreoffice-en-slide-{number:02d}.png",
                f"docs/assets/pptrans-demo-libreoffice-zh-CN-slide-{number:02d}.png",
            }
        )
    for relative in artifact_paths:
        destination = fixture_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative, destination)

    if mutation in {"target", "png"}:
        relative = (
            record["presentations"]["curated_target"]["path"]
            if mutation == "target"
            else "docs/assets/pptrans-demo-libreoffice-en-slide-01.png"
        )
        artifact = fixture_root / relative
        payload = bytearray(artifact.read_bytes())
        payload[-1] ^= 1
        artifact.write_bytes(payload)
    elif mutation == "record":
        record["scope"].append("tampered")
        qa_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    archive_path = tmp_path / f"pptrans-qa-{mutation or 'valid'}.tar.gz"
    with tarfile.open(archive_path, mode="w:gz") as archive:
        archive.add(fixture_root, arcname="pptrans-2.0")
    return archive_path


def _packaged_builder_snapshot(tmp_path: Path, *, mutate_builder: bool = False) -> bytes:
    fixture_root = tmp_path / ("packaged-builder-mutated" if mutate_builder else "packaged-builder")
    source = fixture_root / "examples" / "pptrans-demo.source"
    shutil.copytree(REPO_ROOT / "examples" / "pptrans-demo.source", source)
    for relative in (
        "scripts/rebuild_demo.py",
        "docs/qa/2026-08-31-exact-rebuild.json",
        "examples/pptrans-demo.en.pptx",
    ):
        destination = fixture_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative, destination)
    if mutate_builder:
        (fixture_root / "scripts" / "rebuild_demo.py").write_text(
            "raise RuntimeError('unpinned builder must not execute')\n",
            encoding="utf-8",
        )

    archive_path = tmp_path / f"packaged-builder-{'mutated' if mutate_builder else 'valid'}.tar.gz"
    with tarfile.open(archive_path, mode="w:gz") as archive:
        archive.add(fixture_root, arcname="pptrans-2.0")
    return archive_path.read_bytes()


def _inspect_qa_fixture(checker: ModuleType, path: Path) -> tuple[str, ...]:
    with tarfile.open(path, mode="r:gz") as archive:
        archive_members = tuple(archive.getmembers())
        members = tuple(member.name.replace("\\", "/") for member in archive_members)
        return checker._qa_evidence_failures(archive, archive_members, members)


def test_source_distribution_policy_requires_complete_agent_skills() -> None:
    checker = _load_script("check_wheel.py")

    assert EXPECTED_PACKAGED_SKILL_RESOURCES <= checker.SDIST_REQUIRED_SUFFIXES


def test_source_distribution_policy_requires_the_public_demo_rebuild() -> None:
    checker = _load_script("check_wheel.py")

    assert {
        "README.md",
        "docs/DEMO.md",
        "docs/qa/2026-08-31-exact-rebuild.json",
        "examples/pptrans-demo.source/manifest.json",
        "scripts/rebuild_demo.py",
        "tests/test_demo_rebuild.py",
    } <= checker.SDIST_REQUIRED_SUFFIXES
    assert "scripts/build_demo.mjs" not in checker.SDIST_REQUIRED_SUFFIXES
    assert "scripts/render_demo_comparison.mjs" not in checker.SDIST_REQUIRED_SUFFIXES
    assert checker._forbidden_sdist_path(".env") is True
    assert checker._forbidden_sdist_path(".env.example") is False
    record = json.loads((REPO_ROOT / checker.CURRENT_QA_SUFFIX).read_bytes())
    canonical = json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode()).hexdigest() == checker.CURRENT_QA_CANONICAL_SHA256


@pytest.mark.parametrize(
    ("mutation", "expected_failure"),
    [
        (None, None),
        ("payload", "member differs from manifest"),
        ("entry", "entry 0 must be an object"),
        ("archive", "archive.compression must be 'stored'"),
        ("schema", "schema_version must be 1"),
        ("split_root", "do not share one distribution root"),
    ],
)
def test_source_distribution_demo_payloads_match_their_manifest(
    tmp_path: Path,
    mutation: str | None,
    expected_failure: str | None,
) -> None:
    checker = _load_script("check_wheel.py")

    failures = _inspect_demo_fixture(checker, _demo_sdist_fixture(tmp_path, mutation))

    if expected_failure is None:
        assert failures == ()
    else:
        assert any(expected_failure in failure for failure in failures)


@pytest.mark.parametrize(
    ("mutation", "expected_failure"),
    [
        (None, None),
        ("target", "QA artifact differs from record"),
        ("png", "QA artifact differs from record"),
        ("record", "QA record differs from the pinned contract"),
    ],
)
def test_source_distribution_qa_artifacts_match_the_current_record(
    tmp_path: Path,
    mutation: str | None,
    expected_failure: str | None,
) -> None:
    checker = _load_script("check_wheel.py")

    failures = _inspect_qa_fixture(checker, _qa_sdist_fixture(tmp_path, mutation))

    if expected_failure is None:
        assert failures == ()
    else:
        assert any(expected_failure in failure for failure in failures)


def test_wheel_checker_requires_exact_safe_package_paths(tmp_path: Path) -> None:
    checker = _load_script("check_wheel.py")
    valid = tmp_path / "valid.whl"
    with zipfile.ZipFile(valid, mode="w") as archive:
        for member in checker.REQUIRED_SUFFIXES:
            archive.writestr(member, b"fixture")
    assert checker.inspect_wheel(valid) == ()

    decoy = tmp_path / "decoy.whl"
    with zipfile.ZipFile(decoy, mode="w") as archive:
        for member in checker.REQUIRED_SUFFIXES:
            archive.writestr(f"decoy/{member}", b"fixture")
    decoy.write_bytes(decoy.read_bytes().replace(b"/", b"\\"))
    failures = checker.inspect_wheel(decoy)
    assert any("unsafe wheel member" in failure for failure in failures)
    assert any("missing required wheel member" in failure for failure in failures)


def test_wheel_checker_rejects_case_insensitive_forbidden_fragments(tmp_path: Path) -> None:
    checker = _load_script("check_wheel.py")
    wheel = tmp_path / "uppercase-private.whl"
    with zipfile.ZipFile(wheel, mode="w") as archive:
        for member in checker.REQUIRED_SUFFIXES:
            archive.writestr(member, b"fixture")
        archive.writestr("examples/PRIVATE.PPTX", b"private")

    assert "forbidden wheel member: examples/PRIVATE.PPTX" in checker.inspect_wheel(wheel)


@pytest.mark.parametrize(
    ("member_names", "expected_failure"),
    [
        (("pptrans-2.0/README.md", "other-root/file.txt"), "one top-level"),
        (("pptrans-2.0\\README.md",), "unsafe source-distribution member"),
    ],
)
def test_sdist_checker_rejects_split_roots_and_backslash_names(
    tmp_path: Path,
    member_names: tuple[str, ...],
    expected_failure: str,
) -> None:
    checker = _load_script("check_wheel.py")
    archive_path = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive_path, mode="w:gz") as archive:
        for member_name in member_names:
            info = tarfile.TarInfo(member_name)
            info.size = 1
            archive.addfile(info, io.BytesIO(b"x"))

    failures = checker.inspect_sdist(archive_path)

    assert any(expected_failure in failure for failure in failures)


@pytest.mark.parametrize(
    "relative",
    [
        ".env",
        "secrets/.env",
        ".env.local",
        ".env.production",
        "scripts/build_demo.mjs",
        "docs/assets/pptrans-demo-preview.webp",
        "private.sqlite3",
        "cache.sqlite3-wal",
        "cache.sqlite3-journal",
        "cache.db-shm",
        "ppt_translator/main.py",
        ".tmp-private/deck.pptx",
        "PPT_TRANSLATOR/main.py",
        "SCRIPTS/BUILD_DEMO.MJS",
        ".TMP-PRIVATE/notes.txt",
    ],
)
def test_sdist_checker_rejects_private_or_retired_artifacts(
    tmp_path: Path,
    relative: str,
) -> None:
    checker = _load_script("check_wheel.py")
    archive_path = tmp_path / "forbidden.tar.gz"
    with tarfile.open(archive_path, mode="w:gz") as archive:
        info = tarfile.TarInfo(f"pptrans-2.0/{relative}")
        info.size = 1
        archive.addfile(info, io.BytesIO(b"x"))

    failures = checker.inspect_sdist(archive_path)

    assert f"forbidden source-distribution artifact: {relative}" in failures


@pytest.mark.parametrize("relative", [".git", ".VENV", ".TMP-PRIVATE"])
def test_sdist_checker_rejects_empty_private_directories(
    tmp_path: Path,
    relative: str,
) -> None:
    checker = _load_script("check_wheel.py")
    archive_path = tmp_path / "forbidden-directory.tar.gz"
    with tarfile.open(archive_path, mode="w:gz") as archive:
        info = tarfile.TarInfo(f"pptrans-2.0/{relative}")
        info.type = tarfile.DIRTYPE
        archive.addfile(info)

    failures = checker.inspect_sdist(archive_path)

    assert f"forbidden source-distribution artifact: {relative}" in failures


def test_packaged_demo_builder_authenticates_before_isolated_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_script("check_wheel.py")
    manifest = json.loads(
        (REPO_ROOT / "examples" / "pptrans-demo.source" / "manifest.json").read_bytes()
    )
    expected_output = {
        "bytes": manifest["expected_package"]["bytes"],
        "entries": len(manifest["entries"]),
        "result": "byte-identical",
        "sha256": manifest["expected_package"]["sha256"],
    }
    observed: dict[str, object] = {}
    monkeypatch.setenv("PYTHON_CHECK_WHEEL_SENTINEL", "must-not-propagate")

    def fake_run(command: list[str], **kwargs: object) -> object:
        observed["command"] = command
        observed["environment"] = kwargs["env"]
        return checker.subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(expected_output),
            stderr="",
        )

    monkeypatch.setattr(checker.subprocess, "run", fake_run)

    assert checker.verify_packaged_demo_builder(_packaged_builder_snapshot(tmp_path)) == ()
    command = observed["command"]
    environment = observed["environment"]
    assert isinstance(command, list)
    assert command[1:4] == ["-I", "-X", "utf8"]
    assert isinstance(environment, dict)
    assert not any(key.upper().startswith("PYTHON") for key in environment)


def test_packaged_demo_builder_rejects_unpinned_code_without_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_script("check_wheel.py")

    def unexpected_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("unpinned packaged code was executed")

    monkeypatch.setattr(checker.subprocess, "run", unexpected_run)

    failures = checker.verify_packaged_demo_builder(
        _packaged_builder_snapshot(tmp_path, mutate_builder=True)
    )

    assert failures == ("refusing to execute an unpinned packaged demo builder",)


def test_distribution_checker_accepts_a_disposable_output_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_script("check_wheel.py")
    (tmp_path / "pptrans.whl").write_bytes(b"fixture")
    (tmp_path / "pptrans.tar.gz").write_bytes(b"fixture")
    monkeypatch.setattr(checker, "inspect_wheel", lambda _path: ())
    monkeypatch.setattr(checker, "_inspect_sdist_snapshot", lambda _snapshot: ())
    monkeypatch.setattr(checker, "verify_packaged_demo_builder", lambda _snapshot: ())

    assert checker.main(["--dist-dir", str(tmp_path)]) == 0


def test_distribution_checker_validates_and_executes_one_sdist_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_script("check_wheel.py")
    (tmp_path / "pptrans.whl").write_bytes(b"fixture")
    sdist = tmp_path / "pptrans.tar.gz"
    first_generation = b"first immutable source-distribution generation"
    sdist.write_bytes(first_generation)
    observed: list[bytes] = []
    monkeypatch.setattr(checker, "inspect_wheel", lambda _path: ())

    def inspect_snapshot(snapshot: bytes) -> tuple[()]:
        observed.append(snapshot)
        sdist.write_bytes(b"replacement generation")
        return ()

    def verify_snapshot(snapshot: bytes) -> tuple[()]:
        observed.append(snapshot)
        return ()

    monkeypatch.setattr(checker, "_inspect_sdist_snapshot", inspect_snapshot)
    monkeypatch.setattr(checker, "verify_packaged_demo_builder", verify_snapshot)

    assert checker.main(["--dist-dir", str(tmp_path)]) == 0
    assert observed == [first_generation, first_generation]


def test_minimal_install_checker_detects_optional_provider_sdks() -> None:
    checker = _load_script("check_minimal_install.py")

    assert checker.provider_sdk_presence_failures(lambda _module_name: None) == ()
    assert checker.provider_sdk_presence_failures(
        lambda module_name: object() if module_name == "openai" else None
    ) == ("base install unexpectedly exposes optional provider SDK: openai",)


def test_native_demo_reproducer_pins_the_committed_libreoffice_assets() -> None:
    reproducer = _load_script("reproduce_native_demo.py")

    contract = reproducer.load_contract()
    assert (contract.libreoffice_version, contract.pymupdf_version, contract.dpi) == (
        "26.8.0.3",
        "1.28.2",
        144,
    )
    assert len(contract.slides) == 3
    assert all((slide.width, slide.height) == (1921, 1080) for slide in contract.slides)
    reproducer.verify_committed_assets(contract, REPO_ROOT / "docs" / "assets")


def test_installed_version_checker_requires_runtime_metadata_and_exact_tag_agreement() -> None:
    checker = _load_script("check_installed_version.py")

    assert checker.version_failures("2.0.0a1", "2.0.0a1", "v2.0.0a1") == ()
    assert checker.version_failures("2.0.0a2", "2.0.0a1") == (
        "runtime version '2.0.0a2' != installed metadata '2.0.0a1'",
    )
    assert checker.version_failures("2.0.0a1", "2.0.0a1", "2.0.0a1") == (
        "release tag '2.0.0a1' != installed version tag v2.0.0a1",
    )


def test_release_policy_machine_enforces_the_recorded_provenance_gate(
    capsys: pytest.CaptureFixture[str],
) -> None:
    checker = _load_script("check_release_policy.py")

    assert checker.release_policy_failures("cleared") == ()
    assert checker.release_policy_failures() == (checker.BLOCK_MESSAGE,)
    assert checker.main(["--tag", "v2.0.0a1"]) == 1
    assert "v2.0.0a1: release blocked" in capsys.readouterr().err


def test_benchmark_output_guards_source_aliases_and_existing_files(tmp_path: Path) -> None:
    benchmark = _load_script("benchmark_core.py")
    source = tmp_path / "source.pptx"
    create_complex_deck(source)
    original = source.read_bytes()

    with pytest.raises(ValueError, match="input presentation"):
        benchmark._prepare_output(source, source, overwrite=True)
    assert source.read_bytes() == original

    alias = tmp_path / "source-hard-link.json"
    try:
        os.link(source, alias)
    except OSError as exc:
        pytest.skip(f"hard links unavailable on this filesystem: {exc}")
    with pytest.raises(ValueError, match="input presentation"):
        benchmark._prepare_output(source, alias, overwrite=True)
    assert source.read_bytes() == original

    existing = tmp_path / "result.json"
    existing.write_text("preserve", encoding="utf-8")
    with pytest.raises(FileExistsError, match="already exists"):
        benchmark._prepare_output(source, existing, overwrite=False)
    assert existing.read_text(encoding="utf-8") == "preserve"


def test_benchmark_output_rejects_symlink_target(tmp_path: Path) -> None:
    benchmark = _load_script("benchmark_core.py")
    source = tmp_path / "source.pptx"
    sentinel = tmp_path / "sentinel.json"
    output = tmp_path / "output.json"
    create_complex_deck(source)
    sentinel.write_text("preserve", encoding="utf-8")
    try:
        output.symlink_to(sentinel)
    except OSError as exc:
        pytest.skip(f"symbolic links unavailable on this filesystem: {exc}")

    with pytest.raises(ValueError, match="symbolic link"):
        benchmark._prepare_output(source, output, overwrite=True)
    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_skill_sync_rejects_symlinked_ancestor_without_touching_external_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync = _load_script("sync_agent_skills.py")
    repository = tmp_path / "repository"
    canonical = repository / ".agents" / "skills" / "pptrans-engineering"
    external = tmp_path / "external"
    canonical.mkdir(parents=True)
    external.mkdir()
    (canonical / "SKILL.md").write_text("canonical", encoding="utf-8")
    marker = external / "keep.txt"
    marker.write_text("do not touch", encoding="utf-8")
    try:
        (repository / ".claude").symlink_to(external, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symbolic links unavailable on this filesystem: {exc}")

    monkeypatch.setattr(sync, "REPO_ROOT", repository)
    monkeypatch.setattr(sync, "CANONICAL", canonical)
    monkeypatch.setattr(
        sync,
        "MIRROR",
        repository / ".claude" / "skills" / "pptrans-engineering",
    )

    with pytest.raises(ValueError, match="must not be symlinks"):
        sync.synchronize()
    assert marker.read_text(encoding="utf-8") == "do not touch"
    assert not (external / "skills").exists()
