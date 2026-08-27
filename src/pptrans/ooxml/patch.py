"""Source-guarded, text-node-only PPTX patching."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

from lxml import etree

from pptrans.domain.errors import (
    PatchValidationError,
    SourceChangedError,
    VerificationError,
)
from pptrans.domain.models import (
    DeckPlan,
    PackageLimits,
    PatchSet,
    TranslatedSpan,
    TranslationInput,
    TranslationPatch,
)

from .inspect import PLAN_SCHEMA_VERSION
from .locate import (
    extract_spans,
    paragraph_for_locator,
    paragraph_text_nodes,
    source_digest,
)
from .package import (
    ensure_distinct_package_paths,
    ensure_package_destination_available,
    file_sha256,
    open_package,
    read_xml_part,
    rewrite_package,
)
from .xml import assign_text, parse_xml, serialize_xml, structural_fingerprint, validate_text

PATCH_SCHEMA_VERSION = "pptrans.patch-set/v2"


def _normalize_translations(
    value: Mapping[str, str] | Sequence[TranslatedSpan],
) -> dict[str, str]:
    if isinstance(value, Mapping):
        normalized = dict(value)
    else:
        normalized = {}
        for item in value:
            if not isinstance(item, TranslatedSpan):
                raise PatchValidationError(
                    "Translation sequences must contain TranslatedSpan values."
                )
            if item.span_id in normalized:
                raise PatchValidationError(f"Duplicate translated span ID: {item.span_id!r}")
            normalized[item.span_id] = item.text
    for span_id, text in normalized.items():
        if not isinstance(span_id, str) or not isinstance(text, str):
            raise PatchValidationError("Translated span IDs and text must both be strings.")
        validate_text(text)
    return normalized


def build_patch_set(
    plan: DeckPlan,
    translations: TranslationInput,
    *,
    require_complete: bool = True,
) -> PatchSet:
    """Validate provider output against a plan and build immutable patches."""

    if plan.schema_version != PLAN_SCHEMA_VERSION:
        raise PatchValidationError(f"Unsupported plan schema: {plan.schema_version!r}")
    units = plan.unit_map()
    unknown = set(translations).difference(units)
    if unknown:
        raise PatchValidationError("Unknown translation unit IDs: " + ", ".join(sorted(unknown)))
    if require_complete:
        missing = set(units).difference(translations)
        if missing:
            raise PatchValidationError(
                "Missing translation unit IDs: " + ", ".join(sorted(missing))
            )

    patches: list[TranslationPatch] = []
    for unit in plan.units:
        if unit.id not in translations:
            continue
        translated = _normalize_translations(translations[unit.id])
        expected = unit.translatable_span_ids
        if set(translated) != set(expected):
            missing_spans = set(expected).difference(translated)
            extra_spans = set(translated).difference(expected)
            details: list[str] = []
            if missing_spans:
                details.append("missing " + ", ".join(sorted(missing_spans)))
            if extra_spans:
                details.append("unexpected " + ", ".join(sorted(extra_spans)))
            raise PatchValidationError(f"Unit {unit.id} has invalid spans ({'; '.join(details)}).")
        patches.append(
            TranslationPatch(
                unit_id=unit.id,
                locator=unit.locator,
                source_digest=unit.source_digest,
                source_spans=unit.spans,
                translations=tuple(
                    TranslatedSpan(span_id=span_id, text=translated[span_id])
                    for span_id in expected
                ),
            )
        )
    return PatchSet(
        schema_version=PATCH_SCHEMA_VERSION,
        input_sha256=plan.input_sha256,
        patches=tuple(patches),
    )


def _validate_patch_shape(patch: TranslationPatch) -> dict[str, str]:
    expected = tuple(span.id for span in patch.source_spans if span.translatable)
    actual = tuple(item.span_id for item in patch.translations)
    if actual != expected:
        raise PatchValidationError(
            f"Patch {patch.unit_id} span order does not exactly match its source plan."
        )
    mapping: dict[str, str] = {}
    for item in patch.translations:
        if item.span_id in mapping:
            raise PatchValidationError(f"Patch {patch.unit_id} repeats span {item.span_id!r}.")
        validate_text(item.text)
        mapping[item.span_id] = item.text
    return mapping


def _apply_translation_patch(root: etree._Element, patch: TranslationPatch) -> bool:
    translations = _validate_patch_shape(patch)
    paragraph = paragraph_for_locator(root, patch.locator)
    actual_spans = extract_spans(paragraph)
    if actual_spans != patch.source_spans:
        raise SourceChangedError(f"Source text changed at translation unit {patch.unit_id}.")
    if source_digest(patch.locator, actual_spans) != patch.source_digest:
        raise SourceChangedError(f"Source structure changed at translation unit {patch.unit_id}.")
    nodes = paragraph_text_nodes(paragraph)
    if len(nodes) != len(patch.source_spans):
        raise SourceChangedError(f"Text-node count changed at translation unit {patch.unit_id}.")
    changed = False
    for span in patch.source_spans:
        if span.translatable:
            node = nodes[span.node_index][1]
            translated = translations[span.id]
            if (node.text or "") != translated:
                assign_text(node, translated)
                changed = True
    return changed


def _patch_part(part_name: str, original: bytes, patches: list[TranslationPatch]) -> bytes:
    root = parse_xml(original, part_name=part_name)
    changed_any = False
    for patch in patches:
        changed_any = _apply_translation_patch(root, patch) or changed_any
    if not changed_any:
        return original
    changed = serialize_xml(root, original=original)
    before = structural_fingerprint(original, part_name=part_name)
    after = structural_fingerprint(changed, part_name=part_name)
    if before != after:
        raise VerificationError(f"Text patch unexpectedly changed the structure of {part_name!r}.")
    return changed


def _group_patches(patch_set: PatchSet) -> dict[str, list[TranslationPatch]]:
    by_part: dict[str, list[TranslationPatch]] = defaultdict(list)
    seen_locators = set()
    for patch in patch_set.patches:
        if patch.locator in seen_locators:
            raise PatchValidationError(
                f"Multiple patches target the same paragraph: {patch.locator}"
            )
        seen_locators.add(patch.locator)
        by_part[patch.locator.slide_part].append(patch)
    return by_part


def apply_patch_set(
    source: Path,
    destination: Path,
    patch_set: PatchSet,
    *,
    limits: PackageLimits | None = None,
    overwrite: bool = False,
) -> None:
    """Apply patches without replacing an existing destination by default."""

    source = Path(source)
    destination = Path(destination)
    ensure_distinct_package_paths(source, destination)
    ensure_package_destination_available(destination, overwrite=overwrite)
    if patch_set.schema_version != PATCH_SCHEMA_VERSION:
        raise PatchValidationError(f"Unsupported patch schema: {patch_set.schema_version!r}")
    current_hash = file_sha256(source)
    if current_hash != patch_set.input_sha256:
        raise SourceChangedError("The source PPTX changed after its translation plan was created.")

    by_part = _group_patches(patch_set)
    policy = limits or PackageLimits()

    replacements: dict[str, bytes] = {}
    with open_package(source, policy) as archive:
        for part_name, patches in by_part.items():
            if part_name not in archive.namelist():
                raise PatchValidationError(f"Patch targets a missing slide part: {part_name!r}")
            original = read_xml_part(archive, part_name, policy)
            replacements[part_name] = _patch_part(part_name, original, patches)

    rewrite_package(
        source,
        destination,
        replacements,
        limits=policy,
        overwrite=overwrite,
    )
