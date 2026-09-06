"""Deterministic translation orchestration with exact-ID validation."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256

from pptrans.application.errors import TranslationValidationError
from pptrans.domain.models import (
    MAX_TRANSLATABLE_SPANS_PER_UNIT,
    MAX_TRANSLATED_TEXT_CHARACTERS,
    DeckPlan,
    TranslatedSpan,
    TranslationInput,
    TranslationUnit,
)
from pptrans.domain.text import is_xml_10_text
from pptrans.ports.memory import TranslationMemory
from pptrans.ports.translator import (
    GlossaryTerm,
    TranslationBatchRequest,
    TranslationBatchResult,
    Translator,
    UnitTranslation,
)
from pptrans.translation_contract import (
    TRANSLATION_CONTRACT_VERSION,
    serialize_request_document,
)

MAX_BATCH_SIZE = 200
MAX_TRANSLATION_EXPANSION_RATIO = 20
MAX_TRANSLATION_EXPANSION_SLACK = 512

_PROTECTED_TOKEN = re.compile(
    r"https?://[^\s<>'\"]+"
    r"|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"
    r"|\{\{[^{}\r\n]{1,80}\}\}"
    r"|\$?\{[A-Za-z_][A-Za-z0-9_.-]{0,79}\}"
    r"|%\([A-Za-z_][A-Za-z0-9_]{0,79}\)[#0\- +]?\d*(?:\.\d+)?[diouxXeEfFgGcrs]"
    r"|%[sdif]"
)
_DIGIT_SEQUENCE = re.compile(r"\d+")


@dataclass(frozen=True, slots=True)
class TranslationOptions:
    """Policy that influences provider output and translation-memory identity."""

    glossary: tuple[GlossaryTerm, ...] = ()
    style: str | None = None
    batch_size: int = 24
    prompt_version: str = TRANSLATION_CONTRACT_VERSION
    max_provider_units: int = 2_000
    max_provider_calls: int = 100
    max_provider_source_characters: int = 2_000_000
    max_provider_request_characters: int = 5_000_000

    def __post_init__(self) -> None:
        if not 1 <= self.batch_size <= MAX_BATCH_SIZE:
            raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")
        if self.max_provider_units < 1:
            raise ValueError("max_provider_units must be at least 1")
        if self.max_provider_calls < 1:
            raise ValueError("max_provider_calls must be at least 1")
        if self.max_provider_source_characters < 1:
            raise ValueError("max_provider_source_characters must be at least 1")
        if self.max_provider_request_characters < 1:
            raise ValueError("max_provider_request_characters must be at least 1")


@dataclass(frozen=True, slots=True)
class ProviderWorkEstimate:
    """Deck-text-free upper-bound totals for one provider workload."""

    provider_units: int
    provider_calls: int
    source_context_characters: int
    request_characters: int
    largest_request_characters: int
    request_characters_per_call: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class TranslationStats:
    """Observable execution totals without retaining deck content."""

    units: int
    provider_units: int
    memory_hits: int
    provider_calls: int
    input_tokens: int | None
    output_tokens: int | None


@dataclass(frozen=True, slots=True)
class TranslationRun:
    """Complete, validated translations ready for OOXML patching."""

    translations: TranslationInput
    stats: TranslationStats


def _provider_source_characters(units: Sequence[TranslationUnit]) -> int:
    return sum(
        sum(len(span.source) for span in unit.spans)
        + len(unit.context_before or "")
        + len(unit.context_after or "")
        for unit in units
    )


def estimate_provider_work(
    units: Sequence[TranslationUnit],
    options: TranslationOptions,
    *,
    source_lang: str,
    target_lang: str,
) -> ProviderWorkEstimate:
    """Return deterministic, deck-text-free totals within configured safety ceilings."""

    unit_count = len(units)
    if any(len(unit.translatable_span_ids) > MAX_TRANSLATABLE_SPANS_PER_UNIT for unit in units):
        raise TranslationValidationError(
            "Provider work contains a unit with too many translatable spans."
        )
    if any(
        len(span.source) > MAX_TRANSLATED_TEXT_CHARACTERS
        for unit in units
        for span in unit.spans
        if span.translatable
    ):
        raise TranslationValidationError(
            "Provider work contains a translatable span above the response-size ceiling."
        )
    call_count = (unit_count + options.batch_size - 1) // options.batch_size
    source_characters = _provider_source_characters(units)
    if unit_count > options.max_provider_units:
        raise TranslationValidationError(
            f"Provider work would include {unit_count} units; "
            f"limit is {options.max_provider_units}."
        )
    if call_count > options.max_provider_calls:
        raise TranslationValidationError(
            f"Provider work would require {call_count} logical calls; "
            f"limit is {options.max_provider_calls}."
        )
    if source_characters > options.max_provider_source_characters:
        raise TranslationValidationError(
            f"Provider work would include {source_characters} source/context characters; "
            f"limit is {options.max_provider_source_characters}."
        )

    request_characters_per_call: list[int] = []
    total_request_characters = 0
    for offset in range(0, unit_count, options.batch_size):
        request = TranslationBatchRequest(
            units=tuple(units[offset : offset + options.batch_size]),
            source_lang=source_lang,
            target_lang=target_lang,
            glossary=options.glossary,
            style=options.style,
        )
        try:
            serialized = serialize_request_document(request)
        except ValueError as exc:
            raise TranslationValidationError(
                "A provider batch exceeds the per-request character safety limit."
            ) from exc
        request_characters = len(serialized)
        request_characters_per_call.append(request_characters)
        total_request_characters += request_characters
        if total_request_characters > options.max_provider_request_characters:
            raise TranslationValidationError(
                f"Provider work would serialize {total_request_characters} request characters; "
                f"limit is {options.max_provider_request_characters}."
            )

    per_call = tuple(request_characters_per_call)
    return ProviderWorkEstimate(
        provider_units=unit_count,
        provider_calls=call_count,
        source_context_characters=source_characters,
        request_characters=total_request_characters,
        largest_request_characters=max(per_call, default=0),
        request_characters_per_call=per_call,
    )


def validate_provider_budget(
    units: Sequence[TranslationUnit],
    options: TranslationOptions,
    *,
    source_lang: str,
    target_lang: str,
) -> None:
    """Fail before provider work when a run exceeds its explicit cost ceiling."""

    estimate_provider_work(
        units,
        options,
        source_lang=source_lang,
        target_lang=target_lang,
    )


def _memory_key(
    unit: TranslationUnit,
    *,
    plan: DeckPlan,
    translator: Translator,
    options: TranslationOptions,
) -> str:
    payload = {
        "schema": options.prompt_version,
        "source_lang": plan.source_lang,
        "target_lang": plan.target_lang,
        "provider": translator.provider,
        "model": translator.model,
        "style": options.style,
        "glossary": [
            {"source": term.source, "target": term.target, "note": term.note}
            for term in options.glossary
        ],
        "context_before": unit.context_before,
        "context_after": unit.context_after,
        "spans": [
            {
                "id": span.id,
                "kind": span.kind.value,
                "source": span.source,
                "translatable": span.translatable,
            }
            for span in unit.spans
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


def _validated_unit(unit: TranslationUnit, result: UnitTranslation) -> tuple[TranslatedSpan, ...]:
    if result.unit_id != unit.id:
        raise TranslationValidationError(
            f"Provider returned unit {result.unit_id!r}; expected {unit.id!r}."
        )
    expected = unit.translatable_span_ids
    actual = tuple(span.span_id for span in result.spans)
    if actual != expected:
        raise TranslationValidationError(
            f"Unit {unit.id!r} returned span IDs {actual!r}; expected {expected!r}."
        )
    source_spans = tuple(span for span in unit.spans if span.translatable)
    for source_span, translated_span in zip(source_spans, result.spans, strict=True):
        text = translated_span.text
        if "\x00" in text:
            raise TranslationValidationError(f"Unit {unit.id!r} contains a NUL character.")
        if not is_xml_10_text(text):
            raise TranslationValidationError(
                f"Unit {unit.id!r} contains a character forbidden by XML 1.0."
            )
        if not text.strip():
            raise TranslationValidationError(
                f"Unit {unit.id!r} returned an empty or whitespace-only translation."
            )
        if len(text) > MAX_TRANSLATED_TEXT_CHARACTERS:
            raise TranslationValidationError(
                f"Unit {unit.id!r} returned a translation above the schema size limit."
            )
        maximum_length = (
            len(source_span.source) * MAX_TRANSLATION_EXPANSION_RATIO
            + MAX_TRANSLATION_EXPANSION_SLACK
        )
        if len(text) > maximum_length:
            raise TranslationValidationError(
                f"Unit {unit.id!r} returned an implausibly large translation."
            )
        if _protected_tokens(text) != _protected_tokens(source_span.source):
            raise TranslationValidationError(
                f"Unit {unit.id!r} changed a protected URL, placeholder, email, or number."
            )
    return result.spans


def _protected_tokens(text: str) -> Counter[str]:
    tokens = Counter(f"literal:{match.group(0)}" for match in _PROTECTED_TOKEN.finditer(text))
    tokens.update(f"digits:{match.group(0)}" for match in _DIGIT_SEQUENCE.finditer(text))
    return tokens


def _validate_batch(
    units: tuple[TranslationUnit, ...], result: TranslationBatchResult
) -> Mapping[str, tuple[TranslatedSpan, ...]]:
    expected_ids = tuple(unit.id for unit in units)
    actual_ids = tuple(item.unit_id for item in result.translations)
    if actual_ids != expected_ids:
        raise TranslationValidationError(
            f"Provider returned unit IDs {actual_ids!r}; expected {expected_ids!r}."
        )
    return {
        unit.id: _validated_unit(unit, translated)
        for unit, translated in zip(units, result.translations, strict=True)
    }


def translate_plan(
    plan: DeckPlan,
    translator: Translator,
    *,
    memory: TranslationMemory | None = None,
    options: TranslationOptions | None = None,
) -> TranslationRun:
    """Translate all planned units, failing closed on partial or reordered output."""

    policy = options or TranslationOptions()
    translated: dict[str, tuple[TranslatedSpan, ...]] = {}
    misses: list[TranslationUnit] = []
    keys: dict[str, str] = {}
    memory_hits = 0

    for unit in plan.units:
        key = _memory_key(unit, plan=plan, translator=translator, options=policy)
        keys[unit.id] = key
        cached = memory.get(key) if memory is not None else None
        if cached is None:
            misses.append(unit)
            continue
        translated[unit.id] = _validated_unit(unit, UnitTranslation(unit_id=unit.id, spans=cached))
        memory_hits += 1

    validate_provider_budget(
        misses,
        policy,
        source_lang=plan.source_lang,
        target_lang=plan.target_lang,
    )

    provider_calls = 0
    input_tokens = 0
    output_tokens = 0
    usage_complete = True
    for offset in range(0, len(misses), policy.batch_size):
        batch = tuple(misses[offset : offset + policy.batch_size])
        request = TranslationBatchRequest(
            units=batch,
            source_lang=plan.source_lang,
            target_lang=plan.target_lang,
            glossary=policy.glossary,
            style=policy.style,
        )
        result = translator.translate(request)
        provider_calls += 1
        validated = _validate_batch(batch, result)
        translated.update(validated)
        if result.usage.input_tokens is None or result.usage.output_tokens is None:
            usage_complete = False
        else:
            input_tokens += result.usage.input_tokens
            output_tokens += result.usage.output_tokens
        if memory is not None:
            for unit in batch:
                memory.put(keys[unit.id], validated[unit.id])

    ordered: TranslationInput = {unit.id: translated[unit.id] for unit in plan.units}
    return TranslationRun(
        translations=ordered,
        stats=TranslationStats(
            units=len(plan.units),
            provider_units=len(misses),
            memory_hits=memory_hits,
            provider_calls=provider_calls,
            input_tokens=input_tokens if usage_complete else None,
            output_tokens=output_tokens if usage_complete else None,
        ),
    )


__all__ = [
    "ProviderWorkEstimate",
    "TranslationOptions",
    "TranslationRun",
    "TranslationStats",
    "estimate_provider_work",
    "translate_plan",
    "validate_provider_budget",
]
