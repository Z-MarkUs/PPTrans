"""OpenAI Responses API translation adapter."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, cast

from openai import DefaultHttpxClient as OpenAIDefaultHttpxClient
from openai import OpenAI, OpenAIError

from pptrans.application.errors import ProviderRequestError, ProviderResponseError
from pptrans.ports.translator import ProviderUsage, TranslationBatchRequest, TranslationBatchResult
from pptrans.schemas.translation import TranslationBatchPayload

from .common import (
    SYSTEM_INSTRUCTIONS,
    parse_translation_payload,
    reject_ambient_sdk_routing,
    request_document,
)

MIN_OUTPUT_TOKENS = 256
OPENAI_API_BASE_URL = "https://api.openai.com/v1"
_ROUTING_ENVIRONMENT = ("OPENAI_BASE_URL", "OPENAI_CUSTOM_HEADERS")


class _ResponsesClient(Protocol):
    @property
    def create(self) -> Callable[..., object]: ...


class _OpenAIClient(Protocol):
    @property
    def responses(self) -> _ResponsesClient: ...


def _token_value(usage: object | None, name: str) -> int | None:
    value = getattr(usage, name, None)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


class OpenAITranslator:
    """Translate exact text spans with strict JSON Schema output."""

    provider = "openai"

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        timeout: float = 120.0,
        max_output_tokens: int = 16_000,
        client: _OpenAIClient | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("An explicit OpenAI model is required.")
        if max_output_tokens < MIN_OUTPUT_TOKENS:
            raise ValueError(f"max_output_tokens must be at least {MIN_OUTPUT_TOKENS}.")
        self.model = model.strip()
        self._max_output_tokens = max_output_tokens
        if client is None:
            reject_ambient_sdk_routing("OpenAI", _ROUTING_ENVIRONMENT)
            http_client = OpenAIDefaultHttpxClient(trust_env=False)
            client = cast(
                _OpenAIClient,
                OpenAI(
                    api_key=api_key,
                    base_url=OPENAI_API_BASE_URL,
                    timeout=timeout,
                    max_retries=2,
                    http_client=http_client,
                ),
            )
        self._client = client

    def translate(self, request: TranslationBatchRequest) -> TranslationBatchResult:
        """Call Responses with storage disabled and validate the complete result."""

        try:
            response = self._client.responses.create(
                model=self.model,
                instructions=SYSTEM_INSTRUCTIONS,
                input=request_document(request),
                max_output_tokens=self._max_output_tokens,
                store=False,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "pptrans_translation_batch",
                        "description": "Exact translated spans for a PPTrans batch.",
                        "strict": True,
                        "schema": TranslationBatchPayload.model_json_schema(),
                    }
                },
            )
        except OpenAIError as exc:
            raise ProviderRequestError("OpenAI translation request failed.") from exc

        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text.strip():
            raise ProviderResponseError("OpenAI returned no structured translation output.")
        parsed = parse_translation_payload(output_text)
        usage = getattr(response, "usage", None)
        return TranslationBatchResult(
            translations=parsed.translations,
            usage=ProviderUsage(
                input_tokens=_token_value(usage, "input_tokens"),
                output_tokens=_token_value(usage, "output_tokens"),
            ),
        )


__all__ = ["OpenAITranslator"]
