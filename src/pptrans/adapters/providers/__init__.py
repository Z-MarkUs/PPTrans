"""Concrete translation-provider adapters and their explicit factory."""

from __future__ import annotations

import os
from typing import Literal

from pptrans.application.errors import ProviderConfigurationError
from pptrans.ports.translator import Translator

from .anthropic import AnthropicTranslator
from .identity import IdentityTranslator
from .openai import OpenAITranslator

ProviderName = Literal["anthropic", "identity", "openai"]


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
    if provider == "openai":
        return OpenAITranslator(model=model, api_key=resolved_key.strip())
    return AnthropicTranslator(model=model, api_key=resolved_key.strip())


__all__ = [
    "AnthropicTranslator",
    "IdentityTranslator",
    "OpenAITranslator",
    "ProviderName",
    "create_translator",
]
