"""Fail if PPTrans distributions omit evidence or contain private artifacts."""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

REQUIRED_SUFFIXES = {
    "pptrans/__init__.py",
    "pptrans/cli.py",
    "pptrans/py.typed",
}
SDIST_REQUIRED_SUFFIXES = {
    ".agents/skills/pptrans-engineering/SKILL.md",
    ".claude/skills/pptrans-engineering/SKILL.md",
    "README.zh-CN.md",
    "benchmarks/README.md",
    "benchmarks/results/2026-08-28-windows-python312.json",
    "docs/ARCHITECTURE.md",
    "docs/assets/pptrans-demo-preview.webp",
    "docs/qa/2026-08-28-windows-libreoffice.json",
    "examples/pptrans-demo.en.pptx",
    "scripts/build_demo.mjs",
    "tests/test_public_demo.py",
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
    pptx_members = tuple(member for member in members if member.lower().endswith(".pptx"))
    if len(pptx_members) != 1 or not pptx_members[0].endswith("examples/pptrans-demo.en.pptx"):
        failures.append(
            "source distribution must contain only examples/pptrans-demo.en.pptx as PPTX data"
        )
    return tuple(failures)


def main() -> int:
    wheels = tuple(Path("dist").glob("*.whl"))
    sdists = tuple(Path("dist").glob("*.tar.gz"))
    if len(wheels) != 1:
        print(f"expected exactly one wheel in dist/, found {len(wheels)}")
        return 1
    if len(sdists) != 1:
        print(f"expected exactly one source distribution in dist/, found {len(sdists)}")
        return 1
    failures = (*inspect_wheel(wheels[0]), *inspect_sdist(sdists[0]))
    if failures:
        print("\n".join(failures))
        return 1
    print(f"distribution contents verified: {wheels[0].name}, {sdists[0].name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
