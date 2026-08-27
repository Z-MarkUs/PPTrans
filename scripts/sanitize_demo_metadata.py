"""Normalize metadata on the synthetic PPTrans demo deck.

The visual authoring tool deliberately stays outside the runtime dependency set. This
post-processing step uses PPTrans's own defensive package writer so the committed demo
has project-specific, deterministic document properties.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from lxml import etree

from pptrans.ooxml.package import discover_slide_parts, open_package, rewrite_package
from pptrans.ooxml.xml import parse_xml, serialize_xml

CORE_PART = "docProps/core.xml"
APP_PART = "docProps/app.xml"
CORE = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC = "http://purl.org/dc/elements/1.1/"
DCTERMS = "http://purl.org/dc/terms/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
APP = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
FIXED_TIMESTAMP = "2026-08-28T00:00:00Z"
EXPECTED_DEMO_SLIDES = 3


def _set_text(root: etree._Element, name: str, value: str) -> etree._Element:
    node = root.find(name)
    if node is None:
        node = etree.SubElement(root, name)
    node.text = value
    return node


def normalized_metadata(source: Path) -> dict[str, bytes]:
    """Return deterministic core/app property replacements for the three-slide demo."""

    with open_package(source) as archive:
        if len(discover_slide_parts(archive)) != EXPECTED_DEMO_SLIDES:
            raise ValueError("The public demo generator must produce exactly three slides.")
        core = parse_xml(archive.read(CORE_PART), part_name=CORE_PART)
        app = parse_xml(archive.read(APP_PART), part_name=APP_PART)

    _set_text(core, f"{{{DC}}}creator", "Hehan Zhao")
    _set_text(core, f"{{{CORE}}}lastModifiedBy", "Hehan Zhao")
    _set_text(core, f"{{{DC}}}title", "PPTrans v2 - verifiable OOXML translation demo")
    _set_text(
        core,
        f"{{{DC}}}subject",
        "Synthetic fixture for PPTrans inspection, patching, and verification",
    )
    _set_text(
        core,
        f"{{{CORE}}}keywords",
        "PPTrans, PowerPoint, OOXML, translation, synthetic demo",
    )
    _set_text(
        core,
        f"{{{DC}}}description",
        "Author-owned synthetic content; contains no customer or private presentation data.",
    )
    for field in ("created", "modified"):
        timestamp = _set_text(core, f"{{{DCTERMS}}}{field}", FIXED_TIMESTAMP)
        timestamp.set(f"{{{XSI}}}type", "dcterms:W3CDTF")

    _set_text(app, f"{{{APP}}}Application", "PPTrans demo generator")
    _set_text(app, f"{{{APP}}}PresentationFormat", "Widescreen")
    _set_text(app, f"{{{APP}}}Slides", "3")
    return {CORE_PART: serialize_xml(core), APP_PART: serialize_xml(app)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Raw synthetic demo PPTX")
    parser.add_argument("destination", type=Path, help="Distinct normalized PPTX output")
    args = parser.parse_args()
    rewrite_package(args.source, args.destination, normalized_metadata(args.source))


if __name__ == "__main__":
    main()
