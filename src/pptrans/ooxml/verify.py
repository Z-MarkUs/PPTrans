"""Post-write verification for formatting-safe PPTX translation."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from lxml import etree

from pptrans.domain.errors import PatchValidationError, SourceChangedError, VerificationError
from pptrans.domain.models import (
    PackageLimits,
    PatchSet,
    TranslationPatch,
    VerificationReport,
)

from .locate import extract_spans, paragraph_for_locator, paragraph_text_nodes, source_digest
from .package import file_sha256, open_package, read_xml_part
from .patch import validate_patch_set
from .xml import A_T, XML_SPACE, parse_xml, structural_fingerprint


def _verify_patch(
    source_root: etree._Element,
    output_root: etree._Element,
    patch: TranslationPatch,
    source_node_indices: dict[etree._Element, int],
) -> tuple[set[int], int]:
    source_paragraph = paragraph_for_locator(source_root, patch.locator)
    output_paragraph = paragraph_for_locator(output_root, patch.locator)
    actual_source_spans = extract_spans(source_paragraph)
    if actual_source_spans != patch.source_spans:
        raise VerificationError(f"Patch source does not match translation unit {patch.unit_id}.")
    if source_digest(patch.locator, actual_source_spans) != patch.source_digest:
        raise VerificationError(
            f"Patch source digest does not match translation unit {patch.unit_id}."
        )

    source_nodes = paragraph_text_nodes(source_paragraph)
    output_nodes = paragraph_text_nodes(output_paragraph)
    if len(output_nodes) != len(patch.source_spans):
        raise VerificationError(f"Text-node count changed at translation unit {patch.unit_id}.")

    translations = {item.span_id: item.text for item in patch.translations}
    allowed: set[int] = set()
    verified_spans = 0
    for span in patch.source_spans:
        source_kind, source_node = source_nodes[span.node_index]
        actual_kind, output_node = output_nodes[span.node_index]
        if source_kind is not span.kind or actual_kind is not span.kind:
            raise VerificationError(f"Text-node kind changed at translation unit {patch.unit_id}.")
        expected = translations.get(span.id, span.source)
        if (output_node.text or "") != expected:
            raise VerificationError(f"Unexpected text at unit {patch.unit_id}, span {span.id}.")
        if span.translatable:
            allowed.add(source_node_indices[source_node])
            verified_spans += 1
    return allowed, verified_spans


def _verify_unchanged_text_nodes(
    part_name: str,
    source_nodes: Sequence[etree._Element],
    output_nodes: Sequence[etree._Element],
    allowed_indices: set[int],
) -> None:
    for index, (source_node, output_node) in enumerate(
        zip(source_nodes, output_nodes, strict=True)
    ):
        if index in allowed_indices:
            continue
        if (source_node.text or "") != (output_node.text or ""):
            raise VerificationError(
                f"Unplanned text node changed in {part_name!r} at index {index}."
            )
        if source_node.get(XML_SPACE) != output_node.get(XML_SPACE):
            raise VerificationError(
                f"Unplanned whitespace semantics changed in {part_name!r} at index {index}."
            )


def _verify_target_part(
    part_name: str,
    source_data: bytes,
    output_data: bytes,
    patches: Sequence[TranslationPatch],
) -> int:
    source_structure = structural_fingerprint(source_data, part_name=part_name)
    output_structure = structural_fingerprint(output_data, part_name=part_name)
    if source_structure != output_structure:
        raise VerificationError(f"Formatting structure changed in {part_name!r}.")

    source_root = parse_xml(source_data, part_name=part_name)
    output_root = parse_xml(output_data, part_name=part_name)
    source_nodes = list(source_root.iter(A_T))
    output_nodes = list(output_root.iter(A_T))
    if len(source_nodes) != len(output_nodes):
        raise VerificationError(f"Text-node count changed in {part_name!r}.")

    source_node_indices = {node: index for index, node in enumerate(source_nodes)}
    allowed_indices: set[int] = set()
    verified_spans = 0
    for patch in patches:
        allowed, patch_span_count = _verify_patch(
            source_root, output_root, patch, source_node_indices
        )
        allowed_indices.update(allowed)
        verified_spans += patch_span_count
    _verify_unchanged_text_nodes(part_name, source_nodes, output_nodes, allowed_indices)
    return verified_spans


def verify_output(
    source: Path,
    output: Path,
    patch_set: PatchSet,
    *,
    limits: PackageLimits | None = None,
) -> VerificationReport:
    """Prove that output differs only in allowed DrawingML text values."""

    source = Path(source)
    output = Path(output)
    source_hash = file_sha256(source)
    if source_hash != patch_set.input_sha256:
        raise SourceChangedError("The source PPTX changed before output verification.")

    patches_by_part = validate_patch_set(patch_set)

    changed_parts: list[str] = []
    verified_patches = 0
    verified_spans = 0
    policy = limits or PackageLimits()
    with open_package(source, policy) as source_zip, open_package(output, policy) as output_zip:
        source_names = tuple(source_zip.namelist())
        output_names = tuple(output_zip.namelist())
        if source_names != output_names:
            raise VerificationError("Output package member names or ordering changed.")
        missing_parts = set(patches_by_part).difference(source_names)
        if missing_parts:
            raise PatchValidationError(
                "Patch targets a missing slide part: " + ", ".join(sorted(missing_parts))
            )
        if source_zip.testzip() is not None or output_zip.testzip() is not None:
            raise VerificationError("Source or output PPTX failed its ZIP CRC check.")

        for part_name in source_names:
            patches = patches_by_part.get(part_name)
            if patches:
                source_data = read_xml_part(source_zip, part_name, policy)
                output_data = read_xml_part(output_zip, part_name, policy)
            else:
                source_data = source_zip.read(part_name)
                output_data = output_zip.read(part_name)
            if source_data != output_data:
                changed_parts.append(part_name)
            if not patches:
                if source_data != output_data:
                    raise VerificationError(f"Unrelated package part changed: {part_name!r}")
                continue
            verified_spans += _verify_target_part(part_name, source_data, output_data, patches)
            verified_patches += len(patches)

    unexpected = set(changed_parts).difference(patch_set.target_parts)
    if unexpected:
        raise VerificationError("Unexpected changed parts: " + ", ".join(sorted(unexpected)))
    if verified_patches != len(patch_set.patches):
        raise VerificationError("Not every supplied patch was verified.")
    return VerificationReport(
        source_sha256=source_hash,
        output_sha256=file_sha256(output),
        changed_parts=tuple(changed_parts),
        verified_patches=verified_patches,
        verified_spans=verified_spans,
    )
