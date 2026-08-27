from __future__ import annotations

import pytest
from pydantic import ValidationError

from pptrans.review.repairs import RepairPlan, UnsafeRepairPlan, validate_plan_targets


def _plan() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "slide_number": 3,
        "operations": [
            {
                "kind": "scale_font",
                "operation_id": "op1",
                "target_shape_id": "s3:shape:17",
                "scale": 0.9,
                "minimum_font_points": 9.0,
            },
            {
                "kind": "expand_text_box",
                "operation_id": "op2",
                "target_shape_id": "s3:shape:19",
                "width_scale": 1.0,
                "height_scale": 1.05,
            },
        ],
    }


def test_repair_plan_is_allowlisted_and_has_stable_fingerprint() -> None:
    first = RepairPlan.model_validate(_plan())
    second = RepairPlan.model_validate(_plan())
    assert first.fingerprint == second.fingerprint
    assert len(first.fingerprint) == 64
    validate_plan_targets(first, valid_shape_ids={"s3:shape:17", "s3:shape:19", "s3:shape:21"})


def test_repair_plan_rejects_unknown_shape_and_repeat() -> None:
    plan = RepairPlan.model_validate(_plan())
    with pytest.raises(UnsafeRepairPlan, match="unknown shape"):
        validate_plan_targets(plan, valid_shape_ids={"s3:shape:17"})
    with pytest.raises(UnsafeRepairPlan, match="repeats"):
        validate_plan_targets(
            plan,
            valid_shape_ids={"s3:shape:17", "s3:shape:19"},
            previous_fingerprints={plan.fingerprint},
        )


def test_repair_plan_enforces_one_operation_per_target() -> None:
    raw = _plan()
    raw["operations"][1]["target_shape_id"] = "s3:shape:17"  # type: ignore[index]
    with pytest.raises(ValidationError, match="one repair operation per target"):
        RepairPlan.model_validate(raw)


def test_repair_plan_rejects_cross_slide_target() -> None:
    raw = _plan()
    raw["operations"][0]["target_shape_id"] = "s4:shape:17"  # type: ignore[index]
    with pytest.raises(ValidationError, match="must belong to the plan slide"):
        RepairPlan.model_validate(raw)


@pytest.mark.parametrize("scale", [0.74, 1.0, float("nan"), float("inf")])
def test_font_scale_has_hard_safety_bounds(scale: float) -> None:
    raw = _plan()
    raw["operations"] = [
        {
            "kind": "scale_font",
            "operation_id": "op1",
            "target_shape_id": "s3:shape:17",
            "scale": scale,
            "minimum_font_points": 9.0,
        }
    ]
    with pytest.raises(ValidationError):
        RepairPlan.model_validate(raw)


def test_noop_box_expansion_is_rejected() -> None:
    raw = _plan()
    raw["operations"] = [
        {
            "kind": "expand_text_box",
            "operation_id": "op1",
            "target_shape_id": "s3:shape:17",
            "width_scale": 1.0,
            "height_scale": 1.0,
        }
    ]
    with pytest.raises(ValidationError, match="must expand"):
        RepairPlan.model_validate(raw)


def test_repair_plan_rejects_code_and_unknown_operations() -> None:
    raw = _plan()
    raw["operations"] = [
        {
            "kind": "run_python",
            "operation_id": "op1",
            "target_shape_id": "s3:shape:17",
            "code": "malicious payload",
        }
    ]
    with pytest.raises(ValidationError):
        RepairPlan.model_validate(raw)
