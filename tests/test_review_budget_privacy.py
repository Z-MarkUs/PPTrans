from __future__ import annotations

import pytest
from pydantic import ValidationError

from pptrans.review.budget import BudgetExceeded, BudgetLimit, BudgetLimits, ReviewBudget
from pptrans.review.privacy import (
    ImageRole,
    PrivacyMode,
    PrivacyPolicy,
    PrivacyViolation,
    redact_for_log,
    sanitize_shape_manifest,
    select_upload_roles,
    validate_review_endpoint,
)


def test_budget_reserves_resources_before_work() -> None:
    budget = ReviewBudget(
        BudgetLimits(
            max_requests=2,
            max_slides=1,
            max_repair_rounds_per_slide=1,
            max_upload_megapixels=1.0,
            max_output_tokens_per_request=100,
        )
    )
    budget.reserve_slide(2)
    budget.reserve_slide(2)
    budget.reserve_request(image_pixels=400_000, max_output_tokens=100)
    budget.record_response_usage(input_tokens=12, output_tokens=8)
    assert budget.reserve_repair_round(2) == 1

    usage = budget.snapshot()
    assert usage.requests == 1
    assert usage.slide_numbers == (2,)
    assert usage.repair_rounds == ((2, 1),)
    assert usage.uploaded_pixels == 400_000
    assert usage.input_tokens == 12
    assert usage.output_tokens == 8


def test_budget_fails_closed_without_incrementing_usage() -> None:
    budget = ReviewBudget(
        BudgetLimits(
            max_requests=1,
            max_upload_megapixels=0.5,
            max_output_tokens_per_request=64,
        )
    )
    with pytest.raises(BudgetExceeded) as error:
        budget.reserve_request(image_pixels=500_001, max_output_tokens=64)
    assert error.value.limit is BudgetLimit.UPLOAD_PIXELS
    assert budget.snapshot().requests == 0

    budget.reserve_request(image_pixels=500_000, max_output_tokens=64)
    with pytest.raises(BudgetExceeded) as error:
        budget.reserve_request(image_pixels=0, max_output_tokens=64)
    assert error.value.limit is BudgetLimit.REQUESTS


def test_repair_round_budget_is_per_slide() -> None:
    budget = ReviewBudget(BudgetLimits(max_repair_rounds_per_slide=1))
    budget.reserve_repair_round(1)
    with pytest.raises(BudgetExceeded) as error:
        budget.reserve_repair_round(1)
    assert error.value.limit is BudgetLimit.REPAIR_ROUNDS


def test_budget_limits_reject_boolean_integer() -> None:
    with pytest.raises(ValidationError):
        BudgetLimits(max_requests=True)


def test_privacy_modes_select_only_permitted_images() -> None:
    available = tuple(ImageRole)
    standard = select_upload_roles(available, PrivacyPolicy())
    assert standard == available
    translated_only = select_upload_roles(
        available, PrivacyPolicy(mode=PrivacyMode.TRANSLATED_ONLY)
    )
    assert ImageRole.ORIGINAL not in translated_only
    assert ImageRole.TRANSLATED in translated_only
    assert select_upload_roles(available, PrivacyPolicy(mode=PrivacyMode.OFFLINE)) == ()


def test_cloud_review_requires_translated_render() -> None:
    with pytest.raises(PrivacyViolation, match="translated slide render"):
        select_upload_roles((ImageRole.ORIGINAL,), PrivacyPolicy())


def test_endpoint_validation_requires_https_and_explicit_custom_consent() -> None:
    policy = PrivacyPolicy()
    assert (
        validate_review_endpoint("https://api.openai.com/v1", provider="openai", policy=policy)
        == "https://api.openai.com/v1"
    )
    with pytest.raises(PrivacyViolation, match="HTTPS"):
        validate_review_endpoint("http://api.openai.com/v1", provider="openai", policy=policy)
    with pytest.raises(PrivacyViolation, match="allow_custom_endpoint"):
        validate_review_endpoint("https://models.example/v1", provider="openai", policy=policy)
    custom = PrivacyPolicy(allow_custom_endpoint=True)
    assert validate_review_endpoint(
        "https://models.example/v1", provider="openai", policy=custom
    ).startswith("https://models.example")
    with pytest.raises(PrivacyViolation, match="offline"):
        validate_review_endpoint(
            "https://api.openai.com/v1",
            provider="openai",
            policy=PrivacyPolicy(mode=PrivacyMode.OFFLINE),
        )


def test_manifest_omits_text_and_unapproved_metadata_by_default() -> None:
    entry = {
        "shape_id": "s1:shape:1",
        "shape_type": "textbox",
        "bbox": {"x": 0.1},
        "text": "confidential",
        "speaker_notes": "never upload",
        "raw_xml": "<xml />",
    }
    safe = sanitize_shape_manifest([entry], PrivacyPolicy())
    assert safe == ({"shape_id": "s1:shape:1", "shape_type": "textbox", "bbox": {"x": 0.1}},)
    with_text = sanitize_shape_manifest([entry], PrivacyPolicy(include_manifest_text=True))
    assert with_text[0]["text"] == "confidential"
    assert "speaker_notes" not in with_text[0]


