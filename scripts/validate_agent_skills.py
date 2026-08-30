#!/usr/bin/env python3
"""Validate PPTrans's canonical and mirrored Agent Skills deterministically."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_NAMES = ("pptrans-engineering", "pptrans-operator")
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")
SCAFFOLD_MARKERS = ("<skill-name>", "TODO", "TBD")
QUOTED_INTERFACE_FIELDS = (
    "display_name",
    "short_description",
    "brand_color",
    "default_prompt",
)
MIN_SHORT_DESCRIPTION = 25
MAX_SHORT_DESCRIPTION = 64
MAX_SKILL_NAME = 63
MAX_SKILL_DESCRIPTION = 1_024
MAX_SKILL_LINES = 200
DISCOVERY_REQUIREMENTS = {
    "AGENTS.md": (
        ".agents/skills/pptrans-engineering/",
        ".agents/skills/pptrans-operator/",
        "$pptrans-engineering",
        "$pptrans-operator",
        "scripts/sync_agent_skills.py",
        "scripts/validate_agent_skills.py",
    ),
    "CLAUDE.md": (
        "@AGENTS.md",
        "/pptrans-engineering",
        "/pptrans-operator",
    ),
}


def _skill_roots(skill_name: str) -> tuple[Path, Path]:
    return (
        REPO_ROOT / ".agents" / "skills" / skill_name,
        REPO_ROOT / ".claude" / "skills" / skill_name,
    )


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _scalar(path: Path, line_number: int, raw: str, errors: list[str]) -> Any:
    value = raw.strip()
    if not value:
        errors.append(f"{_relative(path)}:{line_number}: missing scalar value")
        return ""
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            errors.append(f"{_relative(path)}:{line_number}: invalid quoted string: {exc}")
            return ""
        if not isinstance(parsed, str):
            errors.append(f"{_relative(path)}:{line_number}: expected a string")
            return ""
        return parsed
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "~"}:
        return None
    return value


def _load_frontmatter_mapping(path: Path, lines: list[str], errors: list[str]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for line_number, line in enumerate(lines, start=2):
        if not line.strip():
            continue
        if line[:1].isspace() or ":" not in line:
            errors.append(
                f"{_relative(path)}:{line_number}: frontmatter must use flat key-value pairs"
            )
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        if not key or key in data:
            errors.append(f"{_relative(path)}:{line_number}: invalid or duplicate key")
            continue
        data[key] = _scalar(path, line_number, raw_value, errors)
    return data


def _load_openai_mapping(path: Path, text: str, errors: list[str]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    section: dict[str, Any] | None = None
    section_name = ""
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[:1].isspace() and line.endswith(":"):
            section_name = line[:-1].strip()
            if not section_name or section_name in data:
                errors.append(f"{_relative(path)}:{line_number}: invalid or duplicate section")
                section = None
                continue
            section = {}
            data[section_name] = section
            continue
        if not line.startswith("  ") or line.startswith("   ") or ":" not in line:
            errors.append(f"{_relative(path)}:{line_number}: expected a two-space mapping entry")
            continue
        if section is None:
            errors.append(f"{_relative(path)}:{line_number}: entry appears before a section")
            continue
        key, raw_value = line.strip().split(":", 1)
        if not key or key in section:
            errors.append(
                f"{_relative(path)}:{line_number}: invalid or duplicate key in {section_name}"
            )
            continue
        section[key] = _scalar(path, line_number, raw_value, errors)
    return data


def _frontmatter(path: Path, errors: list[str]) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        errors.append(f"{_relative(path)}: missing opening YAML delimiter")
        return {}, text
    try:
        end = lines.index("---", 1)
    except ValueError:
        errors.append(f"{_relative(path)}: missing closing YAML delimiter")
        return {}, text
    metadata = _load_frontmatter_mapping(path, lines[1:end], errors)
    return metadata, text


def _validate_links(root: Path, errors: list[str]) -> None:
    for markdown in sorted(root.rglob("*.md")):
        text = markdown.read_text(encoding="utf-8")
        for raw_target in LINK_PATTERN.findall(text):
            target = raw_target.strip().split("#", 1)[0]
            if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
                continue
            destination = (markdown.parent / target).resolve()
            try:
                destination.relative_to(root.resolve())
            except ValueError:
                errors.append(
                    f"{_relative(markdown)}: relative link escapes the skill: {raw_target}"
                )
                continue
            if not destination.exists():
                errors.append(f"{_relative(markdown)}: broken relative link: {raw_target}")


def _validate_openai_yaml(root: Path, skill_name: str, errors: list[str]) -> None:
    path = root / "agents" / "openai.yaml"
    if not path.is_file():
        errors.append(f"{_relative(path)}: required UI metadata file is missing")
        return

    text = path.read_text(encoding="utf-8")
    data = _load_openai_mapping(path, text, errors)
    interface = data.get("interface")
    policy = data.get("policy")
    if not isinstance(interface, dict):
        errors.append(f"{_relative(path)}: interface must be a mapping")
        return
    if not isinstance(policy, dict):
        errors.append(f"{_relative(path)}: policy must be a mapping")
        policy = {}

    for field in QUOTED_INTERFACE_FIELDS:
        value = interface.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{_relative(path)}: interface.{field} must be a non-empty string")
        quoted_line = re.compile(
            rf'^\s{{2}}{re.escape(field)}:\s+"(?:[^"\\]|\\.)*"\s*$', re.MULTILINE
        )
        if not quoted_line.search(text):
            errors.append(f"{_relative(path)}: interface.{field} must use double quotes")

    short_description = interface.get("short_description", "")
    if isinstance(short_description, str) and not (
        MIN_SHORT_DESCRIPTION <= len(short_description) <= MAX_SHORT_DESCRIPTION
    ):
        errors.append(
            f"{_relative(path)}: short_description must be "
            f"{MIN_SHORT_DESCRIPTION}-{MAX_SHORT_DESCRIPTION} characters"
        )
    brand_color = interface.get("brand_color", "")
    if isinstance(brand_color, str) and not HEX_COLOR_PATTERN.fullmatch(brand_color):
        errors.append(f"{_relative(path)}: brand_color must be a six-digit hex color")
    default_prompt = interface.get("default_prompt", "")
    if isinstance(default_prompt, str) and f"${skill_name}" not in default_prompt:
        errors.append(f"{_relative(path)}: default_prompt must mention ${skill_name}")
    if policy.get("allow_implicit_invocation") is not True:
        errors.append(f"{_relative(path)}: implicit invocation must remain enabled")


def _validate_skill(root: Path, skill_name: str, errors: list[str]) -> None:
    if not root.is_dir():
        errors.append(f"{_relative(root)}: skill directory is missing")
        return
    if root.is_symlink():
        errors.append(f"{_relative(root)}: skill directory must not be a symlink")
    if (
        root.name != skill_name
        or not NAME_PATTERN.fullmatch(root.name)
        or len(root.name) > MAX_SKILL_NAME
    ):
        errors.append(f"{_relative(root)}: invalid skill directory name")

    skill_path = root / "SKILL.md"
    if not skill_path.is_file():
        errors.append(f"{_relative(skill_path)}: required entrypoint is missing")
        return
    metadata, text = _frontmatter(skill_path, errors)
    if metadata.get("name") != skill_name:
        errors.append(f"{_relative(skill_path)}: frontmatter name must be {skill_name}")
    description = metadata.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append(f"{_relative(skill_path)}: description must be a non-empty string")
    elif len(description) > MAX_SKILL_DESCRIPTION:
        errors.append(
            f"{_relative(skill_path)}: description exceeds {MAX_SKILL_DESCRIPTION} characters"
        )
    if len(text.splitlines()) > MAX_SKILL_LINES:
        errors.append(
            f"{_relative(skill_path)}: entrypoint should stay below {MAX_SKILL_LINES} lines"
        )
    errors.extend(
        f"{_relative(skill_path)}: unfinished scaffold marker {marker!r}"
        for marker in SCAFFOLD_MARKERS
        if marker in text
    )

    references = sorted((root / "references").glob("*.md"))
    linked_targets = set(LINK_PATTERN.findall(text))
    for reference in references:
        expected = f"references/{reference.name}"
        if expected not in linked_targets:
            errors.append(f"{_relative(skill_path)}: reference is not routed: {expected}")
    _validate_links(root, errors)
    _validate_openai_yaml(root, skill_name, errors)


def _tree(root: Path) -> dict[Path, str]:
    result: dict[Path, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            result[path.relative_to(root)] = "SYMLINK"
        elif path.is_file():
            result[path.relative_to(root)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _validate_mirror(skill_name: str, errors: list[str]) -> None:
    canonical_root, mirror_root = _skill_roots(skill_name)
    if not canonical_root.is_dir() or not mirror_root.is_dir():
        return
    canonical = _tree(canonical_root)
    mirror = _tree(mirror_root)
    errors.extend(
        f"{skill_name}: Claude mirror is missing {relative.as_posix()}"
        for relative in sorted(canonical.keys() - mirror.keys())
    )
    errors.extend(
        f"{skill_name}: Claude mirror has extra file {relative.as_posix()}"
        for relative in sorted(mirror.keys() - canonical.keys())
    )
    errors.extend(
        f"{skill_name}: Claude mirror differs at {relative.as_posix()}"
        for relative in sorted(canonical.keys() & mirror.keys())
        if canonical[relative] != mirror[relative]
    )


def _validate_discovery(errors: list[str]) -> None:
    for relative_path, required_fragments in DISCOVERY_REQUIREMENTS.items():
        path = REPO_ROOT / relative_path
        if not path.is_file():
            errors.append(f"{_relative(path)}: required agent discovery file is missing")
            continue
        text = path.read_text(encoding="utf-8")
        errors.extend(
            f"{_relative(path)}: missing agent discovery reference {fragment!r}"
            for fragment in required_fragments
            if fragment not in text
        )


def main() -> int:
    errors: list[str] = []
    for skill_name in SKILL_NAMES:
        for root in _skill_roots(skill_name):
            _validate_skill(root, skill_name, errors)
        _validate_mirror(skill_name, errors)
    _validate_discovery(errors)

    if errors:
        print("Agent Skill validation failed:", file=sys.stderr)
        for error in sorted(set(errors)):
            print(f"- {error}", file=sys.stderr)
        return 1

    names = ", ".join(SKILL_NAMES)
    print(f"Validated {names} in .agents and .claude; mirrors are byte-identical.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
