"""Small, security-conscious XML helpers for DrawingML parts."""

from __future__ import annotations

import codecs
import re
from hashlib import sha256

from lxml import etree

from pptrans.domain.errors import InvalidPresentationError, PatchValidationError
from pptrans.domain.text import is_xml_10_text

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
XML_NS = "http://www.w3.org/XML/1998/namespace"

NS = {"a": A_NS, "p": P_NS, "r": R_NS, "rel": REL_NS}

A_T = f"{{{A_NS}}}t"
A_R = f"{{{A_NS}}}r"
A_FLD = f"{{{A_NS}}}fld"
A_P = f"{{{A_NS}}}p"
A_TBL = f"{{{A_NS}}}tbl"
A_TR = f"{{{A_NS}}}tr"
A_TC = f"{{{A_NS}}}tc"
P_SP = f"{{{P_NS}}}sp"
P_GRP_SP = f"{{{P_NS}}}grpSp"
P_GRAPHIC_FRAME = f"{{{P_NS}}}graphicFrame"
P_CXN_SP = f"{{{P_NS}}}cxnSp"
P_CONTENT_PART = f"{{{P_NS}}}contentPart"
XML_SPACE = f"{{{XML_NS}}}space"

SHAPE_TAGS = frozenset({P_SP, P_GRP_SP, P_GRAPHIC_FRAME, P_CXN_SP, P_CONTENT_PART})

_XML_DECLARATION = re.compile(r"^<\?xml\s+([^?]+)\?>", re.IGNORECASE)
_XML_DECLARATION_ATTRIBUTE = re.compile(
    r"([A-Za-z_:][\w:.-]*)\s*=\s*(['\"])(.*?)\2",
    re.DOTALL,
)
_BOMS = (
    (codecs.BOM_UTF32_LE, "UTF-32-LE", "utf-32-le"),
    (codecs.BOM_UTF32_BE, "UTF-32-BE", "utf-32-be"),
    (codecs.BOM_UTF8, "UTF-8", "utf-8"),
    (codecs.BOM_UTF16_LE, "UTF-16-LE", "utf-16-le"),
    (codecs.BOM_UTF16_BE, "UTF-16-BE", "utf-16-be"),
)


def parse_xml(data: bytes, *, part_name: str) -> etree._Element:
    """Parse an OOXML part without DTDs, entities, or network access."""

    if b"<!doctype" in data.lower():
        raise InvalidPresentationError(f"DTD content is not allowed in {part_name!r}.")
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        remove_blank_text=False,
        remove_comments=False,
        huge_tree=False,
    )
    try:
        root = etree.fromstring(data, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise InvalidPresentationError(f"Invalid XML in {part_name!r}: {exc}") from exc
    if getattr(root.getroottree().docinfo, "doctype", None) or any(
        isinstance(node, etree._Entity) for node in root.iter()
    ):
        raise InvalidPresentationError(f"DTD content is not allowed in {part_name!r}.")
    return root


def _declaration_profile(
    data: bytes,
    root: etree._Element,
) -> tuple[bool, str, str | None, str | None, str | None, str | None]:
    """Return declaration semantics without trusting a byte-pattern-only encoding guess."""

    docinfo = root.getroottree().docinfo
    actual_encoding = (docinfo.encoding or "UTF-8").upper().replace("_", "-")
    try:
        document = data.decode(actual_encoding)
    except (LookupError, UnicodeDecodeError):
        document = data.decode(actual_encoding, errors="ignore")
    bom_name = next((name for marker, name, _codec in _BOMS if data.startswith(marker)), None)
    match = _XML_DECLARATION.match(document.lstrip("\ufeff"))
    if match is None:
        return False, actual_encoding, None, None, None, bom_name
    attributes = {
        name.lower(): value
        for name, _quote, value in _XML_DECLARATION_ATTRIBUTE.findall(match.group(1))
    }
    declared_encoding = attributes.get("encoding")
    if declared_encoding is not None:
        declared_encoding = declared_encoding.upper().replace("_", "-")
    standalone = attributes.get("standalone")
    if standalone is not None:
        standalone = standalone.lower()
    return (
        True,
        actual_encoding,
        attributes.get("version"),
        declared_encoding,
        standalone,
        bom_name,
    )


def _original_declaration(data: bytes, encoding: str) -> str | None:
    try:
        document = data.decode(encoding)
    except (LookupError, UnicodeDecodeError):
        document = data.decode(encoding, errors="ignore")
    match = _XML_DECLARATION.match(document.lstrip("\ufeff"))
    return match.group(0) if match is not None else None


def _encode_document(text: str, encoding: str, bom_name: str | None) -> bytes:
    for marker, name, codec in _BOMS:
        if name == bom_name:
            return marker + text.encode(codec)
    return text.encode(encoding)


def serialize_xml(root: etree._Element, *, original: bytes | None = None) -> bytes:
    """Serialize a complete XML document and preserve its declaration semantics."""

    tree = root.getroottree()
    if original is None:
        return etree.tostring(
            tree,
            encoding="UTF-8",
            xml_declaration=True,
            standalone=True,
        )
    has_declaration, encoding, _version, _declared_encoding, _standalone, bom_name = (
        _declaration_profile(original, root)
    )
    body = etree.tostring(tree, encoding=str, xml_declaration=False)
    declaration = _original_declaration(original, encoding) if has_declaration else None
    return _encode_document(f"{declaration or ''}{body}", encoding, bom_name)


def validate_text(text: str) -> None:
    """Reject characters forbidden by XML 1.0 before staging output."""

    if not is_xml_10_text(text):
        raise PatchValidationError("Translated text contains a character forbidden by XML 1.0.")


def requires_xml_space_preserve(text: str) -> bool:
    """Return whether DrawingML must preserve leading or trailing whitespace."""

    return text[:1].isspace() or text[-1:].isspace()


def assign_text(node: etree._Element, text: str) -> None:
    """Change one ``a:t`` value and add whitespace preservation when required."""

    validate_text(text)
    node.text = text
    if requires_xml_space_preserve(text):
        node.set(XML_SPACE, "preserve")


def structural_fingerprint(data: bytes, *, part_name: str) -> str:
    """Hash an XML part after masking the only fields PPTrans may change."""

    root = parse_xml(data, part_name=part_name)
    declaration = _declaration_profile(data, root)
    for node in root.iter(A_T):
        node.text = "__PPTRANS_TEXT__"
        if XML_SPACE in node.attrib:
            del node.attrib[XML_SPACE]
    canonical = etree.tostring(root.getroottree(), method="c14n", with_comments=True)
    fingerprint_input = repr(declaration).encode("ascii") + b"\0" + canonical
    return sha256(fingerprint_input).hexdigest()