def test_manifest_recursively_drops_unapproved_nested_fields() -> None:
    entry = {
        "shape_id": "s1:shape:1",
        "shape_type": "textbox",
        "bbox": {
            "x": 0.1,
            "width": 0.5,
            "text": "nested secret",
            "metadata": {"text": "deeper secret"},
        },
        "text": "explicit text",
        "metadata": {"bbox": {"text": "top-level secret"}},
    }

    safe = sanitize_shape_manifest([entry], PrivacyPolicy(include_manifest_text=True))

    assert safe == (
        {
            "shape_id": "s1:shape:1",
            "shape_type": "textbox",
            "bbox": {"x": 0.1, "width": 0.5},
            "text": "explicit text",
        },
    )


@pytest.mark.parametrize(
    ("entry", "include_text"),
    [
        ({"shape_id": "nested secret"}, False),
        ({"shape_type": {"text": "nested secret"}}, False),
        ({"bbox": "nested secret"}, False),
        ({"bbox": {"x": {"text": "nested secret"}}}, False),
        ({"font_size_min": True}, False),
        ({"text": {"text": "nested secret"}}, True),
    ],
)
def test_manifest_rejects_invalid_types_without_echoing_values(
    entry: dict[str, object], *, include_text: bool
) -> None:
    with pytest.raises(PrivacyViolation) as error:
        sanitize_shape_manifest([entry], PrivacyPolicy(include_manifest_text=include_text))

    assert "nested secret" not in str(error.value)


@pytest.mark.parametrize(
    "entry",
    [
        {"bbox": {"x": -0.1}},
        {"bbox": {"width": 0.0}},
        {"bbox": {"x": 0.8, "width": 0.3}},
        {"bbox": {"y": 0.8, "height": 0.3}},
        {"font_size_min": 0.0},
        {"font_size_max": 1_000.1},
        {"font_size_min": 20.0, "font_size_max": 10.0},
    ],
)
def test_manifest_rejects_out_of_bounds_geometry_and_font_sizes(
    entry: dict[str, object],
) -> None:
    with pytest.raises(PrivacyViolation):
        sanitize_shape_manifest([entry], PrivacyPolicy())


def test_manifest_text_requires_policy_and_has_per_entry_size_limit() -> None:
    oversized_text = "do not echo this secret" * 2_000

    assert sanitize_shape_manifest(
        [{"shape_id": "s1:shape:1", "text": oversized_text}], PrivacyPolicy()
    ) == ({"shape_id": "s1:shape:1"},)
    with pytest.raises(PrivacyViolation) as error:
        sanitize_shape_manifest(
            [{"shape_id": "s1:shape:1", "text": oversized_text}],
            PrivacyPolicy(include_manifest_text=True),
        )
    assert "do not echo this secret" not in str(error.value)


def test_manifest_entry_count_is_bounded() -> None:
    entries = ({"shape_id": "s1:shape:1"} for _ in range(10_001))

    with pytest.raises(PrivacyViolation, match="too many entries"):
        sanitize_shape_manifest(entries, PrivacyPolicy())


def test_manifest_rejects_non_mapping_entries_and_non_finite_numbers() -> None:
    with pytest.raises(PrivacyViolation, match="entry must be an object"):
        sanitize_shape_manifest([object()], PrivacyPolicy())  # type: ignore[list-item]
    for number in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(PrivacyViolation, match="finite number"):
            sanitize_shape_manifest([{"bbox": {"x": number}}], PrivacyPolicy())


def test_manifest_total_included_text_is_bounded() -> None:
    entry = {"shape_id": "s1:shape:1", "text": "x" * 32_768}

    with pytest.raises(PrivacyViolation, match="too much text"):
        sanitize_shape_manifest(
            [entry] * 31,
            PrivacyPolicy(include_manifest_text=True),
        )


def test_log_redaction_removes_secrets_and_image_payloads() -> None:
    logged = redact_for_log(
        {
            "api_key": "secret",
            "authorization": "Bearer abcdef",
            "image_data": "data:image/png;base64,abcd",
            "bytes": b"binary",
            "summary": "safe",
            "nested": ["sk-ant-abcdefghijkl", "visible"],
        }
    )
    assert logged["api_key"] == "<redacted>"
    assert logged["authorization"] == "<redacted>"
    assert logged["image_data"] == "<redacted>"
    assert logged["bytes"] == "<redacted-bytes:6>"
    assert logged["nested"] == ["<redacted>", "visible"]
    assert logged["summary"] == "safe"
