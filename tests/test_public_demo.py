"""Keep the committed public demo synchronized with the real v2 pipeline."""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation

from pptrans.adapters.providers.identity import IdentityTranslator
from pptrans.application.deck import write_translated_deck
from pptrans.application.translate import translate_plan
from pptrans.ooxml import inspect_deck

DEMO_PATH = Path(__file__).parents[1] / "examples" / "pptrans-demo.en.pptx"


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
