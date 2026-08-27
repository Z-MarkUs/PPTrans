"""Shared text predicates for XML-backed domain values."""

from __future__ import annotations

import re

_INVALID_XML_CHARACTER = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def is_xml_10_text(text: str) -> bool:
    """Return whether *text* contains only characters permitted by XML 1.0."""

    return _INVALID_XML_CHARACTER.search(text) is None


__all__ = ["is_xml_10_text"]
