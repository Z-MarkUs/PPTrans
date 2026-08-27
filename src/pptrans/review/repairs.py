"""Validated, deterministic repair plans.

This module defines data only.  It intentionally provides no dynamic property
access and no facility for accepting or running source code from a model.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from pptrans.schemas.review import ShapeId


class RepairKind(str, Enum):
    ENABLE_WORD_WRAP = "enable_word_wrap"
    SCALE_FONT = "scale_font"
    REDUCE_TEXT_MARGINS = "reduce_text_margins"
    TIGHTEN_LINE_SPACING = "tighten_line_spacing"
    EXPAND_TEXT_BOX = "expand_text_box"
    RESTORE_ORIGINAL_GEOMETRY = "restore_original_geometry"


OperationId = Annotated[
    str,
    StringConstraints(min_length=3, max_length=6, pattern=r"^op[0-9]{1,3}$"),
]


class _Operation(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, str_strip_whitespace=True, validate_default=True
    )

    operation_id: OperationId
    target_shape_id: ShapeId


class EnableWordWrap(_Operation):
    kind: Literal[RepairKind.ENABLE_WORD_WRAP] = RepairKind.ENABLE_WORD_WRAP


class ScaleFont(_Operation):
    kind: Literal[RepairKind.SCALE_FONT] = RepairKind.SCALE_FONT
    scale: float = Field(strict=True, ge=0.75, lt=1.0, allow_inf_nan=False)
    minimum_font_points: float = Field(
        default=9.0, strict=True, ge=6.0, le=18.0, allow_inf_nan=False
    )


class ReduceTextMargins(_Operation):
    kind: Literal[RepairKind.REDUCE_TEXT_MARGINS] = RepairKind.REDUCE_TEXT_MARGINS
    scale: float = Field(strict=True, ge=0.25, le=0.95, allow_inf_nan=False)


class TightenLineSpacing(_Operation):
    kind: Literal[RepairKind.TIGHTEN_LINE_SPACING] = RepairKind.TIGHTEN_LINE_SPACING
    scale: float = Field(strict=True, ge=0.85, le=0.99, allow_inf_nan=False)


class ExpandTextBox(_Operation):
    kind: Literal[RepairKind.EXPAND_TEXT_BOX] = RepairKind.EXPAND_TEXT_BOX
    width_scale: float = Field(default=1.0, strict=True, ge=1.0, le=1.10, allow_inf_nan=False)
    height_scale: float = Field(default=1.0, strict=True, ge=1.0, le=1.10, allow_inf_nan=False)

    @model_validator(mode="after")
    def require_expansion(self) -> ExpandTextBox:
        if self.width_scale == 1.0 and self.height_scale == 1.0:
            raise ValueError("at least one text-box dimension must expand")
        return self


class RestoreOriginalGeometry(_Operation):
    kind: Literal[RepairKind.RESTORE_ORIGINAL_GEOMETRY] = RepairKind.RESTORE_ORIGINAL_GEOMETRY


RepairOperation = Annotated[
    EnableWordWrap
    | ScaleFont
    | ReduceTextMargins
    | TightenLineSpacing
    | ExpandTextBox
    | RestoreOriginalGeometry,
    Field(discriminator="kind"),
]


class RepairPlan(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, str_strip_whitespace=True, validate_default=True
    )

    schema_version: Literal["1.0"] = "1.0"
    slide_number: int = Field(strict=True, ge=1, le=100_000)
    operations: tuple[RepairOperation, ...] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def enforce_one_operation_per_target(self) -> RepairPlan:
        target_ids = [operation.target_shape_id for operation in self.operations]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("only one repair operation per target is allowed in a round")
        expected_prefix = f"s{self.slide_number}:"
        if any(not target.startswith(expected_prefix) for target in target_ids):
            raise ValueError("every repair target must belong to the plan slide")
        return self

    @property
    def fingerprint(self) -> str:
        canonical = self.model_dump_json(exclude_none=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class UnsafeRepairPlan(ValueError):  # noqa: N818 - reads naturally at call sites
    """Raised when a valid schema still conflicts with local slide state."""


def validate_plan_targets(
    plan: RepairPlan,
    *,
    valid_shape_ids: set[str] | frozenset[str],
    previous_fingerprints: set[str] | frozenset[str] = frozenset(),
) -> None:
    unknown = sorted(
        operation.target_shape_id
        for operation in plan.operations
        if operation.target_shape_id not in valid_shape_ids
    )
    if unknown:
        raise UnsafeRepairPlan(f"repair plan contains unknown shape ids: {', '.join(unknown)}")
    if plan.fingerprint in previous_fingerprints:
        raise UnsafeRepairPlan("repair plan repeats a previously attempted plan")


__all__ = [
    "EnableWordWrap",
    "ExpandTextBox",
    "ReduceTextMargins",
    "RepairKind",
    "RepairOperation",
    "RepairPlan",
    "RestoreOriginalGeometry",
    "ScaleFont",
    "TightenLineSpacing",
    "UnsafeRepairPlan",
    "validate_plan_targets",
]
