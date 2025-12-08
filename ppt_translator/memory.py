"""Translation memory and glossary management."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, Optional


class TranslationMemory:
    """Simple translation memory using a temporary JSON file."""

    def __init__(self, memory_file: Path) -> None:
        """Initialize translation memory with a file path."""
        self.memory_file = memory_file
        self._memory: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        """Load memory from file if it exists."""
        if self.memory_file.exists():
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    self._memory = json.load(f)
            except Exception:
                self._memory = {}

    def _save(self) -> None:
        """Save memory to file."""
        try:
            self.memory_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self._memory, f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # Best effort saving

    def get(self, text: str) -> Optional[str]:
        """Get translation from memory."""
        with self._lock:
            return self._memory.get(text)

    def set(self, text: str, translation: str) -> None:
        """Store translation in memory."""
        with self._lock:
            self._memory[text] = translation
            self._save()

    def clear(self) -> None:
        """Clear all memory."""
        with self._lock:
            self._memory.clear()
            if self.memory_file.exists():
                try:
                    self.memory_file.unlink()
                except Exception:
                    pass

    def size(self) -> int:
        """Return number of entries in memory."""
        with self._lock:
            return len(self._memory)


class Glossary:
    """User-defined translation glossary."""

    def __init__(self, glossary_file: Optional[Path] = None) -> None:
        """Initialize glossary from file."""
        self._glossary: Dict[str, str] = {}
        if glossary_file and glossary_file.exists():
            self._load(glossary_file)

    def _load(self, glossary_file: Path) -> None:
        """Load glossary from JSON or YAML file."""
        try:
            if glossary_file.suffix.lower() == ".json":
                with open(glossary_file, "r", encoding="utf-8") as f:
                    self._glossary = json.load(f)
            elif glossary_file.suffix.lower() in {".yaml", ".yml"}:
                import yaml

                with open(glossary_file, "r", encoding="utf-8") as f:
                    self._glossary = yaml.safe_load(f) or {}
            else:
                # Try JSON first, then YAML
                try:
                    with open(glossary_file, "r", encoding="utf-8") as f:
                        self._glossary = json.load(f)
                except Exception:
                    import yaml

                    with open(glossary_file, "r", encoding="utf-8") as f:
                        self._glossary = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Warning: Could not load glossary from {glossary_file}: {e}")
            self._glossary = {}

    def apply(self, text: str) -> str:
        """Apply glossary translations to text."""
        if not self._glossary or not text:
            return text

        result = text
        # Sort by key length (longest first) to match longer phrases first
        for key, value in sorted(self._glossary.items(), key=lambda x: len(x[0]), reverse=True):
            if key in result:
                result = result.replace(key, value)
        return result

    def size(self) -> int:
        """Return number of glossary entries."""
        return len(self._glossary)

