"""Strict, provider-neutral schemas for multimodal slide review.

The models in this module deliberately contain observations only.  Passing a
slide and choosing a repair are application decisions, not fields that an LLM
is allowed to control.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class StrictReviewModel(BaseModel):
    """Base model that rejects unrecognised provider output."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


ShapeId = Annotated[
    str,
    StringConstraints(
        min_length=9,
        max_length=128,
        pattern=r"^s[1-9][0-9]*:shape:[1-9][0-9]*(?::(?:shape:[1-9][0-9]*|cell:r[0-9]+c[0-9]+))*$",
    ),
]
IssueId = Annotated[
    str,
    StringConstraints(min_length=2, max_length=4, pattern=r"^i[0-9]{1,2}$"),
]
UnitFloat = Annotated[float, Field(strict=True, ge=0.0, le=1.0, allow_inf_nan=False)]
Score = Annotated[int, Field(strict=True, ge=0, le=100)]
MAX_REVIEW_SCORE = 100


class IssueCategory(str, Enum):
    TEXT_OVERFLOW = "text_overflow"
    TEXT_CLIPPING = "text_clipping"
    OVERLAP = "overlap"
    OUT_OF_BOUNDS = "out_of_bounds"
    FONT_TOO_SMALL = "font_too_small"
    ALIGNMENT_SHIFT = "alignment_shift"
    CONTRAST = "contrast"
    MISSING_CONTENT = "missing_content"
    UNTRANSLATED_CONTENT = "untranslated_content"
    RENDER_PROBLEM = "render_problem"
    OTHER = "other"


class IssueSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RepairHint(str, Enum):
    ENABLE_WRAP = "enable_wrap"
    SHRINK_FONT = "shrink_font"
    REDUCE_MARGINS = "reduce_margins"
    TIGHTEN_SPACING = "tighten_spacing"
    EXPAND_BOX = "expand_box"
    RESTORE_GEOMETRY = "restore_geometry"
    MANUAL_REVIEW = "manual_review"
    NONE = "none"


class NormalizedBox(StrictReviewModel):
    """A slide-relative box whose edges must remain within the slide."""

    x: UnitFloat
    y: UnitFloat
    width: Annotated[float, Field(strict=True, gt=0.0, le=1.0, allow_inf_nan=False)]
    height: Annotated[float, Field(strict=True, gt=0.0, le=1.0, allow_inf_nan=False)]

    @model_validator(mode="after")
    def ensure_inside_slide(self) -> NormalizedBox:
        epsilon = 1e-9
        if self.x + self.width > 1.0 + epsilon:
            raise ValueError("box extends beyond the right edge of the slide")
        if self.y + self.height > 1.0 + epsilon:
            raise ValueError("box extends beyond the bottom edge of the slide")
        return self


class ReviewIssue(StrictReviewModel):
    issue_id: IssueId
    category: IssueCategory
    severity: IssueSeverity
    confidence: UnitFloat
    target_shape_id: ShapeId | None = None
    region: NormalizedBox | None = None
    evidence: Annotated[str, StringConstraints(min_length=1, max_length=240)]
    repair_hint: RepairHint


class SlideReviewPayload(StrictReviewModel):
    """The complete structured observation returned for one slide pair."""

    schema_version: Literal["1.0"] = "1.0"
    slide_number: Annotated[int, Field(strict=True, ge=1, le=100_000)]
    visual_fidelity: Score
    readability: Score
    content_visibility: Score
    issues: tuple[ReviewIssue, ...] = Field(default_factory=tuple, max_length=20)
    summary: Annotated[str, StringConstraints(min_length=1, max_length=300)]

    @model_validator(mode="after")
    def validate_issue_identity(self) -> SlideReviewPayload:
        issue_ids = [issue.issue_id for issue in self.issues]
        if len(issue_ids) != len(set(issue_ids)):
            raise ValueError("issue_id values must be unique within a slide review")

        expected_prefix = f"s{self.slide_number}:"
        mismatched = [
            issue.target_shape_id
            for issue in self.issues
            if issue.target_shape_id is not None
            and not issue.target_shape_id.startswith(expected_prefix)
        ]
        if mismatched:
            raise ValueError("target_shape_id must refer to the reviewed slide")
        return self


class ReviewDecision(StrictReviewModel):
    """Deterministic application decision derived from a review payload."""

    quality_score: Score
    passed: bool
    blocking_issue_ids: tuple[IssueId, ...] = ()
    reasons: tuple[str, ...] = ()


def derive_quality_score(payload: SlideReviewPayload) -> int:
    """Return the stable, half-up weighted score for a review payload."""

    weighted = (
        Decimal(payload.visual_fidelity) * Decimal("0.35")
        + Decimal(payload.readability) * Decimal("0.35")
        + Decimal(payload.content_visibility) * Decimal("0.30")
    )
    return int(weighted.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def evaluate_review(
    payload: SlideReviewPayload,
    *,
    threshold: int = 85,
    blocking_confidence: float = 0.65,
) -> ReviewDecision:
    """Apply a deterministic acceptance rule to provider observations."""

    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, int)
        or not 0 <= threshold <= MAX_REVIEW_SCORE
    ):
        raise ValueError("threshold must be an integer between 0 and 100")
    if (
        isinstance(blocking_confidence, bool)
        or not isinstance(blocking_confidence, (int, float))
        or not 0.0 <= float(blocking_confidence) <= 1.0
    ):
        raise ValueError("blocking_confidence must be between 0 and 1")

    score = derive_quality_score(payload)
    blocking = tuple(
        issue.issue_id
        for issue in payload.issues
        if issue.severity in {IssueSeverity.HIGH, IssueSeverity.CRITICAL}
        and issue.confidence >= float(blocking_confidence)
    )
    reasons: list[str] = []
    if score < threshold:
        reasons.append("score_below_threshold")
    if blocking:
        reasons.append("blocking_issues")
    return ReviewDecision(
        quality_score=score,
        passed=not reasons,
        blocking_issue_ids=blocking,
        reasons=tuple(reasons),
    )


__all__ = [
    "IssueCategory",
    "IssueSeverity",
    "NormalizedBox",
    "RepairHint",
    "ReviewDecision",
    "ReviewIssue",
    "ShapeId",
    "SlideReviewPayload",
    "derive_quality_score",
    "evaluate_review",
]
