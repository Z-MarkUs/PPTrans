"""Build the author-reviewed Simplified Chinese PPTrans showcase deck.

This is a deterministic fixture generator, not a translation provider benchmark.  It
routes a complete, reviewed source-to-target mapping through the same exact-ID
translation orchestration and transactional OOXML writer used by the CLI.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from pptrans.application.deck import write_translated_deck
from pptrans.application.translate import TranslationRun, translate_plan
from pptrans.domain.models import DeckPlan, DeckResult, TranslatedSpan
from pptrans.ooxml import inspect_deck
from pptrans.ports.translator import (
    ProviderUsage,
    TranslationBatchRequest,
    TranslationBatchResult,
    UnitTranslation,
)

CURATED_TRANSLATIONS: Final[Mapping[str, str]] = {
    "PPTRANS | EDITABLE PPTX LOCALIZATION": "PPTRANS | 可编辑 PPTX 本地化",
    "Translate PowerPoint.\n": "翻译 PowerPoint。\n",
    "Preserve the PowerPoint.": "保留 PowerPoint 结构。",
    "PPTrans patches only planned text nodes, verifies the package, and never overwrites "
    "the source deck.": "PPTrans 只改目标文本，验证 OOXML，绝不覆盖源文稿。",
    "github.com/Z-MarkUs/PPTrans": "github.com/Z-MarkUs/PPTrans",
    "01": "01",
    "A translation becomes a verified transaction": "让翻译成为可验证事务",
    "Three boundaries keep presentation content, formatting, and failures explicit.": (
        "三道边界使演示内容、格式与失败状态各自明确。"
    ),
    "Inspect": "检查",
    "Stable shape IDs and source hashes locate every editable text span.": (
        "形状 ID 与源哈希定位可编辑文本。"
    ),
    "02": "02",
    "Translate": "翻译",
    "Providers return strict JSON with exact unit and span IDs in order.": (
        "服务商按顺序返回包含精确单元和片段 ID 的严格 JSON。"
    ),
    "03": "03",
    "Verify": "验证",
    "Only planned text nodes may change before the output is published atomically.": (
        "发布前，只改目标文本。"
    ),
    "Structure stays fixed while text changes": "文本改变，结构不变",
    "This synthetic fixture exercises rich text, tables, Unicode, numbers, and literal "
    "values.": "此合成样例覆盖富文本、表格、Unicode、数字和字面量。",
    "Fixture": "测试项",
    "Source text": "源文本",
    "Expected target": "预期译文",
    "Preservation guard": "保留校验",
    "Emphasis": "强调样式",
    "Bold run": "粗体文本",
    "粗体文本": "粗体文本",
    "Run count unchanged": "Run 数不变",
    "Table cell": "表格单元格",
    "Gross margin": "毛利率",
    "毛利率": "毛利率",
    "Cell address stable": "单元格地址稳定",
    "Unicode": "Unicode",
    "Hello 🌏": "你好 🌏",
    "你好 🌏": "你好 🌏",
    "UTF-8 round-trip": "UTF-8 往返保真",
    "Number": "数字",
    "Q3: 42.6%": "Q3：42.6%",
    "Q3：42.6%": "Q3：42.6%",
    "Numeric token retained": "数字标记不变",
    "Literal": "字面量",
    "PPTrans v2": "PPTrans v2",
    "Exact text retained": "文本精确保留",
}


class CuratedDemoTranslator:
    """Offline adapter for the reviewed showcase fixture only."""

    provider = "curated-demo"
    model = "author-reviewed-zh-CN-v1"

    def translate(self, request: TranslationBatchRequest) -> TranslationBatchResult:
        """Return the reviewed text with the request's exact unit and span IDs."""

        if (request.source_lang, request.target_lang) != ("en", "zh-CN"):
            raise ValueError("The curated demo supports only en to zh-CN.")
        translations = []
        for unit in request.units:
            spans = tuple(
                TranslatedSpan(span_id=span.id, text=CURATED_TRANSLATIONS[span.source])
                for span in unit.spans
                if span.translatable
            )
            translations.append(UnitTranslation(unit_id=unit.id, spans=spans))
        return TranslationBatchResult(
            translations=tuple(translations),
            usage=ProviderUsage(input_tokens=0, output_tokens=0),
        )


def _validate_fixture_vocabulary(plan: DeckPlan) -> None:
    observed = {span.source for unit in plan.units for span in unit.spans if span.translatable}
    expected = set(CURATED_TRANSLATIONS)
    if observed != expected:
        missing = sorted(observed - expected)
        unused = sorted(expected - observed)
        raise ValueError(
            "The curated mapping is out of sync with the source fixture: "
            f"missing={missing!r}, unused={unused!r}"
        )


def build_curated_demo(
    source: Path,
    destination: Path,
    *,
    overwrite: bool = False,
) -> tuple[DeckResult, TranslationRun]:
    """Build and verify the deterministic author-reviewed showcase output."""

    plan = inspect_deck(source, source_lang="en", target_lang="zh-CN")
    _validate_fixture_vocabulary(plan)
    run = translate_plan(plan, CuratedDemoTranslator())
    result = write_translated_deck(
        plan,
        run.translations,
        destination,
        overwrite=overwrite,
    )
    return result, run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Committed English synthetic demo")
    parser.add_argument("destination", type=Path, help="Distinct zh-CN PPTX output")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing destination after all source safeguards pass",
    )
    args = parser.parse_args()
    result, run = build_curated_demo(args.source, args.destination, overwrite=args.overwrite)
    print(
        json.dumps(
            {
                "output": str(result.output_path),
                "output_sha256": result.report.output_sha256,
                "changed_parts": list(result.report.changed_parts),
                "verified_patches": result.report.verified_patches,
                "verified_spans": result.report.verified_spans,
                "provider": CuratedDemoTranslator.provider,
                "model": CuratedDemoTranslator.model,
                "provider_calls": run.stats.provider_calls,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
