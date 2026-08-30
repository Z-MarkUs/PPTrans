"""Anthropic Messages API translation adapter using a forced schema tool."""

from __future__ import annotations

from typing import Any, Protocol, cast

from anthropic import Anthropic, AnthropicError
from anthropic import DefaultHttpxClient as AnthropicDefaultHttpxClient

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
ANTHROPIC_API_BASE_URL = "https://api.anthropic.com"
_ROUTING_ENVIRONMENT = ("ANTHROPIC_BASE_URL", "ANTHROPIC_CUSTOM_HEADERS")


class _MessagesClient(Protocol):
    def create(self, **kwargs: Any) -> object: ...


class _AnthropicClient(Protocol):
    @property
    def messages(self) -> _MessagesClient: ...


def _token_value(usage: object | None, name: str) -> int | None:
    value = getattr(usage, name, None)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


class AnthropicTranslator:
    """Translate exact spans through one required structured tool call."""

    provider = "anthropic"

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        timeout: float = 120.0,
        max_output_tokens: int = 16_000,
        client: _AnthropicClient | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("An explicit Anthropic model is required.")
        if max_output_tokens < MIN_OUTPUT_TOKENS:
            raise ValueError(f"max_output_tokens must be at least {MIN_OUTPUT_TOKENS}.")
        self.model = model.strip()
        self._max_output_tokens = max_output_tokens
        if client is None:
            reject_ambient_sdk_routing("Anthropic", _ROUTING_ENVIRONMENT)
            http_client = AnthropicDefaultHttpxClient(trust_env=False)
            client = cast(
                _AnthropicClient,
                Anthropic(
                    api_key=api_key,
                    base_url=ANTHROPIC_API_BASE_URL,
                    timeout=timeout,
                    max_retries=2,
                    http_client=http_client,
                ),
            )
        self._client = client

    def translate(self, request: TranslationBatchRequest) -> TranslationBatchResult:
        """Force a tool-shaped response and reject text-only or duplicate output."""

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self._max_output_tokens,
                system=SYSTEM_INSTRUCTIONS,
                messages=[{"role": "user", "content": request_document(request)}],
                tools=[
                    {
                        "name": "submit_translations",
                        "description": "Submit every requested unit and translated span.",
                        "input_schema": TranslationBatchPayload.model_json_schema(),
                    }
                ],
                tool_choice={"type": "tool", "name": "submit_translations"},
            )
        except AnthropicError as exc:
            raise ProviderRequestError("Anthropic translation request failed.") from exc

        content = getattr(response, "content", ())
        blocks = content if isinstance(content, (list, tuple)) else ()
        if len(blocks) != 1:
            raise ProviderResponseError(
                "Anthropic did not return exactly one structured translation tool call."
            )
        block = blocks[0]
        payload = getattr(block, "input", None)
        if (
            getattr(block, "type", None) != "tool_use"
            or getattr(block, "name", None) != "submit_translations"
            or not isinstance(payload, dict)
        ):
            raise ProviderResponseError(
                "Anthropic did not return exactly one structured translation tool call."
            )
        parsed = parse_translation_payload(cast(dict[str, Any], payload))
        usage = getattr(response, "usage", None)
        return TranslationBatchResult(
            translations=parsed.translations,
            usage=ProviderUsage(
                input_tokens=_token_value(usage, "input_tokens"),
                output_tokens=_token_value(usage, "output_tokens"),
            ),
        )


__all__ = ["AnthropicTranslator"]
