from __future__ import annotations

import ast
from pathlib import Path

import pytest
from PIL import Image

from pptrans.adapters.renderers.base import RenderError, validate_png


def test_new_package_contains_no_dynamic_code_execution() -> None:
    package_root = Path(__file__).resolve().parents[1] / "src" / "pptrans"
    banned = {"exec", "eval", "compile"}
    findings: list[str] = []
    for source_path in package_root.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        findings.extend(
            f"{source_path}:{node.lineno}:{node.func.id}"
            for node in ast.walk(tree)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in banned
            )
        )
    assert findings == []


def test_png_pixel_boundary_is_enforced(tmp_path: Path) -> None:
    image_path = tmp_path / "large.png"
    Image.new("RGB", (20, 20), "white").save(image_path, "PNG")
    with pytest.raises(RenderError, match="dimensions"):
        validate_png(image_path, max_pixels=399)


def test_non_png_payload_is_rejected(tmp_path: Path) -> None:
    image_path = tmp_path / "pretend.png"
    image_path.write_text("not an image", encoding="utf-8")
    with pytest.raises(RenderError, match="invalid rendered PNG"):
        validate_png(image_path, max_pixels=1_000)
