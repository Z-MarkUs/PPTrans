#!/usr/bin/env python3
"""Synchronize the canonical PPTrans Agent Skill to Claude Code's path."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from contextlib import suppress
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_NAMES = ("pptrans-engineering", "pptrans-operator")
CANONICAL_ROOT = REPO_ROOT / ".agents" / "skills"
MIRROR_ROOT = REPO_ROOT / ".claude" / "skills"


def _validate_root_path(root: Path, *, require_existing: bool) -> None:
    repository = REPO_ROOT.resolve(strict=True)
    try:
        relative = root.absolute().relative_to(REPO_ROOT.absolute())
    except ValueError as exc:
        raise ValueError("Skill paths must remain inside the repository.") from exc

    cursor = REPO_ROOT
    for component in relative.parts:
        cursor /= component
        if cursor.is_symlink():
            raise ValueError(
                f"Skill path components must not be symlinks: {cursor.relative_to(REPO_ROOT)}"
            )
        if cursor.exists() and not cursor.is_dir():
            raise ValueError(
                f"Skill path components must be directories: {cursor.relative_to(REPO_ROOT)}"
            )
    try:
        root.resolve(strict=False).relative_to(repository)
    except ValueError as exc:
        raise ValueError("Resolved Skill paths must remain inside the repository.") from exc
    if require_existing and not root.is_dir():
        raise ValueError(f"Skill directory does not exist: {root.relative_to(REPO_ROOT)}")


def _files(root: Path) -> dict[Path, Path]:
    _validate_root_path(root, require_existing=True)

    result: dict[Path, Path] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Skill entries must not be symlinks: {path.relative_to(REPO_ROOT)}")
        if path.is_file():
            result[path.relative_to(root)] = path
    return result


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _skill_paths(skill_name: str) -> tuple[Path, Path]:
    return CANONICAL_ROOT / skill_name, MIRROR_ROOT / skill_name


def differences() -> list[str]:
    messages: list[str] = []
    for skill_name in SKILL_NAMES:
        canonical_root, mirror_root = _skill_paths(skill_name)
        canonical = _files(canonical_root)
        mirror = _files(mirror_root)
        messages.extend(
            f"{skill_name}: missing from Claude mirror: {relative.as_posix()}"
            for relative in sorted(canonical.keys() - mirror.keys())
        )
        messages.extend(
            f"{skill_name}: extra in Claude mirror: {relative.as_posix()}"
            for relative in sorted(mirror.keys() - canonical.keys())
        )
        messages.extend(
            f"{skill_name}: content differs: {relative.as_posix()}"
            for relative in sorted(canonical.keys() & mirror.keys())
            if _digest(canonical[relative]) != _digest(mirror[relative])
        )
    return messages


def _preflight_skill(canonical_root: Path, mirror_root: Path) -> None:
    _files(canonical_root)
    _validate_root_path(mirror_root, require_existing=False)
    if mirror_root.exists():
        _files(mirror_root)


def _synchronize_skill(canonical_root: Path, mirror_root: Path) -> None:
    canonical = _files(canonical_root)
    _validate_root_path(mirror_root, require_existing=False)
    if mirror_root.exists():
        _files(mirror_root)
    mirror_root.mkdir(parents=True, exist_ok=True)

    for relative, source in canonical.items():
        destination = mirror_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    canonical_paths = set(canonical)
    for path in sorted(mirror_root.rglob("*"), reverse=True):
        relative = path.relative_to(mirror_root)
        if path.is_symlink() or (path.is_file() and relative not in canonical_paths):
            path.unlink()
        elif path.is_dir():
            with suppress(OSError):
                path.rmdir()


def synchronize() -> None:
    skill_paths = tuple(_skill_paths(skill_name) for skill_name in SKILL_NAMES)
    for canonical_root, mirror_root in skill_paths:
        _preflight_skill(canonical_root, mirror_root)
    for canonical_root, mirror_root in skill_paths:
        _synchronize_skill(canonical_root, mirror_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report drift without writing files.",
    )
    args = parser.parse_args(argv)

    try:
        if not args.check:
            synchronize()
        drift = differences()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if drift:
        print("Agent Skill mirror is out of sync:", file=sys.stderr)
        for message in drift:
            print(f"- {message}", file=sys.stderr)
        if args.check:
            print("Run: python scripts/sync_agent_skills.py", file=sys.stderr)
        return 1

    action = "match" if args.check else "were synchronized with"
    print(f"Claude Agent Skills {action} the canonical .agents copies.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
