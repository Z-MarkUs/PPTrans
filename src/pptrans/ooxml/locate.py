"""DrawingML traversal and stable paragraph resolution."""

from __future__ import annotations

import json
from collections.abc import Iterator
from hashlib import sha256

from lxml import etree

from pptrans.domain.errors import InvalidPresentationError, LocatorResolutionError
from pptrans.domain.models import ParagraphLocator, SpanKind, TextContainer, TextSpan

from .xml import (
    A_FLD,
    A_P,
    A_R,
    A_T,
    A_TC,
    A_TR,
    NS,
    P_GRAPHIC_FRAME,
    P_GRP_SP,
    SHAPE_TAGS,
)


def shape_id(shape: etree._Element) -> int | None:
    """Return a shape's non-visual ID without descending into child shapes."""

    for child in shape:
        if child.tag in SHAPE_TAGS:
            continue
        candidate = child.find(".//p:cNvPr", NS)
        raw_id = candidate.get("id") if candidate is not None else None
        if raw_id is not None:
            try:
                return int(raw_id)
            except ValueError:
                return None
    return None


def shape_children(parent: etree._Element) -> Iterator[etree._Element]:
    """Yield direct shapes from a slide shape tree or group."""

    for child in parent:
        if child.tag in SHAPE_TAGS:
            yield child


def walk_shapes(
    parent: etree._Element, parent_path: tuple[int, ...] = ()
) -> Iterator[tuple[etree._Element, tuple[int, ...]]]:
    """Walk direct and nested shapes in deterministic document order."""

    sibling_ids: set[int] = set()
    for shape in shape_children(parent):
        identifier = shape_id(shape)
        if identifier is None:
            raise InvalidPresentationError("A slide shape has no valid non-visual shape ID.")
        if identifier in sibling_ids:
            raise InvalidPresentationError(
                f"Sibling shapes repeat non-visual shape ID {identifier}."
            )
        sibling_ids.add(identifier)
        path = (*parent_path, identifier)
        yield shape, path
        if shape.tag == P_GRP_SP:
            yield from walk_shapes(shape, path)


def resolve_shape(root: etree._Element, path: tuple[int, ...]) -> etree._Element:
    """Resolve a shape by its nested sequence of ``cNvPr`` IDs."""

    if not path:
        raise LocatorResolutionError("Shape locator has an empty shape-ID path.")
    parent = root.find("./p:cSld/p:spTree", NS)
    if parent is None:
        raise LocatorResolutionError("Slide has no p:spTree.")

    current: etree._Element | None = None
    for depth, identifier in enumerate(path):
        current = next(
            (
                candidate
                for candidate in shape_children(parent)
                if shape_id(candidate) == identifier
            ),
            None,
        )
        if current is None:
            raise LocatorResolutionError(
                f"Could not resolve shape ID {identifier} at depth {depth}."
            )
        parent = current
    if current is None:  # Defensive narrowing; an empty path is rejected above.
        raise LocatorResolutionError("Shape locator did not resolve to a shape.")
    return current


def table_for_shape(shape: etree._Element) -> etree._Element | None:
    """Return the DrawingML table owned by a graphic frame, if any."""

    if shape.tag != P_GRAPHIC_FRAME:
        return None
    return shape.find("./a:graphic/a:graphicData/a:tbl", NS)


def text_body_for_locator(root: etree._Element, locator: ParagraphLocator) -> etree._Element:
    """Resolve a locator to its owning ``txBody``."""

    shape = resolve_shape(root, locator.shape_id_path)
    if locator.container is TextContainer.SHAPE:
        body = shape.find("./p:txBody", NS)
        if body is None:
            raise LocatorResolutionError("Located shape no longer has a text body.")
        return body

    if locator.cell is None:
        raise LocatorResolutionError("Table-cell locator is missing row and column indices.")
    table = table_for_shape(shape)
    if table is None:
        raise LocatorResolutionError("Located shape no longer contains a table.")
    rows = table.findall(f"./{A_TR}")
    row_index, column_index = locator.cell
    if row_index < 0 or row_index >= len(rows):
        raise LocatorResolutionError(f"Table row {row_index} does not exist.")
    cells = rows[row_index].findall(f"./{A_TC}")
    if column_index < 0 or column_index >= len(cells):
        raise LocatorResolutionError(f"Table cell ({row_index}, {column_index}) does not exist.")
    body = cells[column_index].find(f"./{{{NS['a']}}}txBody")
    if body is None:
        raise LocatorResolutionError("Located table cell no longer has a text body.")
    return body


def paragraph_for_locator(root: etree._Element, locator: ParagraphLocator) -> etree._Element:
    """Resolve a locator to its exact paragraph."""

    body = text_body_for_locator(root, locator)
    paragraphs = body.findall(f"./{A_P}")
    index = locator.paragraph_index
    if index < 0 or index >= len(paragraphs):
        raise LocatorResolutionError(f"Paragraph {index} does not exist at the planned locator.")
    return paragraphs[index]


def paragraph_text_nodes(
    paragraph: etree._Element,
) -> tuple[tuple[SpanKind, etree._Element], ...]:
    """Return existing text nodes in visual paragraph order."""

    nodes: list[tuple[SpanKind, etree._Element]] = []
    for child in paragraph:
        if child.tag == A_R:
            nodes.extend((SpanKind.TEXT, node) for node in child.findall(f"./{A_T}"))
        elif child.tag == A_FLD:
            nodes.extend((SpanKind.FIELD, node) for node in child.findall(f"./{A_T}"))
    return tuple(nodes)


def extract_spans(paragraph: etree._Element) -> tuple[TextSpan, ...]:
    """Build stable span metadata from an unchanged paragraph."""

    spans: list[TextSpan] = []
    for index, (kind, node) in enumerate(paragraph_text_nodes(paragraph)):
        source = node.text or ""
        spans.append(
            TextSpan(
                id=f"s{index}",
                node_index=index,
                kind=kind,
                source=source,
                translatable=kind is SpanKind.TEXT and bool(source.strip()),
            )
        )
    return tuple(spans)


def source_digest(locator: ParagraphLocator, spans: tuple[TextSpan, ...]) -> str:
    """Hash source content and its structural address for optimistic locking."""

    payload = {
        "locator": {
            "slide_part": locator.slide_part,
            "slide_index": locator.slide_index,
            "shape_id_path": list(locator.shape_id_path),
            "container": locator.container.value,
            "cell": list(locator.cell) if locator.cell is not None else None,
            "paragraph_index": locator.paragraph_index,
        },
        "spans": [
            {
                "id": span.id,
                "node_index": span.node_index,
                "kind": span.kind.value,
                "source": span.source,
                "translatable": span.translatable,
            }
            for span in spans
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()
