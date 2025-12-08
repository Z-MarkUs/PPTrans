"""Base classes for translation providers."""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from openai import OpenAI


class ProviderConfigurationError(RuntimeError):
    """Raised when a provider cannot be configured properly."""


class TranslationProvider(ABC):
    """Abstract provider responsible for translating text."""

    def __init__(self, model: str, temperature: float = 0.3) -> None:
        self.model = model
        self.temperature = temperature

    @abstractmethod
    def translate(
        self, text: str, source_lang: str, target_lang: str, glossary: Optional[Dict[str, str]] = None
    ) -> str:
        """Translate ``text`` from ``source_lang`` to ``target_lang``.
        
        Args:
            text: Text to translate
            source_lang: Source language code
            target_lang: Target language code
            glossary: Optional dictionary of preferred translations (key -> value)
        """
    
    def vision_call(
        self, prompt: str, image_paths: List[str], model: Optional[str] = None
    ) -> str:
        """Make a vision API call with images (optional, for vision-capable providers).
        
        Args:
            prompt: Text prompt for the vision model
            image_paths: List of base64-encoded image strings or file paths
            model: Optional model override (defaults to self.model)
        
        Returns:
            Response text from the vision model
        
        Raises:
            NotImplementedError: If provider doesn't support vision
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support vision calls")


class OpenAICompatibleProvider(TranslationProvider):
    """Provider implementation for OpenAI compatible chat completion APIs."""

    api_key_env: str = "OPENAI_API_KEY"
    default_base_url: str | None = None

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.3,
        organization: str | None = None,
    ) -> None:
        super().__init__(model, temperature=temperature)
        resolved_key = api_key or os.getenv(self.api_key_env)
        if not resolved_key:
            raise ProviderConfigurationError(
                f"Missing API key for provider '{self.__class__.__name__}'. "
                f"Set the {self.api_key_env} environment variable."
            )
        self.client = OpenAI(api_key=resolved_key, base_url=base_url or self.default_base_url, organization=organization)

    def build_messages(
        self, text: str, source_lang: str, target_lang: str, glossary: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, str]]:
        """Construct chat messages sent to the model."""
        system_prompt = (
            "You are a translation assistant. Translate the user provided text "
            f"from {source_lang} to {target_lang} while preserving tone and formatting."
        )
        
        # Include glossary in the prompt if provided
        if glossary:
            glossary_text = "\n".join([f"- {key} → {value}" for key, value in sorted(glossary.items())])
            system_prompt += (
                f"\n\nIMPORTANT: Use the following preferred translations when applicable:\n{glossary_text}\n"
                "Always use these exact terms when translating the corresponding words or phrases."
            )
        
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]

    def translate(
        self, text: str, source_lang: str, target_lang: str, glossary: Optional[Dict[str, str]] = None
    ) -> str:
        # Some models don't support custom temperature, try with it first, then without
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.build_messages(text, source_lang, target_lang, glossary),
                temperature=self.temperature,
                stream=False,
            )
        except Exception as e:
            # If temperature is not supported, retry without it
            error_str = str(e).lower()
            if "temperature" in error_str or "unsupported_value" in error_str:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.build_messages(text, source_lang, target_lang, glossary),
                    stream=False,
                )
            else:
                raise
        return response.choices[0].message.content.strip()
    
    def vision_call(
        self, prompt: str, image_paths: List[str], model: Optional[str] = None
    ) -> str:
        """Make a vision API call using OpenAI-compatible vision models."""
        import base64
        from pathlib import Path
        
        # Encode images to base64
        image_contents = []
        for img_path in image_paths:
            if isinstance(img_path, str) and Path(img_path).exists():
                with open(img_path, "rb") as f:
                    image_data = base64.b64encode(f.read()).decode('utf-8')
                    image_contents.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_data}"
                        }
                    })
            elif isinstance(img_path, str) and img_path.startswith("data:"):
                # Already base64 encoded
                image_contents.append({
                    "type": "image_url",
                    "image_url": {"url": img_path}
                })
            else:
                # Assume it's already base64 string
                image_contents.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img_path}"
                    }
                })
        
        # Build messages with images
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    *image_contents
                ]
            }
        ]
        
        # Use the provided model (required - no auto-selection)
        if not model:
            raise ValueError("Vision model must be explicitly specified. Please provide a vision-capable model name.")
        vision_model = model
        
        try:
            response = self.client.chat.completions.create(
                model=vision_model,
                messages=messages,
                temperature=self.temperature,
                stream=False,
            )
        except Exception as e:
            # If temperature is not supported, retry without it
            error_str = str(e).lower()
            if "temperature" in error_str or "unsupported_value" in error_str:
                response = self.client.chat.completions.create(
                    model=vision_model,
                    messages=messages,
                    stream=False,
                )
            else:
                raise
        
        return response.choices[0].message.content.strip()
