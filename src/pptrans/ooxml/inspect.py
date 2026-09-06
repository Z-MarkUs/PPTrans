"""Inspection of text-bearing paragraphs without reconstructing slide content."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

from lxml import etree

from pptrans.domain.errors import InvalidPresentationError, SourceChangedError
from pptrans.domain.models import (
    DeckPlan,
    Diagnostic,
    PackageLimits,
    ParagraphLocator,
    TextContainer,
    TranslationUnit,
)

from .locate import extract_spans, source_digest, table_for_shape, walk_shapes
from .package import (
    discover_slide_parts,
    file_sha256,
    open_package,
    read_xml_part,
    validate_archive_payloads,
)
from .xml import A_P, A_TC, A_TR, NS, P_CONTENT_PART, P_GRAPHIC_FRAME, parse_xml

PLAN_SCHEMA_VERSION = "pptrans.deck-plan/v2"


def _unit(locator: ParagraphLocator, paragraph: etree._Element) -> TranslationUnit | None:
    spans = extract_spans(paragraph)
    if not any(span.translatable for span in spans):
        return None
    digest = source_digest(locator, spans)
    identifier = sha256(f"{PLAN_SCHEMA_VERSION}:{digest}".encode()).hexdigest()[:24]
    return TranslationUnit(
        id=f"u-{identifier}",
        locator=locator,
        spans=spans,
        source_digest=digest,
    )


def _shape_text_units(
    shape: etree._Element,
    *,
    slide_part: str,
    slide_index: int,
    shape_path: tuple[int, ...],
) -> Iterator[TranslationUnit]:
    body = shape.find("./p:txBody", NS)
    if body is None:
        return
    for paragraph_index, paragraph in enumerate(body.findall(f"./{A_P}")):
        locator = ParagraphLocator(
            slide_part=slide_part,
            slide_index=slide_index,
            shape_id_path=shape_path,
            container=TextContainer.SHAPE,
            paragraph_index=paragraph_index,
        )
        candidate = _unit(locator, paragraph)
        if candidate is not None:
            yield candidate


def _table_units(
    table: etree._Element,
    *,
    slide_part: str,
    slide_index: int,
    shape_path: tuple[int, ...],
) -> Iterator[TranslationUnit]:
    for row_index, row in enumerate(table.findall(f"./{A_TR}")):
        for column_index, cell in enumerate(row.findall(f"./{A_TC}")):
            body = cell.find(f"./{{{NS['a']}}}txBody")
            if body is None:
                continue
            for paragraph_index, paragraph in enumerate(body.findall(f"./{A_P}")):
                locator = ParagraphLocator(
                    slide_part=slide_part,
                    slide_index=slide_index,
                    shape_id_path=shape_path,
                    container=TextContainer.TABLE_CELL,
                    cell=(row_index, column_index),
                    paragraph_index=paragraph_index,
                )
                candidate = _unit(locator, paragraph)
                if candidate is not None:
                    yield candidate


@dataclass(slots=True)
class _InspectionBudget:
    """Incrementally bound semantic work derived from untrusted slide XML."""

    limits: PackageLimits
    units: int = 0
    spans: int = 0
    source_characters: int = 0
    diagnostics: int = 0

    def check_slide(self, root: etree._Element) -> None:
        element_count = sum(1 for _ in root.iter())
        if element_count > self.limits.max_xml_elements_per_part:
            raise InvalidPresentationError(
                "A slide XML part exceeds the element-count safety limit."
            )

    def accept_unit(self, unit: TranslationUnit) -> None:
        translatable_spans = tuple(span for span in unit.spans if span.translatable)
        if len(translatable_spans) > self.limits.max_translatable_spans_per_unit:
            raise InvalidPresentationError(
                "A translation unit exceeds the translatable-span safety limit."
            )
        if any(
            len(span.source) > self.limits.max_source_characters_per_span
            for span in translatable_spans
        ):
            raise InvalidPresentationError(
                "A translatable text span exceeds the per-span character safety limit."
            )
        next_units = self.units + 1
        next_spans = self.spans + len(unit.spans)
        next_characters = self.source_characters + sum(len(span.source) for span in unit.spans)
        if next_units > self.limits.max_translation_units:
            raise InvalidPresentationError("PPTX exceeds the translation-unit safety limit.")
        if next_spans > self.limits.max_text_spans:
            raise InvalidPresentationError("PPTX exceeds the text-span safety limit.")
        if next_characters > self.limits.max_source_characters:
            raise InvalidPresentationError("PPTX exceeds the source-character safety limit.")
        self.units = next_units
        self.spans = next_spans
        self.source_characters = next_characters

    def accept_diagnostic(self) -> None:
        if self.diagnostics >= self.limits.max_diagnostics:
            raise InvalidPresentationError("PPTX exceeds the diagnostic safety limit.")
        self.diagnostics += 1


def _append_units(
    destination: list[TranslationUnit],
    candidates: Iterator[TranslationUnit],
    budget: _InspectionBudget,
) -> None:
    for candidate in candidates:
        budget.accept_unit(candidate)
        destination.append(candidate)


def _attach_context(units: list[TranslationUnit]) -> tuple[TranslationUnit, ...]:
    contextualized: list[TranslationUnit] = []
    for index, unit in enumerate(units):
        previous = units[index - 1] if index else None
        following = units[index + 1] if index + 1 < len(units) else None
        before = (
            previous.source_text
            if previous is not None and previous.locator.slide_part == unit.locator.slide_part
            else None
        )
        after = (
            following.source_text
            if following is not None and following.locator.slide_part == unit.locator.slide_part
            else None
        )
        contextualized.append(replace(unit, context_before=before, context_after=after))
    return tuple(contextualized)


def inspect_deck(
    path: Path,
    *,
    source_lang: str,
    target_lang: str,
    limits: PackageLimits | None = None,
) -> DeckPlan:
    """Create an immutable, source-guarded translation plan for *path*."""

    source = Path(path).expanduser().resolve()
    if not source_lang.strip() or not target_lang.strip():
        raise ValueError("Source and target language codes must be non-empty.")

    initial_hash = file_sha256(source)
    units: list[TranslationUnit] = []
    warnings: list[Diagnostic] = []
    policy = limits or PackageLimits()
    budget = _InspectionBudget(policy)
    with open_package(source, policy) as archive:
        validate_archive_payloads(archive)
        slide_parts = discover_slide_parts(archive, policy)
        if len(slide_parts) > policy.max_slides:
            raise InvalidPresentationError(
                f"PPTX has {len(slide_parts)} slides; limit is {policy.max_slides}."
            )
        for slide_index, slide_part in enumerate(slide_parts, start=1):
            root = parse_xml(read_xml_part(archive, slide_part, policy), part_name=slide_part)
            budget.check_slide(root)
            shape_tree = root.find("./p:cSld/p:spTree", NS)
            if shape_tree is None:
                raise InvalidPresentationError(f"Slide {slide_index} has no shape tree.")

            for shape, shape_path in walk_shapes(shape_tree):
                table = table_for_shape(shape)
                if table is not None:
                    _append_units(
                        units,
                        _table_units(
                            table,
                            slide_part=slide_part,
                            slide_index=slide_index,
                            shape_path=shape_path,
                        ),
                        budget,
                    )
                    continue
                if shape.tag == P_GRAPHIC_FRAME:
                    budget.accept_diagnostic()
                    warnings.append(
                        Diagnostic(
                            code="unsupported_graphic_frame",
                            message="Non-table graphic-frame text is preserved but not translated.",
                            slide_index=slide_index,
                            shape_id_path=shape_path,
                        )
                    )
                    continue
                if shape.tag == P_CONTENT_PART:
                    budget.accept_diagnostic()
                    warnings.append(
                        Diagnostic(
                            code="unsupported_content_part",
                            message="External content-part text is preserved but not translated.",
                            slide_index=slide_index,
                            shape_id_path=shape_path,
                        )
                    )
                    continue
                _append_units(
                    units,
                    _shape_text_units(
                        shape,
                        slide_part=slide_part,
                        slide_index=slide_index,
                        shape_path=shape_path,
                    ),
                    budget,
                )

    if file_sha256(source) != initial_hash:
        raise SourceChangedError("The source PPTX changed while it was being inspected.")

    return DeckPlan(
        schema_version=PLAN_SCHEMA_VERSION,
        source_path=source,
        input_sha256=initial_hash,
        source_lang=source_lang.strip(),
        target_lang=target_lang.strip(),
        slide_parts=slide_parts,
        units=_attach_context(units),
        warnings=tuple(warnings),
    )
