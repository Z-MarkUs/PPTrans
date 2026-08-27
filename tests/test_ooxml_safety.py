from __future__ import annotations

import zipfile
from hashlib import sha256
from pathlib import Path

import pytest
from test_ooxml_helpers import create_complex_deck, translated_values

from pptrans.domain import InvalidPresentationError, PackageLimits, VerificationError
from pptrans.ooxml import apply_patch_set, build_patch_set, inspect_deck, verify_output
from pptrans.ooxml.package import open_package, read_xml_part, rewrite_package
from pptrans.ooxml.xml import A_T, parse_xml, serialize_xml


def test_rejects_legacy_ppt_extension(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.ppt"
    legacy.write_bytes(b"not a pptx")
    with pytest.raises(InvalidPresentationError, match=r"Only \.pptx"):
        inspect_deck(legacy, source_lang="en", target_lang="fr")


def test_rejects_duplicate_package_members(tmp_path: Path) -> None:
    source = tmp_path / "complex.pptx"
    create_complex_deck(source)
    with (
        pytest.warns(UserWarning, match="Duplicate name"),
        zipfile.ZipFile(source, mode="a") as archive,
    ):
        archive.writestr("[Content_Types].xml", b"duplicate")

    with (
        pytest.raises(InvalidPresentationError, match="Duplicate package member"),
        open_package(source),
    ):
        pass


def test_rejects_parent_traversal_package_member(tmp_path: Path) -> None:
    source = tmp_path / "complex.pptx"
    create_complex_deck(source)
    with zipfile.ZipFile(source, mode="a") as archive:
        archive.writestr("../outside.xml", b"unsafe")

    with (
        pytest.raises(InvalidPresentationError, match="Unsafe package member path"),
        open_package(source),
    ):
        pass


def test_inspection_reads_every_member_and_rejects_corrupt_opaque_payload(
    tmp_path: Path,
) -> None:
    source = tmp_path / "corrupt-opaque.pptx"
    create_complex_deck(source)
    marker = b"PPTRANS-OPAQUE-CRC-SENTINEL"
    with zipfile.ZipFile(source, mode="a") as archive:
        archive.writestr(
            "ppt/media/opaque-test.bin",
            marker,
            compress_type=zipfile.ZIP_STORED,
        )
    payload = bytearray(source.read_bytes())
    marker_offset = payload.index(marker)
    payload[marker_offset] ^= 0x01
    source.write_bytes(payload)

    with pytest.raises(InvalidPresentationError, match=r"integrity|CRC"):
        inspect_deck(source, source_lang="en", target_lang="fr")


def test_rejects_a_real_high_compression_ratio_member(tmp_path: Path) -> None:
    source = tmp_path / "high-compression-ratio.pptx"
    member_name = "ppt/media/high-compression-ratio.bin"
    create_complex_deck(source)
    with zipfile.ZipFile(source, mode="a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member_name, b"0" * 1_000_000)

    with zipfile.ZipFile(source) as archive:
        info = archive.getinfo(member_name)
    assert info.compress_size > 0
    assert info.file_size / info.compress_size > PackageLimits().max_compression_ratio

    with (
        pytest.raises(InvalidPresentationError, match="compression-ratio limit"),
        open_package(source),
    ):
        pass


def test_xml_read_ceiling_does_not_depend_on_a_filename_suffix(tmp_path: Path) -> None:
    source = tmp_path / "complex.pptx"
    create_complex_deck(source)
    with zipfile.ZipFile(source) as archive:
        payloads = {info.filename: archive.read(info) for info in archive.infolist()}

    disguised = tmp_path / "disguised-slide.pptx"
    slide_name = "ppt/slides/slide1.xml"
    disguised_name = "ppt/slides/slide1.bin"
    relationships_name = "ppt/_rels/presentation.xml.rels"
    payloads[relationships_name] = payloads[relationships_name].replace(
        b"slides/slide1.xml", b"slides/slide1.bin"
    )
    filler = b"".join(sha256(str(index).encode()).hexdigest().encode() for index in range(4096))
    payloads[disguised_name] = payloads.pop(slide_name) + b"<!--" + filler + b"-->"
    with zipfile.ZipFile(disguised, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in payloads.items():
            archive.writestr(name, payload)

    other_xml_size = max(
        len(payload)
        for name, payload in payloads.items()
        if name != disguised_name and name.lower().endswith((".xml", ".rels"))
    )
    policy = PackageLimits(max_xml_bytes=other_xml_size)
    with (
        open_package(disguised, policy) as archive,
        pytest.raises(InvalidPresentationError, match="XML safety limit"),
    ):
        read_xml_part(archive, disguised_name, policy)
    with pytest.raises(InvalidPresentationError, match="XML safety limit"):
        inspect_deck(disguised, source_lang="en", target_lang="fr", limits=policy)


def test_verifier_rejects_unrelated_part_change(tmp_path: Path) -> None:
    source = tmp_path / "complex.pptx"
    staged = tmp_path / "staged.pptx"
    tampered = tmp_path / "tampered.pptx"
    create_complex_deck(source)
    plan = inspect_deck(source, source_lang="en", target_lang="fr")
    patches = build_patch_set(plan, translated_values(plan))
    apply_patch_set(source, staged, patches)

    with zipfile.ZipFile(staged) as archive:
        core = archive.read("docProps/core.xml")
    rewrite_package(staged, tampered, {"docProps/core.xml": core + b" "})

    with pytest.raises(VerificationError, match="Unrelated package part changed"):
        verify_output(source, tampered, patches)


def test_partial_patch_is_explicit_and_verified(tmp_path: Path) -> None:
    source = tmp_path / "complex.pptx"
    output = tmp_path / "partial.pptx"
    create_complex_deck(source)
    plan = inspect_deck(source, source_lang="en", target_lang="fr")
    first = plan.units[0]
    translations = {
        first.id: {span.id: f"ONLY<{span.source}>" for span in first.spans if span.translatable}
    }
    patches = build_patch_set(plan, translations, require_complete=False)
    apply_patch_set(source, output, patches)
    report = verify_output(source, output, patches)

    assert report.verified_patches == 1
    assert set(report.changed_parts) == {first.locator.slide_part}


def test_verifier_rejects_unplanned_text_change_inside_target_slide(tmp_path: Path) -> None:
    source = tmp_path / "complex.pptx"
    staged = tmp_path / "staged.pptx"
    tampered = tmp_path / "tampered.pptx"
    create_complex_deck(source)
    plan = inspect_deck(source, source_lang="en", target_lang="fr")
    patches = build_patch_set(plan, translated_values(plan))
    apply_patch_set(source, staged, patches)

    slide_part = plan.slide_parts[0]
    with zipfile.ZipFile(staged) as archive:
        slide_data = archive.read(slide_part)
    root = parse_xml(slide_data, part_name=slide_part)
    protected_field = next(node for node in root.iter(A_T) if node.text == "2026-08-28")
    protected_field.text = "tampered field"
    rewrite_package(staged, tampered, {slide_part: serialize_xml(root)})

    with pytest.raises(VerificationError, match=r"Unexpected text|Unplanned text node changed"):
        verify_output(source, tampered, patches)
