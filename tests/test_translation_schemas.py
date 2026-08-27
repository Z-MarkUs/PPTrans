"""Strict-schema and provider-neutral serialization tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pptrans.adapters.providers import common
from pptrans.application.errors import ProviderResponseError
from pptrans.domain.models import (
    ParagraphLocator,
    SpanKind,
    TextContainer,
    TextSpan,
    TranslatedSpan,
    TranslationUnit,
)
from pptrans.ports.translator import GlossaryTerm, TranslationBatchRequest
from pptrans.schemas.translation import (
    TranslatedSpanPayload,
    TranslationBatchPayload,
    UnitTranslationPayload,
)


def _unit() -> TranslationUnit:
    return TranslationUnit(
        id="unit-1",
        locator=ParagraphLocator(
            slide_part="ppt/slides/slide1.xml",
            slide_index=0,
            shape_id_path=(7,),
            container=TextContainer.SHAPE,
            paragraph_index=0,
        ),
        spans=(
            TextSpan(
                id="span-1",
                node_index=0,
                kind=SpanKind.TEXT,
                source="Hello 世界",
                translatable=True,
            ),
            TextSpan(
                id="span-2",
                node_index=1,
                kind=SpanKind.FIELD,
                source="{locked}",
                translatable=False,
            ),
        ),
        source_digest="digest",
        context_before="Previous",
        context_after="Next",
    )


def _valid_payload() -> dict[str, object]:
    return {
        "translations": [
            {
                "unit_id": "unit-1",
                "spans": [{"span_id": "span-1", "text": "你好世界 🌏"}],
            }
        ]
    }


def test_translation_payload_accepts_only_the_documented_shape() -> None:
    payload = TranslationBatchPayload.model_validate(_valid_payload(), strict=True)

    assert payload == TranslationBatchPayload(
        translations=[
            UnitTranslationPayload(
                unit_id="unit-1",
                spans=[TranslatedSpanPayload(span_id="span-1", text="你好世界 🌏")],
            )
        ]
    )


@pytest.mark.parametrize(
    "payload",
    [
        {**_valid_payload(), "commentary": "not allowed"},
        {
            "translations": [
                {
                    "unit_id": "unit-1",
                    "spans": [{"span_id": "span-1", "text": "Bonjour"}],
                    "confidence": 0.99,
                }
            ]
        },
        {
            "translations": [
                {
                    "unit_id": "unit-1",
                    "spans": [{"span_id": "span-1", "text": "Bonjour", "source": "Hello"}],
                }
            ]
        },
    ],
    ids=["top-level-extra", "unit-extra", "span-extra"],
)
def test_translation_payload_forbids_extra_fields(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TranslationBatchPayload.model_validate(payload, strict=True)


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"translations": ()}, "translations"),
        ({"translations": [{"unit_id": 1, "spans": []}]}, "unit_id"),
        ({"translations": [{"unit_id": "unit-1", "spans": ()}]}, "spans"),
        (
            {"translations": [{"unit_id": "unit-1", "spans": [{"span_id": 1, "text": "text"}]}]},
            "span_id",
        ),
        (
            {"translations": [{"unit_id": "unit-1", "spans": [{"span_id": "span-1", "text": 1}]}]},
            "text",
        ),
    ],
)
def test_translation_payload_is_strict_about_container_and_scalar_types(
    payload: dict[str, object], field: str
) -> None:
    with pytest.raises(ValidationError) as raised:
        TranslationBatchPayload.model_validate(payload, strict=True)

    assert field in str(raised.value)


@pytest.mark.parametrize(
    "payload",
    [
        {"translations": [{"unit_id": "", "spans": []}]},
        {"translations": [{"unit_id": "u" * 161, "spans": []}]},
        {"translations": [{"unit_id": "unit-1", "spans": [{"span_id": "", "text": "value"}]}]},
        {
            "translations": [
                {
                    "unit_id": "unit-1",
                    "spans": [{"span_id": "s" * 161, "text": "value"}],
                }
            ]
        },
        {
            "translations": [
                {
                    "unit_id": "unit-1",
                    "spans": [{"span_id": "span-1", "text": ""}],
                }
            ]
        },
        {
            "translations": [
                {
                    "unit_id": "unit-1",
                    "spans": [{"span_id": "span-1", "text": "x" * 100_001}],
                }
            ]
        },
    ],
)
def test_translation_payload_enforces_identifier_and_text_bounds(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        TranslationBatchPayload.model_validate(payload, strict=True)


@pytest.mark.parametrize(
    "raw",
    [
        json.dumps(_valid_payload(), ensure_ascii=False),
        json.dumps(_valid_payload(), ensure_ascii=False).encode(),
        _valid_payload(),
    ],
    ids=["json-text", "json-bytes", "mapping"],
)
def test_parse_translation_payload_normalizes_supported_inputs(raw: object) -> None:
    result = common.parse_translation_payload(raw)  # type: ignore[arg-type]

    assert result.translations[0].unit_id == "unit-1"
    assert result.translations[0].spans == (TranslatedSpan(span_id="span-1", text="你好世界 🌏"),)


@pytest.mark.parametrize(
    "raw",
    [
        "not-json",
        b"\xff",
        [],
        {"translations": "not-a-list"},
        {"translations": [], "extra": True},
    ],
    ids=["invalid-json", "invalid-utf8", "wrong-root", "wrong-list", "extra-field"],
)
def test_parse_translation_payload_wraps_untrusted_payload_failures(raw: object) -> None:
    with pytest.raises(ProviderResponseError) as raised:
        common.parse_translation_payload(raw)  # type: ignore[arg-type]

    assert "invalid translation payload" in str(raised.value)
    assert raised.value.__cause__ is not None


def test_request_document_contains_only_translation_inputs() -> None:
    request = TranslationBatchRequest(
        units=(_unit(),),
        source_lang="en-US",
        target_lang="zh-Hant",
        glossary=(GlossaryTerm(source="Revenue", target="營收", note="finance"),),
        style="concise",
    )

    serialized = common.request_document(request)
    document = json.loads(serialized)

    assert "世界" in serialized
    assert "\\u4e16" not in serialized
    assert document == {
        "source_lang": "en-US",
        "target_lang": "zh-Hant",
        "style": "concise",
        "glossary": [{"source": "Revenue", "target": "營收", "note": "finance"}],
        "units": [
            {
                "unit_id": "unit-1",
                "context_before": "Previous",
                "context_after": "Next",
                "spans": [
                    {"span_id": "span-1", "source": "Hello 世界", "translatable": True},
                    {"span_id": "span-2", "source": "{locked}", "translatable": False},
                ],
            }
        ],
    }
    assert str(Path("source.pptx")) not in serialized
    assert "source_digest" not in serialized
    assert "slide_part" not in serialized


def test_request_document_enforces_character_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    request = TranslationBatchRequest(
        units=(_unit(),),
        source_lang="en",
        target_lang="fr",
    )
    monkeypatch.setattr(common, "MAX_REQUEST_CHARACTERS", 20)

    with pytest.raises(ValueError, match="20-character safety limit"):
        common.request_document(request)
