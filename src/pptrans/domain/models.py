"""Immutable data exchanged by the PPTrans v2 translation core."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

MAX_TRANSLATABLE_SPANS_PER_UNIT = 10_000
MAX_TRANSLATED_TEXT_CHARACTERS = 100_000


class TextContainer(str, Enum):
    """OOXML container holding a translated paragraph."""

    SHAPE = "shape"
    TABLE_CELL = "table_cell"


class SpanKind(str, Enum):
    """Supported DrawingML text-node kinds."""

    TEXT = "text"
    FIELD = "field"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A non-fatal condition found while inspecting a deck."""

    code: str
    message: str
    slide_index: int | None = None
    shape_id_path: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class ParagraphLocator:
    """Stable address of a paragraph in an unchanged PPTX package.

    Shape IDs come from ``p:cNvPr/@id`` and remain stable when shapes are
    reordered.  ``slide_index`` is user-facing metadata; ``slide_part`` is the
    package address used during resolution.
    """

    slide_part: str
    slide_index: int
    shape_id_path: tuple[int, ...]
    container: TextContainer
    paragraph_index: int
    cell: tuple[int, int] | None = None


@dataclass(frozen=True, slots=True)
class TextSpan:
    """One existing ``a:t`` node inside a paragraph."""

    id: str
    node_index: int
    kind: SpanKind
    source: str
    translatable: bool


@dataclass(frozen=True, slots=True)
class TranslationUnit:
    """A paragraph translated as one semantic unit."""

    id: str
    locator: ParagraphLocator
    spans: tuple[TextSpan, ...]
    source_digest: str
    context_before: str | None = None
    context_after: str | None = None

    @property
    def source_text(self) -> str:
        """Return readable source text without changing its span boundaries."""

        return "".join(span.source for span in self.spans)

    @property
    def translatable_span_ids(self) -> tuple[str, ...]:
        """Return the exact span IDs a translation result must contain."""

        return tuple(span.id for span in self.spans if span.translatable)


@dataclass(frozen=True, slots=True)
class DeckPlan:
    """Immutable inspection result used to translate and patch one deck."""

    schema_version: str
    source_path: Path
    input_sha256: str
    source_lang: str
    target_lang: str
    slide_parts: tuple[str, ...]
    units: tuple[TranslationUnit, ...]
    warnings: tuple[Diagnostic, ...] = ()

    def unit_map(self) -> dict[str, TranslationUnit]:
        """Return units keyed by their deterministic IDs."""

        return {unit.id: unit for unit in self.units}


@dataclass(frozen=True, slots=True)
class TranslatedSpan:
    """Validated target text for one source span."""

    span_id: str
    text: str


@dataclass(frozen=True, slots=True)
class TranslationPatch:
    """Source-guarded replacements for one paragraph."""

    unit_id: str
    locator: ParagraphLocator
    source_digest: str
    source_spans: tuple[TextSpan, ...]
    translations: tuple[TranslatedSpan, ...]


@dataclass(frozen=True, slots=True)
class PatchSet:
    """All validated patches for a single source package."""

    schema_version: str
    input_sha256: str
    patches: tuple[TranslationPatch, ...]

    @property
    def target_parts(self) -> frozenset[str]:
        """Return slide parts expected to change."""

        return frozenset(patch.locator.slide_part for patch in self.patches)


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """Evidence that a translated package preserved its source structure."""

    source_sha256: str
    output_sha256: str
    changed_parts: tuple[str, ...]
    verified_patches: int
    verified_spans: int


@dataclass(frozen=True, slots=True)
class DeckResult:
    """Result of an atomic deck-patching transaction."""

    output_path: Path
    report: VerificationReport


TranslationInput = Mapping[str, Mapping[str, str] | Sequence[TranslatedSpan]]


@dataclass(frozen=True, slots=True)
class PackageLimits:
    """Defensive bounds for untrusted ZIP-based office packages."""

    max_members: int = 20_000
    max_member_bytes: int = 256 * 1024 * 1024
    max_xml_bytes: int = 32 * 1024 * 1024
    max_total_bytes: int = 1024 * 1024 * 1024
    max_compression_ratio: int = 500
    max_slides: int = 500
    max_xml_elements_per_part: int = 250_000
    max_translation_units: int = 10_000
    max_text_spans: int = 50_000
    max_source_characters: int = 5_000_000
    max_translatable_spans_per_unit: int = MAX_TRANSLATABLE_SPANS_PER_UNIT
    max_source_characters_per_span: int = MAX_TRANSLATED_TEXT_CHARACTERS
    max_diagnostics: int = 10_000
    required_members: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "[Content_Types].xml",
                "ppt/presentation.xml",
                "ppt/_rels/presentation.xml.rels",
            }
        )
    )
