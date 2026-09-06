"""Shared serialization and validation for model-provider adapters."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from typing import Any

from pydantic import ValidationError

from pptrans.application.errors import ProviderConfigurationError, ProviderResponseError
from pptrans.domain.models import TranslatedSpan
from pptrans.ports.translator import (
    TranslationBatchRequest,
    TranslationBatchResult,
    UnitTranslation,
)
from pptrans.schemas.translation import TranslationBatchPayload
from pptrans.translation_contract import (
    MAX_REQUEST_CHARACTERS,
    SYSTEM_INSTRUCTIONS,
    serialize_request_document,
)


def reject_ambient_sdk_routing(provider: str, variable_names: Iterable[str]) -> None:
    """Reject SDK routing overrides that PPTrans did not receive explicitly."""

    present = sorted(name for name in variable_names if name in os.environ)
    if present:
        joined = ", ".join(present)
        raise ProviderConfigurationError(
            f"PPTrans does not accept ambient {provider} SDK routing settings: {joined}. "
            "Remove them before using the built-in provider adapter."
        )


def request_document(request: TranslationBatchRequest) -> str:
    """Serialize only the content required for translation."""

    return serialize_request_document(request, max_characters=MAX_REQUEST_CHARACTERS)


def parse_translation_payload(raw: str | bytes | dict[str, Any]) -> TranslationBatchResult:
    """Parse strict JSON output into provider-neutral immutable values."""

    try:
        if isinstance(raw, (str, bytes)):
            parsed: object = json.loads(raw)
        else:
            parsed = raw
        payload = TranslationBatchPayload.model_validate(parsed, strict=True)
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as exc:
        raise ProviderResponseError("Provider returned an invalid translation payload.") from exc
    return TranslationBatchResult(
        translations=tuple(
            UnitTranslation(
                unit_id=unit.unit_id,
                spans=tuple(
                    TranslatedSpan(span_id=span.span_id, text=span.text) for span in unit.spans
                ),
            )
            for unit in payload.translations
        )
    )


__all__ = [
    "SYSTEM_INSTRUCTIONS",
    "parse_translation_payload",
    "reject_ambient_sdk_routing",
    "request_document",
]
