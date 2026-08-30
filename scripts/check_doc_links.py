#!/usr/bin/env python3
"""Validate tracked Markdown links, fragments, and local images without network access."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess  # nosec B404 - fixed, non-shell Git index query only
import sys
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from lxml import etree
from markdown_it import MarkdownIt
from markdown_it.rules_inline import StateInline
from PIL import Image, UnidentifiedImageError

REPO_ROOT = Path(__file__).resolve().parents[1]
EXTERNAL_SCHEMES = frozenset({"http", "https", "mailto", "tel"})
UNSAFE_SCHEMES = frozenset({"data", "file", "javascript", "vbscript"})
RASTER_FORMATS = {
    ".gif": "GIF",
    ".jpeg": "JPEG",
    ".jpg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}
INVALID_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")
WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
CODE_LINE_FRAGMENT = re.compile(r"^L([1-9][0-9]*)(?:-L([1-9][0-9]*))?$")
PATH_LIKE_LABEL = re.compile(r"^[A-Za-z0-9_.-]+\.[A-Za-z0-9]+$")
SOURCE_OFFSET_META = "pptrans_source_offset"


@dataclass(frozen=True, slots=True)
class Reference:
    source: Path
    line: int
    target: str
    label: str
    image: bool


@dataclass(frozen=True, slots=True)
class CheckResult:
    markdown_files: int
    internal_references: int
    external_references: int
    image_references: int
    errors: tuple[str, ...]


@dataclass(slots=True)
class _ValidationContext:
    root: Path
    tracked: frozenset[str]
    tracked_directories: frozenset[str]
    anchor_cache: dict[Path, set[str]]
    image_cache: dict[Path, str | None]


@dataclass(frozen=True, slots=True)
class _ParsedTarget:
    raw: str
    path_text: str
    fragment: str


@dataclass(frozen=True, slots=True)
class _LocalTarget:
    raw: str
    path: Path
    indexed: str
    fragment: str


class _HTMLScanner(HTMLParser):
    def __init__(self, source: Path, base_line: int) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.base_line = base_line
        self.references: list[Reference] = []
        self.anchors: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.casefold(): value or "" for name, value in attrs}
        line = self.base_line + self.getpos()[0] - 1
        lowered = tag.casefold()
        identifier = attributes.get("id") or (attributes.get("name") if lowered == "a" else "")
        if identifier:
            self.anchors.add(identifier)
        if lowered == "a" and attributes.get("href") is not None:
            self.references.append(
                Reference(self.source, line, attributes["href"], "", image=False)
            )
        if lowered == "img" and attributes.get("src") is not None:
            self.references.append(
                Reference(
                    self.source,
                    line,
                    attributes["src"],
                    attributes.get("alt", "").strip(),
                    image=True,
                )
            )


def _inline_text(tokens: list[object]) -> str:
    pieces: list[str] = []
    for token in tokens:
        node_kind = getattr(token, "type", "")
        if node_kind in {"text", "code_inline"}:
            pieces.append(str(getattr(token, "content", "")))
        elif node_kind in {"softbreak", "hardbreak"}:
            pieces.append(" ")
        elif node_kind == "image":
            pieces.append(str(getattr(token, "content", "")))
    return "".join(pieces).strip()


def _inline_lines(tokens: list[object], start_line: int) -> list[int]:
    """Map inline child tokens to their 1-based source lines."""
    lines: list[int] = []
    line = start_line
    for token in tokens:
        lines.append(line)
        node_kind = getattr(token, "type", "")
        if node_kind in {"softbreak", "hardbreak"}:
            line += 1
        line += str(getattr(token, "content", "")).count("\n")
    return lines


def _source_position_rule(
    rule: Callable[[StateInline, bool], bool],
) -> Callable[[StateInline, bool], bool]:
    def wrapped(state: StateInline, silent: bool) -> bool:  # noqa: FBT001
        start = state.pos
        token_count = len(state.tokens)
        matched = rule(state, silent)
        if matched and not silent:
            for token in state.tokens[token_count:]:
                token.meta.setdefault(SOURCE_OFFSET_META, start)
        return matched

    return wrapped


def _enable_inline_source_positions(parser: MarkdownIt) -> None:
    names = parser.inline.ruler.get_active_rules()
    rules = parser.inline.ruler.getRules("")
    for name, rule in zip(names, rules, strict=True):
        parser.inline.ruler.at(name, _source_position_rule(rule))


def _preserve_link_target(target: str) -> str:
    """Keep raw percent escapes available for repository-policy validation."""
    return target


def _document_data(path: Path) -> tuple[list[Reference], set[str]]:
    parser = MarkdownIt("commonmark", {"html": True})
    parser.normalizeLink = _preserve_link_target
    _enable_inline_source_positions(parser)
    tokens = parser.parse(path.read_text(encoding="utf-8"))
    references: list[Reference] = []
    anchors: set[str] = set()
    heading_slugs: set[str] = set()

    for index, token in enumerate(tokens):
        if token.type == "heading_open" and index + 1 < len(tokens):
            inline = tokens[index + 1]
            if inline.type == "inline":
                slug = _github_slug(_inline_text(list(inline.children or ())))
                if slug:
                    candidate = slug
                    suffix = 1
                    while candidate in heading_slugs:
                        candidate = f"{slug}-{suffix}"
                        suffix += 1
                    heading_slugs.add(candidate)
                    anchors.add(candidate)

        if token.type == "inline":
            start_line = (token.map or [0])[0] + 1
            children = list(token.children or ())
            child_lines = _inline_lines(children, start_line)
            child_index = 0
            while child_index < len(children):
                child = children[child_index]
                offset = child.meta.get(SOURCE_OFFSET_META)
                line = (
                    start_line + token.content.count("\n", 0, offset)
                    if isinstance(offset, int) and 0 <= offset <= len(token.content)
                    else child_lines[child_index]
                )
                if child.type == "link_open":
                    close = child_index + 1
                    while close < len(children) and children[close].type != "link_close":
                        close += 1
                    references.append(
                        Reference(
                            path,
                            line,
                            child.attrGet("href") or "",
                            _inline_text(children[child_index + 1 : close]),
                            image=False,
                        )
                    )
                elif child.type == "image":
                    references.append(
                        Reference(
                            path,
                            line,
                            child.attrGet("src") or "",
                            child.content.strip(),
                            image=True,
                        )
                    )
                elif child.type == "html_inline":
                    scanner = _HTMLScanner(path, line)
                    scanner.feed(child.content)
                    references.extend(scanner.references)
                    anchors.update(scanner.anchors)
                child_index += 1

        if token.type == "html_block":
            scanner = _HTMLScanner(path, (token.map or [0])[0] + 1)
            scanner.feed(token.content)
            references.extend(scanner.references)
            anchors.update(scanner.anchors)

    return references, anchors


def _github_slug(text: str) -> str:
    characters: list[str] = []
    for character in text.strip().lower():
        if character in {"-", "_"}:
            characters.append(character)
        elif character.isspace():
            characters.append("-")
        elif unicodedata.category(character)[:1] in {"L", "M", "N"}:
            characters.append(character)
    return "".join(characters)


def _git_index(root: Path) -> frozenset[str]:
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("git is required to enumerate tracked documentation")
    completed = subprocess.run(  # noqa: S603  # nosec B603
        [executable, "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
        shell=False,
    )
    return frozenset(os.fsdecode(item) for item in completed.stdout.split(b"\0") if item)


def _tracked_directories(tracked: frozenset[str]) -> frozenset[str]:
    directories: set[str] = {"."} if tracked else set()
    for entry in tracked:
        parent = PurePosixPath(entry).parent
        while parent != PurePosixPath("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    return frozenset(directories)


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _error(root: Path, reference: Reference, message: str) -> str:
    return f"{_relative(root, reference.source)}:{reference.line}: {message}"


def _has_symlink_component(root: Path, relative: PurePosixPath) -> bool:
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            return True
    return False


def _validate_raster(path: Path, expected_format: str) -> str | None:
    try:
        with Image.open(path) as image:
            actual_format = image.format
            image.verify()
        with Image.open(path) as image:
            image.load()
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        return f"linked image is not decodable: {exc}"
    if actual_format != expected_format:
        return f"linked image extension expects {expected_format}, decoded as {actual_format}"
    return None


def _validate_svg(path: Path) -> str | None:
    try:
        parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
        root = etree.parse(path, parser).getroot()
    except (OSError, etree.XMLSyntaxError) as exc:
        return f"linked SVG is not safely parseable: {exc}"
    if etree.QName(root).localname.casefold() != "svg":
        return "linked .svg does not have an SVG root element"
    return None


def _validate_fragment(path: Path, fragment: str, anchors: set[str]) -> str | None:
    if path.suffix.casefold() == ".md":
        if fragment not in anchors:
            return f"Markdown heading fragment does not exist: #{fragment}"
        return None

    code_lines = CODE_LINE_FRAGMENT.fullmatch(fragment)
    if code_lines:
        start = int(code_lines.group(1))
        end = int(code_lines.group(2) or start)
        if end < start:
            return f"code-line fragment has descending range #{fragment}"
        line_count = sum(1 for _line in path.open(encoding="utf-8", errors="replace"))
        if end > line_count:
            return f"code-line fragment #{fragment} exceeds {line_count} lines"
        return None
    return None


def _parse_target(
    root: Path, reference: Reference
) -> tuple[_ParsedTarget | None, str | None, bool]:
    raw = reference.target.strip()
    if "\x00" in raw:
        return None, _error(root, reference, "link target contains a NUL character"), False
    if INVALID_PERCENT.search(raw):
        return (
            None,
            _error(root, reference, f"link target has invalid percent encoding: {raw!r}"),
            False,
        )

    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        return (
            None,
            _error(root, reference, f"link target is not a valid URI: {raw!r} ({exc})"),
            False,
        )
    scheme = parsed.scheme.casefold()
    if scheme in EXTERNAL_SCHEMES or (not scheme and parsed.netloc):
        return None, None, True
    if scheme in UNSAFE_SCHEMES:
        return None, _error(root, reference, f"unsafe link scheme is not allowed: {scheme}"), False
    if scheme:
        return None, _error(root, reference, f"unsupported link scheme: {scheme}"), False

    path_text = unquote(parsed.path)
    fragment = unquote(parsed.fragment)
    decoded = unquote(raw)
    if "\\" in decoded:
        return (
            None,
            _error(root, reference, f"link target must use forward slashes: {raw!r}"),
            False,
        )
    if not path_text and not fragment and not parsed.query:
        return None, _error(root, reference, "link target is empty"), False
    if path_text.startswith("/") or WINDOWS_DRIVE.match(path_text):
        return None, _error(root, reference, f"repository link must be relative: {raw!r}"), False
    return _ParsedTarget(raw, path_text, fragment), None, False


def _resolve_target(
    root: Path,
    reference: Reference,
    parsed: _ParsedTarget,
) -> tuple[_LocalTarget | None, str | None]:
    if parsed.path_text:
        parts = list(PurePosixPath(reference.source.parent.relative_to(root).as_posix()).parts)
        for part in PurePosixPath(parsed.path_text).parts:
            if part in {"", "."}:
                continue
            if part == "..":
                if not parts:
                    return None, _error(
                        root,
                        reference,
                        f"link escapes the repository: {parsed.raw!r}",
                    )
                parts.pop()
            else:
                parts.append(part)
    else:
        parts = list(PurePosixPath(reference.source.relative_to(root).as_posix()).parts)
    relative = PurePosixPath(*parts)
    lexical = root.joinpath(*parts)

    try:
        lexical.resolve(strict=False).relative_to(root.resolve())
    except ValueError:
        return None, _error(
            root,
            reference,
            f"link resolves outside the repository: {parsed.raw!r}",
        )
    if _has_symlink_component(root, relative):
        return None, _error(
            root,
            reference,
            f"link traverses a symbolic link: {parsed.raw!r}",
        )
    return _LocalTarget(parsed.raw, lexical, relative.as_posix(), parsed.fragment), None


def _validate_index(
    context: _ValidationContext,
    reference: Reference,
    target: _LocalTarget,
) -> str | None:
    root = context.root
    indexed = target.indexed
    path = target.path
    raw = target.raw

    if indexed in context.tracked:
        if not path.is_file():
            return _error(root, reference, f"tracked link target is not a file: {raw!r}")
    elif indexed in context.tracked_directories:
        if not path.is_dir():
            return _error(root, reference, f"tracked directory target is missing: {raw!r}")
    else:
        casefold_matches = {
            entry
            for entry in context.tracked | context.tracked_directories
            if entry.casefold() == indexed.casefold()
        }
        if casefold_matches:
            expected = min(casefold_matches)
            return _error(
                root,
                reference,
                f"link target casing differs from the Git index: {raw!r}; expected {expected!r}",
            )
        return _error(root, reference, f"link target is not tracked: {raw!r}")

    tracked_suffixes = {
        PurePosixPath(entry).suffix.casefold()
        for entry in context.tracked
        if PurePosixPath(entry).suffix
    }
    tracked_basenames = {PurePosixPath(entry).name.casefold() for entry in context.tracked}
    label_path = PurePosixPath(reference.label)
    label_looks_like_path = bool(
        reference.label
        and PATH_LIKE_LABEL.fullmatch(reference.label)
        and (
            label_path.suffix.casefold() in tracked_suffixes
            or label_path.name.casefold() in tracked_basenames
        )
    )
    if label_looks_like_path and reference.label.casefold() != path.name.casefold():
        return _error(
            root,
            reference,
            f"path-like label {reference.label!r} does not match target {path.name!r}",
        )
    return None


def _validate_content(
    context: _ValidationContext,
    reference: Reference,
    target: _LocalTarget,
) -> str | None:
    root = context.root
    path = target.path
    raw = target.raw

    if target.fragment:
        if not path.is_file():
            return _error(root, reference, f"directory link cannot use a fragment: {raw!r}")
        anchors = context.anchor_cache.get(path)
        if anchors is None:
            anchors = _document_data(path)[1] if path.suffix.casefold() == ".md" else set()
            context.anchor_cache[path] = anchors
        fragment_error = _validate_fragment(path, target.fragment, anchors)
        if fragment_error:
            return _error(root, reference, fragment_error)

    if reference.image:
        image_error = context.image_cache.get(path)
        if path not in context.image_cache:
            suffix = path.suffix.casefold()
            if suffix in RASTER_FORMATS:
                image_error = _validate_raster(path, RASTER_FORMATS[suffix])
            elif suffix == ".svg":
                image_error = _validate_svg(path)
            else:
                image_error = f"unsupported local image extension: {suffix or '<none>'}"
            context.image_cache[path] = image_error
        if image_error:
            return _error(root, reference, image_error)
    return None


def _validate_reference(
    context: _ValidationContext,
    reference: Reference,
) -> tuple[tuple[str, ...], bool]:
    errors: list[str] = []
    if reference.image and not reference.label.strip():
        errors.append(
            _error(
                context.root,
                reference,
                f"informative image has empty alt text: {reference.target!r}",
            )
        )
    parsed, error, external = _parse_target(context.root, reference)
    if error:
        errors.append(error)
        return tuple(errors), external
    if external:
        return tuple(errors), True
    assert parsed is not None
    target, error = _resolve_target(context.root, reference, parsed)
    if error:
        errors.append(error)
        return tuple(errors), False
    assert target is not None
    error = _validate_index(context, reference, target)
    if error:
        errors.append(error)
        return tuple(errors), False
    error = _validate_content(context, reference, target)
    if error:
        errors.append(error)
    return tuple(errors), False


def check_repository(root: Path, tracked_paths: frozenset[str] | None = None) -> CheckResult:
    root = root.resolve()
    tracked = tracked_paths if tracked_paths is not None else _git_index(root)
    markdown = tuple(
        root.joinpath(*PurePosixPath(path).parts)
        for path in sorted(tracked)
        if PurePosixPath(path).suffix.casefold() == ".md"
    )
    tracked_directories = _tracked_directories(tracked)
    context = _ValidationContext(root, tracked, tracked_directories, {}, {})
    errors: list[str] = []
    internal = 0
    external = 0
    images = 0

    for document in markdown:
        if document.is_symlink() or not document.is_file():
            errors.append(
                f"{_relative(root, document)}: tracked Markdown source is missing or linked"
            )
            continue
        references, anchors = _document_data(document)
        context.anchor_cache[document] = anchors
        for reference in references:
            images += int(reference.image)
            reference_errors, is_external = _validate_reference(context, reference)
            if is_external:
                external += 1
            else:
                internal += 1
            errors.extend(reference_errors)

    return CheckResult(
        markdown_files=len(markdown),
        internal_references=internal,
        external_references=external,
        image_references=images,
        errors=tuple(sorted(set(errors))),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Git checkout root; defaults to the script's repository.",
    )
    arguments = parser.parse_args(argv)
    try:
        result = check_repository(arguments.root)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Documentation validation could not run: {exc}", file=sys.stderr)
        return 2

    if result.errors:
        print("Documentation link validation failed:", file=sys.stderr)
        for error in result.errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        "Documentation links verified: "
        f"{result.markdown_files} Markdown files, "
        f"{result.internal_references} internal references, "
        f"{result.external_references} external references skipped, "
        f"{result.image_references} image references."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
