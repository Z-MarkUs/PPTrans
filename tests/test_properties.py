"""Deterministic property tests for PPTrans's untrusted-data boundaries."""

from __future__ import annotations

import posixpath
import zipfile
from pathlib import Path
from urllib.parse import unquote

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from test_ooxml_helpers import create_complex_deck

from pptrans.application.errors import TranslationValidationError
from pptrans.application.translate import translate_plan
from pptrans.domain.errors import InvalidPresentationError, PatchValidationError
from pptrans.domain.models import (
    DeckPlan,
    ParagraphLocator,
    SpanKind,
    TextContainer,
    TextSpan,
    TranslatedSpan,
    TranslationUnit,
)
from pptrans.domain.text import is_xml_10_text
from pptrans.ooxml import inspect_deck
from pptrans.ooxml.package import _resolve_part
from pptrans.ooxml.xml import A_NS, assign_text, parse_xml, serialize_xml, validate_text
from pptrans.ports.translator import (
    ProviderUsage,
    TranslationBatchRequest,
    TranslationBatchResult,
    UnitTranslation,
)

_DETERMINISTIC = {"derandomize": True, "deadline": None, "database": None}


def _xml_10_code_point(code_point: int) -> bool:
    """Return the XML 1.0 fifth-edition ``Char`` production."""

    return (
        code_point in (0x09, 0x0A, 0x0D)
        or 0x20 <= code_point <= 0xD7FF
        or 0xE000 <= code_point <= 0xFFFD
        or 0x10000 <= code_point <= 0x10FFFF
    )


_XML_BOUNDARIES = (
    0x00,
    0x08,
    0x09,
    0x0A,
    0x0B,
    0x0C,
    0x0D,
    0x0E,
    0x1F,
    0x20,
    0xD7FF,
    0xD800,
    0xDFFF,
    0xE000,
    0xFFFD,
    0xFFFE,
    0xFFFF,
    0x10000,
    0x10FFFF,
)


@settings(max_examples=4_096, **_DETERMINISTIC)
@given(
    st.one_of(
        st.sampled_from(_XML_BOUNDARIES),
        st.integers(min_value=0, max_value=0x10FFFF),
    )
)
def test_xml_text_validation_matches_the_xml_10_character_production(
    code_point: int,
) -> None:
    text = chr(code_point)
    expected = _xml_10_code_point(code_point)

    assert is_xml_10_text(text) is expected
    if expected:
        validate_text(text)
    else:
        with pytest.raises(PatchValidationError, match=r"forbidden by XML 1\.0"):
            validate_text(text)


_VALID_XML_CHARACTER = st.one_of(
    st.sampled_from(("\t", "\n", "\r")),
    st.characters(min_codepoint=0x20, max_codepoint=0xD7FF),
    st.characters(min_codepoint=0xE000, max_codepoint=0xFFFD),
    st.characters(min_codepoint=0x10000, max_codepoint=0x10FFFF),
)


@settings(max_examples=2_000, **_DETERMINISTIC)
@given(st.text(_VALID_XML_CHARACTER, max_size=200))
def test_valid_xml_text_survives_assignment_serialization_and_reparse(text: str) -> None:
    root = parse_xml(
        f'<a:t xmlns:a="{A_NS}">seed</a:t>'.encode(),
        part_name="property-text.xml",
    )

    assign_text(root, text)
    reparsed = parse_xml(
        serialize_xml(root),
        part_name="property-text.xml",
    )

    assert (reparsed.text or "") == text


def _translation_unit() -> TranslationUnit:
    return TranslationUnit(
        id="unit-property",
        locator=ParagraphLocator(
            slide_part="ppt/slides/slide1.xml",
            slide_index=1,
            shape_id_path=(2,),
            container=TextContainer.SHAPE,
            paragraph_index=0,
        ),
        spans=tuple(
            TextSpan(
                id=f"span-{index}",
                node_index=index,
                kind=SpanKind.TEXT,
                source=("alpha", "beta", "gamma")[index],
                translatable=True,
            )
            for index in range(3)
        ),
        source_digest="property-digest",
    )


