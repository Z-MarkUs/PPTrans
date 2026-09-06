"""Concrete translation-provider adapters and their explicit factory."""

from __future__ import annotations

import os
from collections.abc import Callable
from importlib import import_module
from typing import TYPE_CHECKING, Literal, Protocol, cast

from pptrans.application.errors import ProviderConfigurationError
from pptrans.ports.translator import Translator

from .identity import IdentityTranslator

ProviderName = Literal["anthropic", "identity", "openai"]
PaidProviderName = Literal["anthropic", "openai"]

_PROVIDER_CLASSES: dict[PaidProviderName, str] = {
    "anthropic": "AnthropicTranslator",
    "openai": "OpenAITranslator",
}


class _ProviderConstructor(Protocol):
    def __call__(self, *, model: str, api_key: str) -> Translator: ...


if TYPE_CHECKING:
    from pptrans.ports.translator import TranslationBatchRequest, TranslationBatchResult

    class _OpenAIResponsesClient(Protocol):
        @property
        def create(self) -> Callable[..., object]: ...

    class _OpenAIClient(Protocol):
        @property
        def responses(self) -> _OpenAIResponsesClient: ...

    class _AnthropicMessagesClient(Protocol):
        @property
        def create(self) -> Callable[..., object]: ...

    class _AnthropicClient(Protocol):
        @property
        def messages(self) -> _AnthropicMessagesClient: ...

    class OpenAITranslator:
        provider: Literal["openai"]
        model: str

        def __init__(
            self,
            *,
            model: str,
            api_key: str | None = None,
            timeout: float = 120.0,
            max_output_tokens: int = 16_000,
            client: _OpenAIClient | None = None,
        ) -> None: ...

        def translate(self, request: TranslationBatchRequest) -> TranslationBatchResult: ...

    class AnthropicTranslator:
        provider: Literal["anthropic"]
        model: str

        def __init__(
            self,
            *,
            model: str,
            api_key: str | None = None,
            timeout: float = 120.0,
            max_output_tokens: int = 16_000,
            client: _AnthropicClient | None = None,
        ) -> None: ...

        def translate(self, request: TranslationBatchRequest) -> TranslationBatchResult: ...


def _load_provider_constructor(provider: PaidProviderName) -> _ProviderConstructor:
    """Load a paid adapter only after its provider is explicitly selected."""

    try:
        module = import_module(f"{__name__}.{provider}")
    except ModuleNotFoundError as exc:
        if exc.name == provider:
            raise ProviderConfigurationError(
                f"Provider {provider!r} requires its optional SDK. Install "
                f'`pptrans[{provider}]` or `-e ".[{provider}]"` from a source checkout.'
            ) from exc
        raise
    return cast(_ProviderConstructor, getattr(module, _PROVIDER_CLASSES[provider]))


def create_translator(
    provider: ProviderName,
    *,
    model: str | None,
    api_key: str | None = None,
) -> Translator:
    """Create a provider without guessing a paid model or credential."""

    if provider not in {"anthropic", "identity", "openai"}:
        raise ProviderConfigurationError(f"Unsupported provider: {provider!r}.")
    if provider == "identity":
        if model not in (None, "", IdentityTranslator.model):
            raise ProviderConfigurationError("The identity provider only supports identity-v1.")
        return IdentityTranslator()

    if not model or not model.strip():
        raise ProviderConfigurationError(f"--model is required for provider {provider!r}.")
    environment_name = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
    resolved_key = api_key if api_key is not None else os.getenv(environment_name)
    if not resolved_key or not resolved_key.strip():
        raise ProviderConfigurationError(
            f"Set {environment_name} or pass a key through the Python API."
        )
    constructor = _load_provider_constructor(provider)
    return constructor(model=model, api_key=resolved_key.strip())


def __getattr__(name: str) -> object:
    """Preserve lazy public class imports without loading both paid SDKs."""

    for provider, class_name in _PROVIDER_CLASSES.items():
        if name == class_name:
            return _load_provider_constructor(provider)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AnthropicTranslator",
    "IdentityTranslator",
    "OpenAITranslator",
    "PaidProviderName",
    "ProviderName",
    "create_translator",
]
