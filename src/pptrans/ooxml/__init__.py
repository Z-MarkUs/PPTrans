"""Formatting-preserving OOXML inspection, patching, and verification."""

from .inspect import PLAN_SCHEMA_VERSION, inspect_deck
from .package import (
    discover_slide_parts,
    file_sha256,
    open_package,
    package_member_hashes,
    read_xml_part,
)
from .patch import PATCH_SCHEMA_VERSION, apply_patch_set, build_patch_set
from .verify import verify_output

__all__ = [
    "PATCH_SCHEMA_VERSION",
    "PLAN_SCHEMA_VERSION",
    "apply_patch_set",
    "build_patch_set",
    "discover_slide_parts",
    "file_sha256",
    "inspect_deck",
    "open_package",
    "package_member_hashes",
    "read_xml_part",
    "verify_output",
]
