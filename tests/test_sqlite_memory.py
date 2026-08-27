"""SQLite translation-memory persistence and corruption tests."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
from contextlib import closing
from pathlib import Path

import pytest

from pptrans.adapters.sqlite_memory import SQLiteTranslationMemory
from pptrans.application.errors import TranslationMemoryError, TranslationValidationError
from pptrans.domain.models import TranslatedSpan


def _spans(text: str = "你好世界 🌏") -> tuple[TranslatedSpan, ...]:
    return (
        TranslatedSpan(span_id="span-一", text=text),
        TranslatedSpan(span_id="span-2", text="مرحبا بالعالم"),
    )


def test_memory_reports_miss_then_round_trips_unicode() -> None:
    with SQLiteTranslationMemory(":memory:") as memory:
        assert memory.get("missing") is None

        memory.put("deck:語言:🔑", _spans())

        assert memory.get("deck:語言:🔑") == _spans()


def test_memory_upsert_replaces_one_key_without_touching_another() -> None:
    with SQLiteTranslationMemory(":memory:") as memory:
        memory.put("first", _spans("old"))
        memory.put("second", _spans("stable"))

        memory.put("first", _spans("new"))

        assert memory.get("first") == _spans("new")
        assert memory.get("second") == _spans("stable")


def test_file_memory_creates_parent_and_persists_after_reopen(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "translation-memory.sqlite3"

    with SQLiteTranslationMemory(path) as memory:
        memory.put("persistent", _spans())

    assert path.is_file()
    with SQLiteTranslationMemory(path) as reopened:
        assert reopened.get("persistent") == _spans()


def test_memory_rejects_a_symlink_leaf_without_touching_its_target(tmp_path: Path) -> None:
    target = tmp_path / "target.sqlite3"
    link = tmp_path / "selected.sqlite3"
    target.write_bytes(b"preserve target")
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symbolic links unavailable on this filesystem: {exc}")

    with pytest.raises(TranslationMemoryError, match="Could not open"):
        SQLiteTranslationMemory(link)

    assert target.read_bytes() == b"preserve target"


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits are unavailable on Windows")
def test_new_file_memory_uses_private_posix_permissions(tmp_path: Path) -> None:
    existing_parent = tmp_path / "existing"
    existing_parent.mkdir(mode=0o750)
    existing_parent.chmod(0o750)
    first_created_parent = existing_parent / "private"
    second_created_parent = first_created_parent / "nested"
    path = second_created_parent / "translation-memory.sqlite3"

    with SQLiteTranslationMemory(path):
        pass

    assert stat.S_IMODE(existing_parent.stat().st_mode) == 0o750
    assert stat.S_IMODE(first_created_parent.stat().st_mode) & 0o077 == 0
    assert stat.S_IMODE(second_created_parent.stat().st_mode) & 0o077 == 0
    assert stat.S_IMODE(path.stat().st_mode) & 0o177 == 0


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits are unavailable on Windows")
def test_existing_database_permissions_are_not_relaxed(tmp_path: Path) -> None:
    path = tmp_path / "memory.sqlite3"
    with SQLiteTranslationMemory(path):
        pass
    path.chmod(0o400)

    try:
        with SQLiteTranslationMemory(path):
            pass
    except TranslationMemoryError:
        # Some POSIX environments refuse even the read-only reopen during initialization.
        pass

    assert stat.S_IMODE(path.stat().st_mode) == 0o400


def test_file_memory_converts_persistent_wal_to_delete_without_losing_data(
    tmp_path: Path,
) -> None:
    path = tmp_path / "memory.sqlite3"
    with closing(sqlite3.connect(path)) as connection:
        selected_mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()
        connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sentinel VALUES ('preserved')")
        connection.commit()

    assert selected_mode == ("wal",)

    with SQLiteTranslationMemory(path):
        pass

    with closing(sqlite3.connect(path)) as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()
        sentinel = connection.execute("SELECT value FROM sentinel").fetchone()

    assert journal_mode == ("delete",)
    assert sentinel == ("preserved",)
    assert not Path(f"{path}-journal").exists()
    assert not Path(f"{path}-shm").exists()
    assert not Path(f"{path}-wal").exists()


def test_memory_uses_bound_parameters_for_untrusted_cache_keys() -> None:
    hostile_key = "key'); DROP TABLE translations; --"

    with SQLiteTranslationMemory(":memory:") as memory:
        memory.put(hostile_key, _spans())

        assert memory.get(hostile_key) == _spans()
        memory.put("still-present", _spans("safe"))
        assert memory.get("still-present") == _spans("safe")


def test_persisted_json_is_compact_and_unicode_is_not_ascii_escaped(tmp_path: Path) -> None:
    path = tmp_path / "memory.sqlite3"
    with SQLiteTranslationMemory(path) as memory:
        memory.put("unicode", _spans())

    with sqlite3.connect(path) as connection:
        raw = connection.execute(
            "SELECT payload FROM translations WHERE cache_key = ?", ("unicode",)
        ).fetchone()

    assert raw is not None
    serialized = raw[0]
    assert "你好世界" in serialized
    assert "\\u4f60" not in serialized
    assert ": " not in serialized
    assert json.loads(serialized)[0] == {"span_id": "span-一", "text": "你好世界 🌏"}


@pytest.mark.parametrize(
    "corrupt_payload",
    [
        "not-json",
        "null",
        "{}",
        '[{"span_id":"span-1"}]',
        '[{"span_id":"span-1","text":7}]',
        '[{"span_id":"span-1","text":"ok","extra":true}]',
        '[{"span_id":"","text":"ok"}]',
    ],
    ids=[
        "invalid-json",
        "null-root",
        "object-root",
        "missing-text",
        "wrong-text-type",
        "extra-field",
        "empty-id",
    ],
)
def test_memory_rejects_corrupted_rows(
    tmp_path: Path,
    corrupt_payload: str,
) -> None:
    path = tmp_path / "memory.sqlite3"
    memory = SQLiteTranslationMemory(path)
    memory.put("corrupt", _spans("original"))
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE translations SET payload = ? WHERE cache_key = ?",
            (corrupt_payload, "corrupt"),
        )
        connection.commit()

    try:
        with pytest.raises(TranslationValidationError, match="entry is invalid") as raised:
            memory.get("corrupt")
    finally:
        memory.close()

    assert raised.value.__cause__ is not None


def test_failed_put_validation_does_not_replace_an_existing_entry() -> None:
    with SQLiteTranslationMemory(":memory:") as memory:
        memory.put("key", _spans("valid"))

        with pytest.raises(TranslationMemoryError, match="Could not validate"):
            memory.put("key", (TranslatedSpan(span_id="", text="invalid"),))

        assert memory.get("key") == _spans("valid")


def test_memory_maps_oversized_payload_validation_without_echoing_content() -> None:
    sensitive = "PRIVATE-MARKER-" + "x" * 100_000

    with (
        SQLiteTranslationMemory(":memory:") as memory,
        pytest.raises(TranslationMemoryError, match="Could not validate") as raised,
    ):
        memory.put("key", (TranslatedSpan(span_id="span-1", text=sensitive),))

    assert "PRIVATE-MARKER" not in str(raised.value)


def test_context_manager_closes_the_connection() -> None:
    memory = SQLiteTranslationMemory(":memory:")

    with memory:
        memory.put("key", _spans())

    with pytest.raises(TranslationMemoryError, match="Could not read"):
        memory.get("key")