class _ResultTranslator:
    provider = "property"
    model = "property-v1"

    def __init__(self, span_ids: tuple[str, ...]) -> None:
        self.span_ids = span_ids

    def translate(self, request: TranslationBatchRequest) -> TranslationBatchResult:
        return TranslationBatchResult(
            translations=(
                UnitTranslation(
                    unit_id=request.units[0].id,
                    spans=tuple(
                        TranslatedSpan(span_id=span_id, text="translated")
                        for span_id in self.span_ids
                    ),
                ),
            ),
            usage=ProviderUsage(input_tokens=1, output_tokens=1),
        )


@settings(max_examples=1_000, **_DETERMINISTIC)
@given(
    st.lists(
        st.sampled_from(("span-0", "span-1", "span-2", "extra")),
        max_size=5,
    ).map(tuple)
)
def test_provider_span_results_are_accepted_only_in_exact_plan_order(
    span_ids: tuple[str, ...],
) -> None:
    unit = _translation_unit()
    plan = DeckPlan(
        schema_version="property",
        source_path=Path("property.pptx"),
        input_sha256="0" * 64,
        source_lang="en",
        target_lang="fr",
        slide_parts=(unit.locator.slide_part,),
        units=(unit,),
    )
    translator = _ResultTranslator(span_ids)

    if span_ids == unit.translatable_span_ids:
        run = translate_plan(plan, translator)
        assert tuple(span.span_id for span in run.translations[unit.id]) == span_ids
    else:
        with pytest.raises(TranslationValidationError, match="returned span IDs"):
            translate_plan(plan, translator)


_RELATIONSHIP_TARGET = st.lists(
    st.sampled_from(
        (
            "..",
            ".",
            "%2e%2e",
            "%2E%2E",
            "%2f",
            "%5c",
            "%00",
            "C:",
            "slides",
            "nested",
            "slide1.xml",
        )
    ),
    min_size=1,
    max_size=8,
).map("/".join)


@settings(max_examples=2_000, **_DETERMINISTIC)
@given(_RELATIONSHIP_TARGET)
def test_relationship_targets_never_resolve_outside_the_package(target: str) -> None:
    decoded = unquote(target).replace("\\", "/")
    if decoded.startswith("/"):
        candidate = decoded.lstrip("/")
    else:
        candidate = posixpath.normpath(posixpath.join("ppt", decoded))
    escaped = candidate == ".." or candidate.startswith("../")

    if escaped:
        with pytest.raises(InvalidPresentationError, match="Unsafe package member path"):
            _resolve_part("ppt/presentation.xml", target)
        return

    try:
        resolved = _resolve_part("ppt/presentation.xml", target)
    except InvalidPresentationError:
        return
    assert resolved
    assert not resolved.startswith("/")
    assert "\\" not in resolved
    assert "\x00" not in resolved
    assert ".." not in Path(resolved).parts


def test_common_relationship_target_normalizes_inside_the_package() -> None:
    assert (
        _resolve_part("ppt/presentation.xml", "slides/../slides/slide1.xml")
        == "ppt/slides/slide1.xml"
    )


def test_byte_mutated_pptx_either_inspects_or_fails_with_a_domain_error(
    tmp_path: Path,
) -> None:
    source = tmp_path / "mutated.pptx"
    pristine = tmp_path / "pristine.pptx"
    create_complex_deck(pristine)
    original = pristine.read_bytes()
    pristine_plan = inspect_deck(pristine, source_lang="en", target_lang="fr")
    assert pristine_plan.source_path == pristine.resolve()

    @settings(max_examples=250, **_DETERMINISTIC)
    @given(
        st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=len(original) - 1),
                st.integers(min_value=0, max_value=255),
            ),
            min_size=1,
            max_size=4,
        )
    )
    def check_mutation(changes: list[tuple[int, int]]) -> None:
        mutated = bytearray(original)
        for offset, value in changes:
            mutated[offset] = value
        source.write_bytes(mutated)

        try:
            plan = inspect_deck(source, source_lang="en", target_lang="fr")
        except InvalidPresentationError:
            return
        assert plan.source_path == source.resolve()
        with zipfile.ZipFile(source) as archive:
            assert archive.testzip() is None

    check_mutation()
