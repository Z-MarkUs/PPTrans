"""Small configuration helpers with no hidden model or provider defaults."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from platformdirs import user_cache_path


def load_environment(dotenv_path: Path | None = None) -> bool:
    """Load one explicitly selected dotenv file without replacing exported values."""

    if dotenv_path is None:
        return False
    resolved = dotenv_path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Environment file does not exist: {resolved}")
    return load_dotenv(dotenv_path=resolved, override=False)


def default_memory_path() -> Path:
    """Return the platform-appropriate local cache database path."""

    return user_cache_path("pptrans", "Z-MarkUs") / "translation-memory-v2.sqlite3"


__all__ = ["default_memory_path", "load_environment"]
