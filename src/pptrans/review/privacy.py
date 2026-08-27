"""Privacy policy and logging redaction for cloud-assisted slide review."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, StrictBool


class PrivacyMode(str, Enum):
    STANDARD = "standard"
    TRANSLATED_ONLY = "translated-only"
    OFFLINE = "offline"


class ImageRole(str, Enum):
    ORIGINAL = "original"
    TRANSLATED = "translated"
    SHAPE_OVERLAY = "shape_overlay"


class PrivacyViolation(ValueError):  # noqa: N818 - reads naturally at call sites
    """Raised when an upload or endpoint conflicts with the active policy."""


class PrivacyPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    mode: PrivacyMode = PrivacyMode.STANDARD
    include_manifest_text: StrictBool = False
    keep_review_artifacts: StrictBool = False
    allow_custom_endpoint: StrictBool = False

    @property
    def network_allowed(self) -> bool:
        return self.mode is not PrivacyMode.OFFLINE

    @property
    def upload_roles(self) -> tuple[ImageRole, ...]:
        if self.mode is PrivacyMode.OFFLINE:
            return ()
        if self.mode is PrivacyMode.TRANSLATED_ONLY:
            return (ImageRole.TRANSLATED, ImageRole.SHAPE_OVERLAY)
        return (ImageRole.ORIGINAL, ImageRole.TRANSLATED, ImageRole.SHAPE_OVERLAY)


_KNOWN_PROVIDER_HOSTS: dict[str, frozenset[str]] = {
    "openai": frozenset({"api.openai.com"}),
    "anthropic": frozenset({"api.anthropic.com"}),
}


def validate_review_endpoint(endpoint: str, *, provider: str, policy: PrivacyPolicy) -> str:
    """Validate and normalize a remote endpoint before any review request."""

    if not policy.network_allowed:
        raise PrivacyViolation("offline privacy mode forbids network review endpoints")
    parsed = urlparse(endpoint)
    if parsed.scheme.lower() != "https":
        raise PrivacyViolation("review endpoints must use HTTPS")
    if not parsed.hostname or parsed.username or parsed.password:
        raise PrivacyViolation("review endpoint authority is invalid")
    if parsed.query or parsed.fragment:
        raise PrivacyViolation("review endpoints may not contain a query or fragment")

    host = parsed.hostname.rstrip(".").lower()
    known_hosts = _KNOWN_PROVIDER_HOSTS.get(provider.lower(), frozenset())
    if host not in known_hosts and not policy.allow_custom_endpoint:
        raise PrivacyViolation(
            f"custom review endpoint '{host}' requires allow_custom_endpoint=True"
        )
    return parsed._replace(netloc=host if parsed.port is None else f"{host}:{parsed.port}").geturl()


def select_upload_roles(
    available_roles: Iterable[ImageRole], policy: PrivacyPolicy
) -> tuple[ImageRole, ...]:
    """Select only the image roles permitted by the active privacy policy."""

    available = set(available_roles)
    selected = tuple(role for role in policy.upload_roles if role in available)
    if policy.network_allowed and ImageRole.TRANSLATED not in selected:
        raise PrivacyViolation("a translated slide render is required for cloud review")
    return selected


_SHAPE_ID = re.compile(
    r"^s[1-9][0-9]*:shape:[1-9][0-9]*"
    r"(?::(?:shape:[1-9][0-9]*|cell:r[0-9]+c[0-9]+))*$"
)
_SHAPE_TYPE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_BBOX_FIELDS = ("x", "y", "width", "height")
_MAX_MANIFEST_ENTRIES = 10_000
_MAX_MANIFEST_TEXT_LENGTH = 32_768
_MAX_MANIFEST_TEXT_TOTAL = 1_000_000


def _manifest_string(
    value: Any,
    *,
    field: str,
    max_length: int,
    pattern: re.Pattern[str] | None = None,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise PrivacyViolation(f"shape manifest {field} must be a string")
    if (not allow_empty and not value) or len(value) > max_length:
        raise PrivacyViolation(f"shape manifest {field} has an invalid length")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise PrivacyViolation(f"shape manifest {field} has an invalid format")
    return str(value)


def _manifest_number(
    value: Any,
    *,
    field: str,
    minimum: float,
    maximum: float,
    minimum_inclusive: bool = True,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PrivacyViolation(f"shape manifest {field} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise PrivacyViolation(f"shape manifest {field} must be a finite number")
    below_minimum = number < minimum if minimum_inclusive else number <= minimum
    if below_minimum or number > maximum:
        raise PrivacyViolation(f"shape manifest {field} is outside the permitted range")
    return number


def _sanitize_bbox(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise PrivacyViolation("shape manifest bbox must be an object")

    result: dict[str, float] = {}
    for field in _BBOX_FIELDS:
        if field not in value:
            continue
        result[field] = _manifest_number(
            value[field],
            field=f"bbox.{field}",
            minimum=0.0,
            maximum=1.0,
            minimum_inclusive=field in {"x", "y"},
        )

    epsilon = 1e-9
    if "x" in result and "width" in result and result["x"] + result["width"] > 1 + epsilon:
        raise PrivacyViolation("shape manifest bbox extends beyond the horizontal boundary")
    if "y" in result and "height" in result and result["y"] + result["height"] > 1 + epsilon:
        raise PrivacyViolation("shape manifest bbox extends beyond the vertical boundary")
    return result


def _sanitize_manifest_entry(entry: Mapping[str, Any], policy: PrivacyPolicy) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if "shape_id" in entry:
        result["shape_id"] = _manifest_string(
            entry["shape_id"], field="shape_id", max_length=128, pattern=_SHAPE_ID
        )
    if "shape_type" in entry:
        result["shape_type"] = _manifest_string(
            entry["shape_type"], field="shape_type", max_length=64, pattern=_SHAPE_TYPE
        )
    if "bbox" in entry:
        result["bbox"] = _sanitize_bbox(entry["bbox"])
    if "font_size_min" in entry:
        result["font_size_min"] = _manifest_number(
            entry["font_size_min"],
            field="font_size_min",
            minimum=0.0,
            maximum=1_000.0,
            minimum_inclusive=False,
        )
    if "font_size_max" in entry:
        result["font_size_max"] = _manifest_number(
            entry["font_size_max"],
            field="font_size_max",
            minimum=0.0,
            maximum=1_000.0,
            minimum_inclusive=False,
        )
    if (
        "font_size_min" in result
        and "font_size_max" in result
        and result["font_size_min"] > result["font_size_max"]
    ):
        raise PrivacyViolation("shape manifest font-size bounds are inconsistent")
    if policy.include_manifest_text and "text" in entry:
        result["text"] = _manifest_string(
            entry["text"],
            field="text",
            max_length=_MAX_MANIFEST_TEXT_LENGTH,
            allow_empty=True,
        )
    return result


def sanitize_shape_manifest(
    entries: Iterable[Mapping[str, Any]], policy: PrivacyPolicy
) -> tuple[dict[str, Any], ...]:
    """Return a bounded manifest containing only recursively validated safe fields.

    Free-form shape text is copied only when ``include_manifest_text`` is explicitly
    enabled. Unknown top-level and nested fields are dropped rather than forwarded.
    """

    result: list[dict[str, Any]] = []
    total_text_length = 0
    for index, entry in enumerate(entries):
        if index >= _MAX_MANIFEST_ENTRIES:
            raise PrivacyViolation("shape manifest contains too many entries")
        if not isinstance(entry, Mapping):
            raise PrivacyViolation("shape manifest entry must be an object")
        sanitized = _sanitize_manifest_entry(entry, policy)
        text = sanitized.get("text")
        if isinstance(text, str):
            total_text_length += len(text)
            if total_text_length > _MAX_MANIFEST_TEXT_TOTAL:
                raise PrivacyViolation("shape manifest contains too much text")
        result.append(sanitized)
    return tuple(result)


_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|authorization|password|secret|token|png[_-]?bytes|image[_-]?data|base64)",
    re.IGNORECASE,
)
_SECRET_TEXT = re.compile(r"(?:Bearer\s+\S+|sk-(?:ant-)?[A-Za-z0-9_-]{8,})", re.IGNORECASE)


def redact_for_log(value: Any, *, _key: str = "") -> Any:
    """Return a logging-safe copy of nested request metadata."""

    if _key and _SENSITIVE_KEY.search(_key):
        result: Any = "<redacted>"
    elif isinstance(value, Mapping):
        result = {str(key): redact_for_log(item, _key=str(key)) for key, item in value.items()}
    elif isinstance(value, (list, tuple)):
        result = [redact_for_log(item) for item in value]
    elif isinstance(value, (bytes, bytearray, memoryview)):
        result = f"<redacted-bytes:{len(value)}>"
    elif isinstance(value, str) and (value.startswith("data:image/") or _SECRET_TEXT.search(value)):
        result = "<redacted>"
    else:
        result = value
    return result


__all__ = [
    "ImageRole",
    "PrivacyMode",
    "PrivacyPolicy",
    "PrivacyViolation",
    "redact_for_log",
    "sanitize_shape_manifest",
    "select_upload_roles",
    "validate_review_endpoint",
]
