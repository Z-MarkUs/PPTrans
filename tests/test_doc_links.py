"""Offline regression tests for tracked documentation-link integrity."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image

REPO_ROOT = Path(__file__).parents[1]


def _load_checker() -> ModuleType:
    path = REPO_ROOT / "scripts" / "check_doc_links.py"
    spec = importlib.util.spec_from_file_location("test_check_doc_links_script", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(root: Path, relative: str, content: str) -> Path:
    path = root.joinpath(*Path(relative).parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _tracked(*paths: str) -> frozenset[str]:
    return frozenset(Path(path).as_posix() for path in paths)


def test_current_repository_documentation_is_internally_consistent() -> None:
    checker = _load_checker()

    result = checker.check_repository(REPO_ROOT)

    assert result.errors == ()
    assert result.markdown_files >= 23
    assert result.internal_references >= 148
    assert result.external_references >= 7
    assert result.image_references >= 10


def test_checker_parses_reference_html_fragments_queries_and_images(tmp_path: Path) -> None:
    checker = _load_checker()
    root = tmp_path / "repo"
    source = _write(
        root,
        "docs/source.md",
        """# Source heading

[inline](target.md#repeated-1)
[reference][target]
[same](#source-heading)
[Chinese](target.md#中文标题)
[HTML target](target.md?view=1#explicit-anchor)
<a href="target.md#repeated">raw HTML</a>
![Preview image](../assets/demo%20image.webp)
<img src="../assets/demo%20image.webp" alt="HTML preview">
[external](https://example.invalid/never-requested)

[target]: target.md#中文标题
""",
    )
    target = _write(
        root,
        "docs/target.md",
        """# Repeated

# Repeated

# 中文标题

<span id="explicit-anchor"></span>
""",
    )
    image = root / "assets" / "demo image.webp"
    image.parent.mkdir(parents=True)
    Image.new("RGB", (8, 6), "navy").save(image, format="WEBP")

    result = checker.check_repository(
        root,
        _tracked("docs/source.md", "docs/target.md", "assets/demo image.webp"),
    )

    assert source.is_file() and target.is_file()
    assert result.errors == ()
    assert result.markdown_files == 2
    assert result.internal_references == 8
    assert result.external_references == 1
    assert result.image_references == 2


def test_checker_validates_images_nested_inside_links(tmp_path: Path) -> None:
    checker = _load_checker()
    root = tmp_path / "repo"
    _write(root, "source.md", "[![Preview](missing.png)](target.md)\n")
    _write(root, "target.md", "# Target\n")

    result = checker.check_repository(root, _tracked("source.md", "target.md"))

    assert result.internal_references == 2
    assert result.image_references == 1
    assert len(result.errors) == 1
    assert "missing.png" in result.errors[0]


@pytest.mark.parametrize(
    "headings",
    [
        "# Foo-1\n\n# Foo\n\n# Foo\n",
        "# Foo\n\n# Foo-1\n\n# Foo\n",
    ],
)
def test_checker_handles_natural_heading_suffix_collisions(tmp_path: Path, headings: str) -> None:
    checker = _load_checker()
    root = tmp_path / "repo"
    _write(root, "source.md", "[third heading](target.md#foo-2)\n")
    _write(root, "target.md", headings)

    result = checker.check_repository(root, _tracked("source.md", "target.md"))

    assert result.errors == ()


def test_checker_reports_each_inline_reference_on_its_source_line(tmp_path: Path) -> None:
    checker = _load_checker()
    root = tmp_path / "repo"
    _write(root, "source.md", "[present](target.md)\n[missing](missing.md)\n")
    _write(root, "target.md", "# Target\n")

    result = checker.check_repository(root, _tracked("source.md", "target.md"))

    assert len(result.errors) == 1
    assert result.errors[0].startswith("source.md:2:")


@pytest.mark.parametrize(
    "source",
    [
        "`code\nmore`\n[missing](missing.md)\n",
        '[present](target.md "title\ncontinued")\n[missing](missing.md)\n',
    ],
)
def test_checker_preserves_lines_through_multiline_inline_syntax(
    tmp_path: Path, source: str
) -> None:
    checker = _load_checker()
    root = tmp_path / "repo"
    _write(root, "source.md", source)
    _write(root, "target.md", "# Target\n")

    result = checker.check_repository(root, _tracked("source.md", "target.md"))

    assert len(result.errors) == 1
    assert result.errors[0].startswith("source.md:3:")


@pytest.mark.parametrize(
    ("target", "tracked_target", "target_state", "expected"),
    [
        ("missing.md", None, "missing", "link target is not tracked"),
        ("untracked.md", None, "create", "link target is not tracked"),
        ("Target.md", "target.md", "create", "casing differs from the Git index"),
        ("../outside.md", None, "missing", "link escapes the repository"),
        ("bad%ZZ.md", None, "missing", "invalid percent encoding"),
        ("bad\\path.md", None, "missing", "must use forward slashes"),
        ("/absolute.md", None, "missing", "repository link must be relative"),
        ("ftp://example.invalid/file", None, "missing", "unsupported link scheme"),
        ("", None, "missing", "link target is empty"),
    ],
)
def test_checker_rejects_unsafe_missing_untracked_and_nonportable_targets(
    tmp_path: Path,
    target: str,
    tracked_target: str | None,
    target_state: str,
    expected: str,
) -> None:
    checker = _load_checker()
    root = tmp_path / "repo"
    _write(root, "source.md", f"[target]({target})\n")
    tracked = {"source.md"}
    if target_state == "create":
        actual = tracked_target or target
        _write(root, actual, "# Target\n")
    if tracked_target:
        tracked.add(tracked_target)

    result = checker.check_repository(root, frozenset(tracked))

    assert len(result.errors) == 1
    assert expected in result.errors[0]
    assert result.errors[0].startswith("source.md:1:")


def test_checker_rejects_unsafe_raw_html_links(tmp_path: Path) -> None:
    checker = _load_checker()
    root = tmp_path / "repo"
    _write(root, "source.md", '<a href="javascript:alert(1)">unsafe</a>\n')

    result = checker.check_repository(root, _tracked("source.md"))

    assert len(result.errors) == 1
    assert "unsafe link scheme is not allowed: javascript" in result.errors[0]


def test_checker_reports_malformed_raw_html_uri_without_raising(tmp_path: Path) -> None:
    checker = _load_checker()
    root = tmp_path / "repo"
    _write(root, "source.md", '<a href="http://[">malformed</a>\n')

    result = checker.check_repository(root, _tracked("source.md"))

    assert len(result.errors) == 1
    assert "link target is not a valid URI" in result.errors[0]


@pytest.mark.parametrize(
    "source",
    [
        "![](https://example.invalid/image.png)\n",
        '<img src="https://example.invalid/image.png" alt="">\n',
    ],
)
def test_checker_requires_alt_text_for_external_images(tmp_path: Path, source: str) -> None:
    checker = _load_checker()
    root = tmp_path / "repo"
    _write(root, "source.md", source)

    result = checker.check_repository(root, _tracked("source.md"))

    assert result.external_references == 1
    assert result.image_references == 1
    assert len(result.errors) == 1
    assert "informative image has empty alt text" in result.errors[0]


@pytest.mark.parametrize(
    ("target_state", "expected_target_error"),
    [
        ("missing", "link target is not tracked"),
        ("corrupt", "linked image is not decodable"),
    ],
)
def test_checker_reports_alt_and_local_image_integrity_errors(
    tmp_path: Path,
    target_state: str,
    expected_target_error: str,
) -> None:
    checker = _load_checker()
    root = tmp_path / "repo"
    _write(root, "source.md", "![](preview.png)\n")
    tracked = {"source.md"}
    if target_state == "corrupt":
        (root / "preview.png").write_bytes(b"not-an-image")
        tracked.add("preview.png")

    result = checker.check_repository(root, frozenset(tracked))

    assert len(result.errors) == 2
    assert any("informative image has empty alt text" in error for error in result.errors)
    assert any(expected_target_error in error for error in result.errors)


@pytest.mark.parametrize(
    "source",
    [
        '<img src="https://example.invalid/image.png" alt="   ">\n',
        '<img src="preview.png" alt="   ">\n',
    ],
)
def test_checker_rejects_whitespace_only_html_alt_text(tmp_path: Path, source: str) -> None:
    checker = _load_checker()
    root = tmp_path / "repo"
    _write(root, "source.md", source)
    image = root / "preview.png"
    Image.new("RGB", (2, 2), "blue").save(image, format="PNG")

    result = checker.check_repository(root, _tracked("source.md", "preview.png"))

    assert len(result.errors) == 1
    assert "informative image has empty alt text" in result.errors[0]


def test_checker_validates_markdown_and_code_line_fragments(tmp_path: Path) -> None:
    checker = _load_checker()
    root = tmp_path / "repo"
    _write(
        root,
        "source.md",
        "[missing](target.md#absent)\n[out of range](sample.py#L1-L4)\n",
    )
    _write(root, "target.md", "# Present\n")
    _write(root, "sample.py", "one\ntwo\nthree\n")

    result = checker.check_repository(
        root,
        _tracked("source.md", "target.md", "sample.py"),
    )

    assert len(result.errors) == 2
    assert "Markdown heading fragment does not exist: #absent" in result.errors[0]
    assert "code-line fragment #L1-L4 exceeds 3 lines" in result.errors[1]


def test_checker_does_not_treat_markdown_or_directory_fragments_as_code_lines(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    root = tmp_path / "repo"
    _write(root, "source.md", "[Markdown](target.md#L1)\n[directory](docs/#L1)\n")
    _write(root, "target.md", "# Present\n")
    _write(root, "docs/member.txt", "tracked\n")

    result = checker.check_repository(
        root,
        _tracked("source.md", "target.md", "docs/member.txt"),
    )

    assert len(result.errors) == 2
    assert any("Markdown heading fragment does not exist: #L1" in error for error in result.errors)
    assert any("directory link cannot use a fragment" in error for error in result.errors)


def test_checker_accepts_encoded_percent_and_links_to_repository_root(tmp_path: Path) -> None:
    checker = _load_checker()
    root = tmp_path / "repo"
    _write(root, "docs/source.md", "[percent](../100%25.md)\n[root](..)\n")
    _write(root, "100%.md", "# Percent\n")

    result = checker.check_repository(root, _tracked("docs/source.md", "100%.md"))

    assert result.errors == ()


def test_checker_accepts_only_real_html_named_anchors(tmp_path: Path) -> None:
    checker = _load_checker()
    root = tmp_path / "repo"
    _write(
        root,
        "source.md",
        "[legacy](target.md#legacy)\n[metadata](target.md#description)\n",
    )
    _write(
        root,
        "target.md",
        '<meta name="description"><a name="legacy"></a>\n',
    )

    result = checker.check_repository(root, _tracked("source.md", "target.md"))

    assert len(result.errors) == 1
    assert "Markdown heading fragment does not exist: #description" in result.errors[0]


def test_checker_uses_github_compatible_non_ascii_heading_lowercase(tmp_path: Path) -> None:
    checker = _load_checker()
    root = tmp_path / "repo"
    _write(root, "source.md", "[right](target.md#straße)\n[wrong](target.md#strasse)\n")
    _write(root, "target.md", "# Straße\n")

    result = checker.check_repository(root, _tracked("source.md", "target.md"))

    assert len(result.errors) == 1
    assert "Markdown heading fragment does not exist: #strasse" in result.errors[0]


@pytest.mark.parametrize(
    ("alt", "payload", "suffix", "expected"),
    [
        ("", b"valid-later", ".webp", "informative image has empty alt text"),
        ("Preview", b"not-an-image", ".webp", "linked image is not decodable"),
        ("Preview", b"valid-later", ".png", "extension expects PNG, decoded as WEBP"),
    ],
)
def test_checker_rejects_bad_image_evidence(
    tmp_path: Path,
    alt: str,
    payload: bytes,
    suffix: str,
    expected: str,
) -> None:
    checker = _load_checker()
    root = tmp_path / "repo"
    image = root / f"preview{suffix}"
    image.parent.mkdir(parents=True)
    if payload == b"valid-later":
        Image.new("RGB", (4, 4), "red").save(image, format="WEBP")
    else:
        image.write_bytes(payload)
    _write(root, "source.md", f"![{alt}]({image.name})\n")

    result = checker.check_repository(root, _tracked("source.md", image.name))

    assert len(result.errors) == 1
    assert expected in result.errors[0]


def test_checker_rejects_truncated_image_pixel_data(tmp_path: Path) -> None:
    checker = _load_checker()
    root = tmp_path / "repo"
    image = root / "preview.jpg"
    image.parent.mkdir(parents=True)
    pixels = [
        ((index * 17) % 256, (index * 31) % 256, (index * 47) % 256) for index in range(128**2)
    ]
    generated = Image.new("RGB", (128, 128))
    generated.putdata(pixels)
    generated.save(image, format="JPEG", quality=90)
    image.write_bytes(image.read_bytes()[:-50])
    _write(root, "source.md", "![Preview](preview.jpg)\n")

    result = checker.check_repository(root, _tracked("source.md", "preview.jpg"))

    assert len(result.errors) == 1
    assert "linked image is not decodable" in result.errors[0]


def test_checker_rejects_symlink_traversal_when_supported(tmp_path: Path) -> None:
    checker = _load_checker()
    root = tmp_path / "repo"
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n", encoding="utf-8")
    root.mkdir()
    linked = root / "linked.md"
    try:
        linked.symlink_to(outside)
    except OSError:
        pytest.skip("symbolic links are unavailable in this environment")
    _write(root, "source.md", "[linked](linked.md)\n")

    result = checker.check_repository(root, _tracked("source.md", "linked.md"))

    assert len(result.errors) == 1
    assert "link resolves outside the repository" in result.errors[0]


def test_checker_rejects_misleading_path_like_labels_and_sorts_failures(tmp_path: Path) -> None:
    checker = _load_checker()
    root = tmp_path / "repo"
    _write(
        root,
        "source.md",
        "[README.md](CONTRIBUTING.md)\n[z](z-missing.md)\n[a](a-missing.md)\n",
    )
    _write(root, "CONTRIBUTING.md", "# Contributing\n")

    result = checker.check_repository(root, _tracked("source.md", "CONTRIBUTING.md"))

    assert len(result.errors) == 3
    assert result.errors == tuple(sorted(result.errors))
    assert any(
        "path-like label 'README.md' does not match target 'CONTRIBUTING.md'" in error
        for error in result.errors
    )
    assert any("a-missing.md" in error for error in result.errors)
    assert any("z-missing.md" in error for error in result.errors)


def test_checker_does_not_treat_version_labels_as_file_paths(tmp_path: Path) -> None:
    checker = _load_checker()
    root = tmp_path / "repo"
    _write(root, "source.md", "[v1.2](CHANGELOG.md)\n")
    _write(root, "CHANGELOG.md", "# Changelog\n")

    result = checker.check_repository(root, _tracked("source.md", "CHANGELOG.md"))

    assert result.errors == ()
