"""Deterministic orchestration and translation-memory contract tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from pptrans.adapters.providers.identity import IdentityTranslator
from pptrans.application.errors import TranslationValidationError
from pptrans.application.translate import TranslationOptions, translate_plan
from pptrans.domain.models import (
    DeckPlan,
    ParagraphLocator,
    SpanKind,
    TextContainer,
    TextSpan,
    TranslatedSpan,
    TranslationUnit,
)
from pptrans.ports.translator import (
    GlossaryTerm,
    ProviderUsage,
    TranslationBatchRequest,
    TranslationBatchResult,
    UnitTranslation,
)
from pptrans.schemas.translation import TranslationBatchPayload
from pptrans.translation_contract import (
    MAX_REQUEST_CHARACTERS,
    SYSTEM_INSTRUCTIONS,
    TRANSLATION_CONTRACT_VERSION,
    translation_contract_version,
)


def _unit(
    index: int,
    *,
    sources: tuple[str, ...] = ("Hello",),
    translatable: tuple[bool, ...] | None = None,
    context_before: str | None = None,
    context_after: str | None = None,
) -> TranslationUnit:
    flags = translatable or tuple(True for _ in sources)
    assert len(flags) == len(sources)
    return TranslationUnit(
        id=f"unit-{index}",
        locator=ParagraphLocator(
            slide_part="ppt/slides/slide1.xml",
            slide_index=0,
            shape_id_path=(index + 1,),
            container=TextContainer.SHAPE,
            paragraph_index=0,
        ),
        spans=tuple(
            TextSpan(
                id=f"unit-{index}-span-{span_index}",
                node_index=span_index,
                kind=SpanKind.TEXT,
                source=source,
                translatable=flags[span_index],
            )
            for span_index, source in enumerate(sources)
        ),
        source_digest=f"digest-{index}",
        context_before=context_before,
        context_after=context_after,
    )


def _plan(
    units: tuple[TranslationUnit, ...],
    *,
    source_lang: str = "en",
    target_lang: str = "fr",
    input_sha256: str = "a" * 64,
) -> DeckPlan:
    return DeckPlan(
        schema_version="2",
        source_path=Path("source.pptx"),
        input_sha256=input_sha256,
        source_lang=source_lang,
        target_lang=target_lang,
        slide_parts=("ppt/slides/slide1.xml",),
        units=units,
    )


def _translated_unit(unit: TranslationUnit, *, suffix: str = "-translated") -> UnitTranslation:
    return UnitTranslation(
        unit_id=unit.id,
        spans=tuple(
            TranslatedSpan(span_id=span.id, text=f"{span.source}{suffix}")
            for span in unit.spans
            if span.translatable
        ),
    )


class _EchoTranslator:
    def __init__(
        self,
        *,
        provider: str = "fake",
        model: str = "fake-v1",
        responder: Callable[[TranslationBatchRequest], TranslationBatchResult] | None = None,
        usage: ProviderUsage | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.calls: list[TranslationBatchRequest] = []
        self._responder = responder
        self._usage = usage or ProviderUsage(input_tokens=10, output_tokens=5)

    def translate(self, request: TranslationBatchRequest) -> TranslationBatchResult:
        self.calls.append(request)
        if self._responder is not None:
            return self._responder(request)
        return TranslationBatchResult(
            translations=tuple(_translated_unit(unit) for unit in request.units),
            usage=self._usage,
        )


class _DictionaryMemory:
    def __init__(self) -> None:
        self.data: dict[str, tuple[TranslatedSpan, ...]] = {}
        self.gets: list[str] = []
        self.puts: list[tuple[str, tuple[TranslatedSpan, ...]]] = []

    def get(self, key: str) -> tuple[TranslatedSpan, ...] | None:
        self.gets.append(key)
        return self.data.get(key)

    def put(self, key: str, spans: tuple[TranslatedSpan, ...]) -> None:
        self.puts.append((key, spans))
        self.data[key] = spans


def test_translate_plan_batches_in_order_and_aggregates_complete_usage() -> None:
    units = tuple(_unit(index, sources=(f"Text {index}",)) for index in range(5))
    plan = _plan(units)
    translator = _EchoTranslator()
    glossary = (GlossaryTerm(source="Text", target="Texte", note="noun"),)
    options = TranslationOptions(glossary=glossary, style="formal", batch_size=2)

    run = translate_plan(plan, translator, options=options)

    assert [tuple(unit.id for unit in call.units) for call in translator.calls] == [
        ("unit-0", "unit-1"),
        ("unit-2", "unit-3"),
        ("unit-4",),
    ]
    assert all(call.source_lang == "en" for call in translator.calls)
    assert all(call.target_lang == "fr" for call in translator.calls)
    assert all(call.glossary == glossary for call in translator.calls)
    assert all(call.style == "formal" for call in translator.calls)
    assert tuple(run.translations) == tuple(unit.id for unit in units)
    assert run.translations["unit-3"] == (
        TranslatedSpan(span_id="unit-3-span-0", text="Text 3-translated"),
    )
    assert run.stats.units == 5
    assert run.stats.provider_units == 5
    assert run.stats.memory_hits == 0
    assert run.stats.provider_calls == 3
    assert run.stats.input_tokens == 30
    assert run.stats.output_tokens == 15


@pytest.mark.parametrize("mode", ["missing", "extra", "reordered", "duplicate"])
def test_translate_plan_rejects_partial_extra_or_reordered_units(mode: str) -> None:
    units = (_unit(0), _unit(1))

    def respond(request: TranslationBatchRequest) -> TranslationBatchResult:
        translated = tuple(_translated_unit(unit) for unit in request.units)
        if mode == "missing":
            translated = translated[:-1]
        elif mode == "extra":
            translated += (UnitTranslation(unit_id="extra", spans=()),)
        elif mode == "reordered":
            translated = tuple(reversed(translated))
        else:
            translated = (translated[0], translated[0])
        return TranslationBatchResult(translations=translated)

    with pytest.raises(TranslationValidationError, match="Provider returned unit IDs"):
        translate_plan(_plan(units), _EchoTranslator(responder=respond))


@pytest.mark.parametrize(
    "actual_ids",
    [
        ("unit-0-span-0",),
        ("unit-0-span-0", "extra", "unit-0-span-1"),
        ("unit-0-span-1", "unit-0-span-0"),
        ("unit-0-span-0", "unit-0-span-0"),
        ("wrong", "unit-0-span-1"),
    ],
    ids=["missing", "extra", "reordered", "duplicate", "wrong"],
)
def test_translate_plan_rejects_any_span_id_or_order_mismatch(
    actual_ids: tuple[str, ...],
) -> None:
    unit = _unit(0, sources=("Hello", "world"))

    def respond(_request: TranslationBatchRequest) -> TranslationBatchResult:
        return TranslationBatchResult(
            translations=(
                UnitTranslation(
                    unit_id=unit.id,
                    spans=tuple(
                        TranslatedSpan(span_id=span_id, text="translated") for span_id in actual_ids
                    ),
                ),
            )
        )

    with pytest.raises(TranslationValidationError, match="returned span IDs"):
        translate_plan(_plan((unit,)), _EchoTranslator(responder=respond))


def test_translate_plan_rejects_a_translation_for_a_locked_span() -> None:
    unit = _unit(0, sources=("Hello", "2026"), translatable=(True, False))

    def respond(_request: TranslationBatchRequest) -> TranslationBatchResult:
        return TranslationBatchResult(
            translations=(
                UnitTranslation(
                    unit_id=unit.id,
                    spans=(
                        TranslatedSpan(span_id="unit-0-span-0", text="Bonjour"),
                        TranslatedSpan(span_id="unit-0-span-1", text="2026"),
                    ),
                ),
            )
        )

    with pytest.raises(TranslationValidationError, match="returned span IDs"):
        translate_plan(_plan((unit,)), _EchoTranslator(responder=respond))


def test_translate_plan_rejects_nul_characters() -> None:
    unit = _unit(0)

    def respond(_request: TranslationBatchRequest) -> TranslationBatchResult:
        return TranslationBatchResult(
            translations=(
                UnitTranslation(
                    unit_id=unit.id,
                    spans=(TranslatedSpan(span_id="unit-0-span-0", text="bad\x00text"),),
                ),
            )
        )

    with pytest.raises(TranslationValidationError, match="NUL"):
        translate_plan(_plan((unit,)), _EchoTranslator(responder=respond))


@pytest.mark.parametrize("invalid_text", ["bad\x0btext", "bad\ud800text"])
def test_forbidden_xml_characters_never_enter_translation_memory(
    invalid_text: str,
) -> None:
    unit = _unit(0)
    memory = _DictionaryMemory()

    def respond(_request: TranslationBatchRequest) -> TranslationBatchResult:
        return TranslationBatchResult(
            translations=(
                UnitTranslation(
                    unit_id=unit.id,
                    spans=(TranslatedSpan(span_id="unit-0-span-0", text=invalid_text),),
                ),
            )
        )

    with pytest.raises(TranslationValidationError, match=r"forbidden by XML 1\.0"):
        translate_plan(
            _plan((unit,)),
            _EchoTranslator(responder=respond),
            memory=memory,
        )

    assert memory.puts == []
    assert memory.data == {}


@pytest.mark.parametrize("translated_text", ["", " \t\n"])
def test_translate_plan_rejects_blank_visible_text(translated_text: str) -> None:
    unit = _unit(0)

    def respond(_request: TranslationBatchRequest) -> TranslationBatchResult:
        return TranslationBatchResult(
            translations=(
                UnitTranslation(
                    unit_id=unit.id,
                    spans=(TranslatedSpan(span_id="unit-0-span-0", text=translated_text),),
                ),
            )
        )

    with pytest.raises(TranslationValidationError, match="empty or whitespace-only"):
        translate_plan(_plan((unit,)), _EchoTranslator(responder=respond))


def test_translate_plan_rejects_implausible_expansion() -> None:
    unit = _unit(0, sources=("Short",))

    def respond(_request: TranslationBatchRequest) -> TranslationBatchResult:
        return TranslationBatchResult(
            translations=(
                UnitTranslation(
                    unit_id=unit.id,
                    spans=(TranslatedSpan(span_id="unit-0-span-0", text="x" * 700),),
                ),
            )
        )

    with pytest.raises(TranslationValidationError, match="implausibly large"):
        translate_plan(_plan((unit,)), _EchoTranslator(responder=respond))


@pytest.mark.parametrize(
    "translation",
    [
        "Consultez https://different.invalid pour {name} en 2026.",
        "Consultez https://example.com pour {other} en 2026.",
        "Consultez https://example.com pour {name} en 2027.",
    ],
    ids=["url", "placeholder", "number"],
)
def test_translate_plan_rejects_changed_protected_tokens(translation: str) -> None:
    unit = _unit(0, sources=("Visit https://example.com for {name} in 2026.",))

    def respond(_request: TranslationBatchRequest) -> TranslationBatchResult:
        return TranslationBatchResult(
            translations=(
                UnitTranslation(
                    unit_id=unit.id,
                    spans=(TranslatedSpan(span_id="unit-0-span-0", text=translation),),
                ),
            )
        )

    with pytest.raises(TranslationValidationError, match="changed a protected"):
        translate_plan(_plan((unit,)), _EchoTranslator(responder=respond))


def test_translate_plan_accepts_reordered_but_unchanged_protected_tokens() -> None:
    unit = _unit(0, sources=("Email mark@example.com with {code} before 2026.",))

    def respond(_request: TranslationBatchRequest) -> TranslationBatchResult:
        return TranslationBatchResult(
            translations=(
                UnitTranslation(
                    unit_id=unit.id,
                    spans=(
                        TranslatedSpan(
                            span_id="unit-0-span-0",
                            text="Avant 2026, utilisez {code} et mark@example.com.",
                        ),
                    ),
                ),
            )
        )

    run = translate_plan(_plan((unit,)), _EchoTranslator(responder=respond))

    assert run.translations[unit.id][0].text.startswith("Avant 2026")


def test_translation_memory_turns_a_second_run_into_exact_hits() -> None:
    plan = _plan((_unit(0), _unit(1)))
    memory = _DictionaryMemory()
    first_translator = _EchoTranslator()

    first = translate_plan(plan, first_translator, memory=memory)
    second_translator = _EchoTranslator()
    second = translate_plan(plan, second_translator, memory=memory)

    assert len(first_translator.calls) == 1
    assert len(memory.puts) == 2
    assert second_translator.calls == []
    assert second.translations == first.translations
    assert second.stats.units == 2
    assert second.stats.provider_units == 0
    assert second.stats.memory_hits == 2
    assert second.stats.provider_calls == 0
    assert second.stats.input_tokens == 0
    assert second.stats.output_tokens == 0


def test_translation_memory_batches_only_misses_and_preserves_plan_order() -> None:
    plan = _plan((_unit(0), _unit(1), _unit(2)))
    memory = _DictionaryMemory()
    translate_plan(plan, _EchoTranslator(), memory=memory)
    removed_key = tuple(memory.data)[1]
    del memory.data[removed_key]
    translator = _EchoTranslator()

    run = translate_plan(plan, translator, memory=memory)

    assert len(translator.calls) == 1
    assert tuple(unit.id for unit in translator.calls[0].units) == ("unit-1",)
    assert tuple(run.translations) == ("unit-0", "unit-1", "unit-2")
    assert run.stats.provider_units == 1
    assert run.stats.memory_hits == 2


def test_cached_units_do_not_consume_provider_budget() -> None:
    plan = _plan((_unit(0), _unit(1)))
    memory = _DictionaryMemory()
    translate_plan(plan, _EchoTranslator(), memory=memory)
    translator = _EchoTranslator()

    run = translate_plan(
        plan,
        translator,
        memory=memory,
        options=TranslationOptions(
            max_provider_units=1,
            max_provider_calls=1,
            max_provider_source_characters=1,
        ),
    )

    assert translator.calls == []
    assert run.stats.memory_hits == 2
    assert run.stats.provider_units == 0


def test_invalid_cached_spans_fail_before_any_provider_call() -> None:
    plan = _plan((_unit(0),))
    memory = _DictionaryMemory()
    translate_plan(plan, _EchoTranslator(), memory=memory)
    only_key = next(iter(memory.data))
    memory.data[only_key] = (TranslatedSpan(span_id="wrong", text="stale"),)
    translator = _EchoTranslator()

    with pytest.raises(TranslationValidationError, match="returned span IDs"):
        translate_plan(plan, translator, memory=memory)

    assert translator.calls == []


def test_forbidden_xml_character_in_cached_row_fails_before_provider() -> None:
    plan = _plan((_unit(0),))
    memory = _DictionaryMemory()
    translate_plan(plan, _EchoTranslator(), memory=memory)
    only_key = next(iter(memory.data))
    memory.data[only_key] = (TranslatedSpan(span_id="unit-0-span-0", text="poisoned\x0brow"),)
    translator = _EchoTranslator()

    with pytest.raises(TranslationValidationError, match=r"forbidden by XML 1\.0"):
        translate_plan(plan, translator, memory=memory)

    assert translator.calls == []


def test_invalid_provider_batch_is_not_written_to_memory() -> None:
    unit = _unit(0)
    memory = _DictionaryMemory()

    def respond(_request: TranslationBatchRequest) -> TranslationBatchResult:
        return TranslationBatchResult(translations=())

    with pytest.raises(TranslationValidationError):
        translate_plan(
            _plan((unit,)),
            _EchoTranslator(responder=respond),
            memory=memory,
        )

    assert memory.puts == []
    assert memory.data == {}


@pytest.mark.parametrize(
    "variation",
    [
        "source-lang",
        "target-lang",
        "provider",
        "model",
        "style",
        "prompt-version",
        "glossary",
        "context-before",
        "context-after",
        "source-text",
        "segmentation",
        "translatability",
    ],
)
def test_translation_memory_key_invalidates_every_semantic_input(variation: str) -> None:
    base_unit = _unit(
        0,
        sources=("Hello", " world"),
        context_before="Before",
        context_after="After",
    )
    first_plan = _plan((base_unit,))
    second_plan = first_plan
    first_translator = _EchoTranslator()
    second_translator = _EchoTranslator()
    first_options = TranslationOptions(style="formal")
    second_options = first_options

    if variation == "source-lang":
        second_plan = replace(second_plan, source_lang="de")
    elif variation == "target-lang":
        second_plan = replace(second_plan, target_lang="es")
    elif variation == "provider":
        second_translator.provider = "another-provider"
    elif variation == "model":
        second_translator.model = "another-model"
    elif variation == "style":
        second_options = replace(second_options, style="casual")
    elif variation == "prompt-version":
        second_options = replace(second_options, prompt_version="pptrans-translate/v3")
    elif variation == "glossary":
        second_options = replace(
            second_options,
            glossary=(GlossaryTerm(source="Hello", target="Bonjour"),),
        )
    elif variation == "context-before":
        second_plan = replace(
            second_plan,
            units=(replace(base_unit, context_before="Changed before"),),
        )
    elif variation == "context-after":
        second_plan = replace(
            second_plan,
            units=(replace(base_unit, context_after="Changed after"),),
        )
    elif variation == "source-text":
        changed = replace(base_unit.spans[0], source="Changed")
        changed_unit = replace(base_unit, spans=(changed, *base_unit.spans[1:]))
        second_plan = replace(second_plan, units=(changed_unit,))
    elif variation == "segmentation":
        second_plan = replace(second_plan, units=(_unit(0, sources=("Hello world",)),))
    else:
        changed = replace(base_unit.spans[1], translatable=False)
        changed_unit = replace(base_unit, spans=(base_unit.spans[0], changed))
        second_plan = replace(second_plan, units=(changed_unit,))

    memory = _DictionaryMemory()
    translate_plan(first_plan, first_translator, memory=memory, options=first_options)
    second = translate_plan(
        second_plan,
        second_translator,
        memory=memory,
        options=second_options,
    )

    assert second.stats.memory_hits == 0
    assert second.stats.provider_units == 1
    assert len(second_translator.calls) == 1
    assert len(memory.data) == 2


def test_nonsemantic_deck_identity_and_batch_size_reuse_memory() -> None:
    unit = _unit(0)
    first_plan = _plan((unit,), input_sha256="a" * 64)
    second_plan = replace(
        first_plan,
        source_path=Path("another-deck.pptx"),
        input_sha256="b" * 64,
    )
    memory = _DictionaryMemory()
    translate_plan(
        first_plan,
        IdentityTranslator(),
        memory=memory,
        options=TranslationOptions(batch_size=1),
    )

    second = translate_plan(
        second_plan,
        IdentityTranslator(),
        memory=memory,
        options=TranslationOptions(batch_size=200),
    )

    assert second.stats.memory_hits == 1
    assert second.stats.provider_calls == 0


def test_incomplete_usage_in_any_batch_marks_the_total_unknown() -> None:
    calls = 0

    def respond(request: TranslationBatchRequest) -> TranslationBatchResult:
        nonlocal calls
        calls += 1
        usage = (
            ProviderUsage(input_tokens=10, output_tokens=5)
            if calls == 1
            else ProviderUsage(input_tokens=None, output_tokens=4)
        )
        return TranslationBatchResult(
            translations=tuple(_translated_unit(unit) for unit in request.units),
            usage=usage,
        )

    run = translate_plan(
        _plan((_unit(0), _unit(1))),
        _EchoTranslator(responder=respond),
        options=TranslationOptions(batch_size=1),
    )

    assert run.stats.input_tokens is None
    assert run.stats.output_tokens is None


def test_empty_plan_never_calls_the_provider() -> None:
    translator = _EchoTranslator()

    run = translate_plan(_plan(()), translator)

    assert run.translations == {}
    assert translator.calls == []
    assert run.stats.units == 0
    assert run.stats.provider_calls == 0
    assert run.stats.input_tokens == 0
    assert run.stats.output_tokens == 0


@pytest.mark.parametrize(
    ("options", "message"),
    [
        (TranslationOptions(max_provider_units=1), "2 units"),
        (
            TranslationOptions(batch_size=1, max_provider_calls=1),
            "2 logical calls",
        ),
        (
            TranslationOptions(max_provider_source_characters=3),
            "source/context characters",
        ),
        (
            TranslationOptions(
                batch_size=1,
                glossary=(GlossaryTerm(source="source", target="target"),),
                max_provider_request_characters=100,
            ),
            "request characters",
        ),
    ],
    ids=["units", "calls", "source-characters", "request-characters"],
)
def test_provider_budgets_fail_before_any_provider_call(
    options: TranslationOptions,
    message: str,
) -> None:
    translator = _EchoTranslator()
    plan = _plan(
        (
            _unit(0, sources=("one",), context_before="before"),
            _unit(1, sources=("two",), context_after="after"),
        )
    )

    with pytest.raises(TranslationValidationError, match=message):
        translate_plan(plan, translator, options=options)

    assert translator.calls == []


@pytest.mark.parametrize(
    ("plan", "message"),
    [
        (
            _plan((_unit(0, sources=tuple("x" for _ in range(10_001))),)),
            "too many translatable spans",
        ),
        (
            _plan((_unit(0, sources=("x" * 100_001,)),)),
            "response-size ceiling",
        ),
    ],
    ids=["per-unit-span-count", "per-span-source-characters"],
)
def test_schema_impossible_units_fail_before_any_provider_call(
    plan: DeckPlan,
    message: str,
) -> None:
    translator = _EchoTranslator()

    with pytest.raises(TranslationValidationError, match=message):
        translate_plan(plan, translator)

    assert translator.calls == []


def test_oversized_translated_span_fails_before_memory_write() -> None:
    unit = _unit(0, sources=("x" * 6_000,))
    memory = _DictionaryMemory()

    def respond(_request: TranslationBatchRequest) -> TranslationBatchResult:
        return TranslationBatchResult(
            translations=(
                UnitTranslation(
                    unit_id=unit.id,
                    spans=(
                        TranslatedSpan(
                            span_id="unit-0-span-0",
                            text="y" * 100_001,
                        ),
                    ),
                ),
            )
        )

    with pytest.raises(TranslationValidationError, match="schema size limit"):
        translate_plan(
            _plan((unit,)),
            _EchoTranslator(responder=respond),
            memory=memory,
        )

    assert memory.puts == []


@pytest.mark.parametrize("batch_size", [0, -1, 201])
def test_translation_options_reject_invalid_batch_sizes(batch_size: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 200"):
        TranslationOptions(batch_size=batch_size)


@pytest.mark.parametrize("batch_size", [1, 200])
def test_translation_options_accept_boundary_batch_sizes(batch_size: int) -> None:
    assert TranslationOptions(batch_size=batch_size).batch_size == batch_size


@pytest.mark.parametrize(
    "changes",
    [
        {"max_provider_units": 0},
        {"max_provider_calls": 0},
        {"max_provider_source_characters": 0},
        {"max_provider_request_characters": 0},
    ],
)
def test_translation_options_reject_nonpositive_provider_budgets(
    changes: dict[str, int],
) -> None:
    with pytest.raises(ValueError, match="must be at least 1"):
        TranslationOptions(**changes)


def test_provider_policy_defaults_are_pinned_to_documented_limits() -> None:
    options = TranslationOptions()

    assert options.batch_size == 24
    assert options.max_provider_units == 2_000
    assert options.max_provider_calls == 100
    assert options.max_provider_source_characters == 2_000_000
    assert options.max_provider_request_characters == 5_000_000
    assert MAX_REQUEST_CHARACTERS == 1_000_000


def test_translation_contract_version_tracks_prompt_and_schema() -> None:
    schema = TranslationBatchPayload.model_json_schema()

    assert translation_contract_version() == TRANSLATION_CONTRACT_VERSION
    assert (
        translation_contract_version(SYSTEM_INSTRUCTIONS + "\nChanged behavior.", schema)
        != TRANSLATION_CONTRACT_VERSION
    )
    changed_schema = {**schema, "description": "Changed response contract"}
    assert (
        translation_contract_version(SYSTEM_INSTRUCTIONS, changed_schema)
        != TRANSLATION_CONTRACT_VERSION
    )
