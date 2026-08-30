"""Regression tests for repository tooling that writes user-selected paths."""

from __future__ import annotations

import importlib.util
import os
import sys
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


def test_source_distribution_policy_requires_complete_agent_skills() -> None:
    checker = _load_script("check_wheel.py")

    assert EXPECTED_PACKAGED_SKILL_RESOURCES <= checker.SDIST_REQUIRED_SUFFIXES


def test_distribution_checker_accepts_a_disposable_output_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _load_script("check_wheel.py")
    (tmp_path / "pptrans.whl").write_bytes(b"fixture")
    (tmp_path / "pptrans.tar.gz").write_bytes(b"fixture")
    monkeypatch.setattr(checker, "inspect_wheel", lambda _path: ())
    monkeypatch.setattr(checker, "inspect_sdist", lambda _path: ())

    assert checker.main(["--dist-dir", str(tmp_path)]) == 0


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
