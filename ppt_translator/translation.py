"""Translation service orchestrating providers, caching and chunking."""
from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Dict, List, Optional

from .providers.base import TranslationProvider

_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?。！？])\s+")


class TranslationService:
    """Translate text using a configured provider with caching support."""

    def __init__(
        self,
        provider: TranslationProvider,
        *,
        max_chunk_size: int = 1000,
        memory_file: Optional[Path] = None,
        glossary: Optional[object] = None,
    ) -> None:
        self.provider = provider
        self.max_chunk_size = max_chunk_size
        self._cache: Dict[str, str] = {}
        self._lock = threading.Lock()
        # Import here to avoid circular imports
        from .memory import TranslationMemory, Glossary

        self.memory = TranslationMemory(memory_file) if memory_file else None
        self.glossary = glossary if glossary else None

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Translate ``text`` with glossary, memory, and caching support."""
        if not text or text.isspace():
            return text

        # Check in-memory cache first
        with self._lock:
            if text in self._cache:
                return self._cache[text]

        # Check translation memory (persistent across slides)
        if self.memory:
            cached = self.memory.get(text)
            if cached:
                with self._lock:
                    self._cache[text] = cached
                return cached

        # Translate using LLM provider (with glossary in prompt)
        glossary_dict = self.glossary._glossary if self.glossary else None
        chunks = self.chunk_text(text, self.max_chunk_size)
        translated_chunks: List[str] = []
        for chunk in chunks:
            stripped = chunk.strip()
            if not stripped:
                translated_chunks.append(chunk)
                continue
            # Pass glossary to provider so it's included in the prompt
            translated = self.provider.translate(chunk, source_lang, target_lang, glossary=glossary_dict)
            translated_chunks.append(translated.strip())

        combined = " ".join(part for part in translated_chunks if part)
        if not combined:
            combined = text

        # Post-process with glossary as a review/fallback (in case LLM missed some terms)
        if self.glossary:
            combined = self.glossary.apply(combined)

        # Cache and save to memory
        with self._lock:
            self._cache[text] = combined
        if self.memory:
            self.memory.set(text, combined)

        return combined

    @staticmethod
    def chunk_text(text: str, max_chunk_size: int = 1000) -> List[str]:
        """Split long text into smaller chunks preserving sentence boundaries."""
        if len(text) <= max_chunk_size:
            return [text]

        sentences = [segment.strip() for segment in _SENTENCE_SPLIT_PATTERN.split(text) if segment.strip()]
        if not sentences:
            sentences = [text]

        chunks: List[str] = []
        current: List[str] = []
        current_len = 0

        for sentence in sentences:
            sentence_len = len(sentence)
            if current and current_len + sentence_len + 1 > max_chunk_size:
                chunks.append(" ".join(current))
                current = []
                current_len = 0
            if sentence_len > max_chunk_size:
                if current:
                    chunks.append(" ".join(current))
                    current = []
                    current_len = 0
                chunks.extend(
                    [sentence[i : i + max_chunk_size] for i in range(0, sentence_len, max_chunk_size)]
                )
                continue
            current.append(sentence)
            current_len += sentence_len + 1

        if current:
            chunks.append(" ".join(current))

        if not chunks:
            return [text]
        return chunks

    def clear_cache(self) -> None:
        """Drop cached translations."""
        with self._lock:
            self._cache.clear()

    def cache_size(self) -> int:
        """Return the number of cached entries."""
        with self._lock:
            return len(self._cache)
