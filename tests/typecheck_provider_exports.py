"""Downstream typing contract for the lazy paid-provider exports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pptrans.adapters.providers import AnthropicTranslator, OpenAITranslator
    from pptrans.ports.translator import TranslationBatchRequest, TranslationBatchResult

    class _OpenAIResponses:
        def create(self, **kwargs: Any) -> object:
            raise NotImplementedError

    class _OpenAIClient:
        @property
        def responses(self) -> _OpenAIResponses:
            return _OpenAIResponses()

    class _AnthropicMessages:
        def create(self, **kwargs: Any) -> object:
            raise NotImplementedError

    class _AnthropicClient:
        @property
        def messages(self) -> _AnthropicMessages:
            return _AnthropicMessages()

    openai: OpenAITranslator = OpenAITranslator(
        model="test-model",
        api_key="not-a-real-key",
        timeout=1.0,
        max_output_tokens=256,
        client=_OpenAIClient(),
    )
    anthropic: AnthropicTranslator = AnthropicTranslator(
        model="test-model",
        api_key="not-a-real-key",
        timeout=1.0,
        max_output_tokens=256,
        client=_AnthropicClient(),
    )

    def _openai_result(
        translator: OpenAITranslator,
        request: TranslationBatchRequest,
    ) -> TranslationBatchResult:
        return translator.translate(request)

    def _anthropic_result(
        translator: AnthropicTranslator,
        request: TranslationBatchRequest,
    ) -> TranslationBatchResult:
        return translator.translate(request)
