"""Fail if PPTrans distributions omit evidence or contain private artifacts."""

from __future__ import annotations

import argparse
import sys
import tarfile
import zipfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

REQUIRED_SUFFIXES = {
    "pptrans/__init__.py",
    "pptrans/cli.py",
    "pptrans/py.typed",
}
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
    "README.zh-CN.md",
    "benchmarks/README.md",
    "benchmarks/results/2026-08-28-windows-python312.json",
    "benchmarks/results/2026-08-31-windows-python312.json",
    "docs/ARCHITECTURE.md",
    "docs/assets/pptrans-demo-preview.webp",
    "docs/assets/pptrans-demo-libreoffice-en-slide-01.png",
    "docs/assets/pptrans-demo-libreoffice-en-slide-02.png",
    "docs/assets/pptrans-demo-libreoffice-en-slide-03.png",
    "docs/assets/pptrans-demo-libreoffice-zh-CN-slide-01.png",
    "docs/assets/pptrans-demo-libreoffice-zh-CN-slide-02.png",
    "docs/assets/pptrans-demo-libreoffice-zh-CN-slide-03.png",
    "docs/assets/pptrans-demo-source-slide-01.webp",
    "docs/assets/pptrans-demo-source-slide-02.webp",
    "docs/assets/pptrans-demo-source-slide-03.webp",
    "docs/assets/pptrans-demo-zh-CN-slide-01.webp",
    "docs/assets/pptrans-demo-zh-CN-slide-02.webp",
    "docs/assets/pptrans-demo-zh-CN-slide-03.webp",
    "docs/qa/2026-08-28-curated-zh-cn.json",
    "docs/qa/2026-08-28-windows-libreoffice.json",
    "examples/pptrans-demo.en.pptx",
    "examples/pptrans-demo.zh-CN.pptx",
    "scripts/build_curated_demo.py",
    "scripts/build_demo.mjs",
    "scripts/check_doc_links.py",
    "scripts/check_installed_version.py",
    "scripts/check_minimal_install.py",
    "scripts/check_release_policy.py",
    "scripts/render_demo_comparison.mjs",
    "scripts/reproduce_native_demo.py",
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


def inspect_wheel(path: Path) -> tuple[str, ...]:
    """Return validation failures for one wheel."""

    if not path.is_file() or path.suffix != ".whl":
        return (f"not a wheel: {path}",)
    with zipfile.ZipFile(path) as archive:
        members = tuple(name.replace("\\", "/") for name in archive.namelist())
    failures = [
        f"missing required member ending in {required}"
        for required in sorted(REQUIRED_SUFFIXES)
        if not any(member.endswith(required) for member in members)
    ]
    failures.extend(
        f"forbidden wheel member: {member}"
        for member in members
        if any(fragment in member for fragment in FORBIDDEN_FRAGMENTS)
    )
    return tuple(failures)


def inspect_sdist(path: Path) -> tuple[str, ...]:
    """Return validation failures for one gzip-compressed source distribution."""

    if not path.is_file() or not path.name.endswith(".tar.gz"):
        return (f"not a gzip source distribution: {path}",)
    with tarfile.open(path, mode="r:gz") as archive:
        members = tuple(member.name.replace("\\", "/") for member in archive.getmembers())
    failures = [
        f"unsafe source-distribution member: {member}"
        for member in members
        if PurePosixPath(member).is_absolute() or ".." in PurePosixPath(member).parts
    ]
    failures.extend(
        f"missing source-distribution member ending in {required}"
        for required in sorted(SDIST_REQUIRED_SUFFIXES)
        if not any(member.endswith(required) for member in members)
    )
    pptx_members = {
        suffix
        for member in members
        for suffix in (
            "examples/pptrans-demo.en.pptx",
            "examples/pptrans-demo.zh-CN.pptx",
        )
        if member.endswith(suffix)
    }
    expected_pptx_members = {
        "examples/pptrans-demo.en.pptx",
        "examples/pptrans-demo.zh-CN.pptx",
    }
    all_pptx_members = tuple(member for member in members if member.lower().endswith(".pptx"))
    if pptx_members != expected_pptx_members or len(all_pptx_members) != len(expected_pptx_members):
        failures.append(
            "source distribution must contain only the English and curated zh-CN demo PPTX files"
        )
    return tuple(failures)


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
    failures = (*inspect_wheel(wheels[0]), *inspect_sdist(sdists[0]))
    if failures:
        print("\n".join(failures))
        return 1
    print(f"distribution contents verified: {wheels[0].name}, {sdists[0].name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
