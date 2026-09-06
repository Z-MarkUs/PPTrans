from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from pptrans.schemas.review import (
    SlideReviewPayload,
    derive_quality_score,
    evaluate_review,
)


def _payload(*, severity: str = "low", confidence: float = 0.9) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "slide_number": 3,
        "visual_fidelity": 90,
        "readability": 80,
        "content_visibility": 70,
        "issues": [
            {
                "issue_id": "i1",
                "category": "text_overflow",
                "severity": severity,
                "confidence": confidence,
                "target_shape_id": "s3:shape:17",
                "region": {"x": 0.1, "y": 0.1, "width": 0.4, "height": 0.3},
                "evidence": "The translated title extends outside its text box.",
                "repair_hint": "shrink_font",
            }
        ],
        "summary": "One translated title needs attention.",
    }


def test_review_score_and_pass_are_derived_locally() -> None:
    payload = SlideReviewPayload.model_validate(_payload())
    assert derive_quality_score(payload) == 81
    assert evaluate_review(payload, threshold=80).passed is True
    assert evaluate_review(payload, threshold=82).reasons == ("score_below_threshold",)


def test_high_confidence_severe_issue_blocks_high_score() -> None:
    raw = _payload(severity="critical", confidence=0.8)
    raw.update(visual_fidelity=100, readability=100, content_visibility=100)
    decision = evaluate_review(SlideReviewPayload.model_validate(raw), threshold=85)
    assert decision.quality_score == 100
    assert decision.passed is False
    assert decision.blocking_issue_ids == ("i1",)


def test_schema_rejects_extra_fields_and_malicious_code() -> None:
    raw = _payload()
    raw["code"] = "do something unsafe"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SlideReviewPayload.model_validate(raw)


def test_schema_rejects_duplicate_issue_ids() -> None:
    raw = _payload()
    raw["issues"] = [raw["issues"][0], raw["issues"][0]]  # type: ignore[index]
    with pytest.raises(ValidationError, match="issue_id values must be unique"):
        SlideReviewPayload.model_validate(raw)


def test_schema_rejects_target_on_another_slide() -> None:
    raw = _payload()
    raw["issues"][0]["target_shape_id"] = "s4:shape:17"  # type: ignore[index]
    with pytest.raises(ValidationError, match="must refer to the reviewed slide"):
        SlideReviewPayload.model_validate(raw)


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -0.1, 1.1])
def test_schema_rejects_invalid_confidence(invalid: float) -> None:
    with pytest.raises(ValidationError):
        SlideReviewPayload.model_validate(_payload(confidence=invalid))


def test_schema_rejects_box_outside_slide() -> None:
    raw = _payload()
    raw["issues"][0]["region"] = {  # type: ignore[index]
        "x": 0.8,
        "y": 0.1,
        "width": 0.3,
        "height": 0.3,
    }
    with pytest.raises(ValidationError, match="right edge"):
        SlideReviewPayload.model_validate(raw)


def test_schema_has_closed_objects() -> None:
    schema = SlideReviewPayload.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["ReviewIssue"]["additionalProperties"] is False


@pytest.mark.parametrize("threshold", [-1, 101, 85.5, True])
def test_threshold_must_be_bounded_integer(threshold: object) -> None:
    with pytest.raises(ValueError, match="threshold"):
        evaluate_review(SlideReviewPayload.model_validate(_payload()), threshold=threshold)  # type: ignore[arg-type]
