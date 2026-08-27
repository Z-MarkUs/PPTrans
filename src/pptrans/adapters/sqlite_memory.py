"""Small, local SQLite translation memory with strict payload validation."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from pptrans.application.errors import TranslationMemoryError, TranslationValidationError
from pptrans.domain.models import TranslatedSpan
from pptrans.schemas.translation import TranslatedSpanPayload

_SPAN_LIST = TypeAdapter(list[TranslatedSpanPayload])


def _create_private_directories(path: Path) -> None:
    """Create every missing directory with owner-only POSIX permissions."""

    missing: list[Path] = []
    current = path
    while not current.exists():
        missing.append(current)
        parent = current.parent
        if parent == current:
            break
        current = parent

    for directory in reversed(missing):
        # If a previously missing path appears, fail rather than trust a raced directory.
        directory.mkdir(mode=0o700)


def _prepare_database_path(path: Path) -> tuple[str, bool]:
    """Resolve a cache path and privately create new POSIX filesystem objects."""

    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    resolved = expanded.parent.resolve(strict=False) / expanded.name
    if resolved.is_symlink():
        raise OSError("Translation-memory path must not be a symbolic link.")
    if os.name != "posix":
        resolved.parent.mkdir(parents=True, exist_ok=True)
        if resolved.is_symlink():
            raise OSError("Translation-memory path became a symbolic link.")
        return str(resolved), False

    _create_private_directories(resolved.parent)
    try:
        existing = resolved.lstat()
    except FileNotFoundError:
        # Exclusive creation makes an intervening file appearance a fail-closed error.
        descriptor = os.open(
            resolved,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        os.close(descriptor)
    else:
        if not stat.S_ISREG(existing.st_mode):
            raise OSError("Translation-memory path is not a regular file.")
        # Existing mode bits and ACLs may be stricter than 0600; do not rewrite them.

    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError("Translation-memory path is not a regular file.")
    finally:
        os.close(descriptor)

    # mode=rw prevents sqlite3.connect() from recreating a raced-away file with default modes.
    return f"{resolved.as_uri()}?mode=rw", True


class SQLiteTranslationMemory:
    """Persist translations locally without storing slide or file metadata."""

    def __init__(self, path: Path | str) -> None:
        raw_path = str(path)
        is_memory = raw_path == ":memory:"
        try:
            use_uri = False
            if not is_memory:
                raw_path, use_uri = _prepare_database_path(Path(path))
            if use_uri:
                self._connection = sqlite3.connect(raw_path, uri=True)
            else:
                self._connection = sqlite3.connect(raw_path)
            journal_mode = self._connection.execute("PRAGMA journal_mode = DELETE").fetchone()
            if not is_memory and (
                journal_mode is None or str(journal_mode[0]).casefold() != "delete"
            ):
                raise sqlite3.OperationalError("DELETE journal mode was not activated")
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS translations (
                    cache_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._connection.commit()
        except (OSError, sqlite3.Error) as exc:
            connection = getattr(self, "_connection", None)
            if isinstance(connection, sqlite3.Connection):
                connection.close()
            raise TranslationMemoryError(
                "Could not open or initialize the translation-memory database."
            ) from exc

    def get(self, key: str) -> tuple[TranslatedSpan, ...] | None:
        """Return a validated entry, rejecting corrupted local data."""

        try:
            row = self._connection.execute(
                "SELECT payload FROM translations WHERE cache_key = ?", (key,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise TranslationMemoryError("Could not read the translation-memory database.") from exc
        if row is None:
            return None
        try:
            raw = json.loads(str(row[0]))
            payload = _SPAN_LIST.validate_python(raw, strict=True)
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            raise TranslationValidationError("Translation-memory entry is invalid.") from exc
        return tuple(TranslatedSpan(span_id=item.span_id, text=item.text) for item in payload)

    def put(self, key: str, spans: tuple[TranslatedSpan, ...]) -> None:
        """Upsert one compact JSON payload in a transaction."""

        try:
            payload = [
                TranslatedSpanPayload(span_id=item.span_id, text=item.text) for item in spans
            ]
            serialized = json.dumps(
                [item.model_dump(mode="json") for item in payload],
                ensure_ascii=False,
                separators=(",", ":"),
            )
        except (TypeError, UnicodeError, ValidationError) as exc:
            raise TranslationMemoryError("Could not validate translation-memory content.") from exc
        try:
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO translations(cache_key, payload)
                    VALUES (?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        payload = excluded.payload,
                        created_at = CURRENT_TIMESTAMP
                    """,
                    (key, serialized),
                )
        except sqlite3.Error as exc:
            raise TranslationMemoryError(
                "Could not write the translation-memory database."
            ) from exc

    def close(self) -> None:
        """Close the local database."""

        try:
            self._connection.close()
        except sqlite3.Error as exc:
            raise TranslationMemoryError(
                "Could not close the translation-memory database."
            ) from exc

    def __enter__(self) -> SQLiteTranslationMemory:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = ["SQLiteTranslationMemory"]
