"""Keep the committed public demo synchronized with the real v2 pipeline."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from zipfile import ZipFile

from pptx import Presentation

from pptrans.adapters.providers.identity import IdentityTranslator
from pptrans.application.deck import write_translated_deck
from pptrans.application.translate import translate_plan
from pptrans.ooxml import inspect_deck

DEMO_PATH = Path(__file__).parents[1] / "examples" / "pptrans-demo.en.pptx"
CURATED_DEMO_PATH = Path(__file__).parents[1] / "examples" / "pptrans-demo.zh-CN.pptx"
NATIVE_QA_PATH = Path(__file__).parents[1] / "docs" / "qa" / "2026-08-28-windows-libreoffice.json"


def _load_curated_demo_script() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / "build_curated_demo.py"
    spec = importlib.util.spec_from_file_location("test_build_curated_demo", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_public_demo_runs_end_to_end_without_network(tmp_path: Path) -> None:
    plan = inspect_deck(DEMO_PATH, source_lang="en", target_lang="en")

    assert len(plan.slide_parts) == 3
    assert len(plan.units) == 41
    assert sum(len(unit.translatable_span_ids) for unit in plan.units) == 45
    assert plan.warnings == ()

    run = translate_plan(plan, IdentityTranslator())
    result = write_translated_deck(plan, run.translations, tmp_path / "demo.identity.pptx")

    assert result.report.verified_patches == 41
    assert result.report.verified_spans == 45
    assert run.stats.provider_calls == 2
    assert run.stats.input_tokens == 0
    reopened = Presentation(result.output_path)
    assert len(reopened.slides) == 3
    assert reopened.core_properties.author == "Hehan Zhao"
    assert reopened.core_properties.last_modified_by == "Hehan Zhao"
    assert reopened.core_properties.title == "PPTrans v2 - verifiable OOXML translation demo"
    assert reopened.core_properties.subject.startswith("Synthetic fixture")


def test_native_qa_record_is_pinned_to_the_committed_demo() -> None:
    record = json.loads(NATIVE_QA_PATH.read_text(encoding="utf-8"))
    demo_bytes = DEMO_PATH.read_bytes()
    demo_sha256 = hashlib.sha256(demo_bytes).hexdigest()

    assert record["schema_version"] == 1
    assert record["presentations"]["source"] == {
        "path": "examples/pptrans-demo.en.pptx",
        "bytes": len(demo_bytes),
        "sha256": demo_sha256,
    }
    assert record["presentations"]["identity_output"] == {
        "bytes": len(demo_bytes),
        "sha256": demo_sha256,
        "byte_identical_to_source": True,
    }
    assert [slide["slide_number"] for slide in record["slides"]] == [1, 2, 3]
    assert all(slide["pixel_equal"] is True for slide in record["slides"])
    assert all(
        slide["source_png_sha256"] == slide["identity_png_sha256"] for slide in record["slides"]
    )
    assert record["visual_review"]["reviewed_slide_count"] == 3
    assert record["cleanup"] == {
        "private_render_workspace_present_after_success": False,
        "publication_staging_present_after_success": False,
        "libreoffice_process_present_after_success": False,
    }


def test_curated_zh_cn_demo_is_reproducible_and_structurally_verified(tmp_path: Path) -> None:
    curated = _load_curated_demo_script()
    rebuilt = tmp_path / "pptrans-demo.zh-CN.pptx"
    result, run = curated.build_curated_demo(DEMO_PATH, rebuilt)

    assert rebuilt.read_bytes() == CURATED_DEMO_PATH.read_bytes()
    assert result.report.changed_parts == (
        "ppt/slides/slide1.xml",
        "ppt/slides/slide2.xml",
        "ppt/slides/slide3.xml",
    )
    assert result.report.verified_patches == 41
    assert result.report.verified_spans == 45
    assert run.stats.provider_calls == 2
    assert run.stats.input_tokens == 0
    assert run.stats.output_tokens == 0

    with ZipFile(DEMO_PATH) as source, ZipFile(rebuilt) as target:
        assert source.namelist() == target.namelist()
        changed_members = {
            name for name in source.namelist() if source.read(name) != target.read(name)
        }
    assert changed_members == set(result.report.changed_parts)

    source_plan = inspect_deck(DEMO_PATH, source_lang="en", target_lang="zh-CN")
    target_plan = inspect_deck(CURATED_DEMO_PATH, source_lang="zh-CN", target_lang="en")
    for source_unit, target_unit in zip(source_plan.units, target_plan.units, strict=True):
        assert target_unit.locator == source_unit.locator
        assert tuple(span.id for span in target_unit.spans) == tuple(
            span.id for span in source_unit.spans
        )
        for source_span, target_span in zip(source_unit.spans, target_unit.spans, strict=True):
            assert target_span.source == curated.CURATED_TRANSLATIONS[source_span.source]

    reopened = Presentation(CURATED_DEMO_PATH)
    assert len(reopened.slides) == 3
    assert reopened.core_properties.author == "Hehan Zhao"
