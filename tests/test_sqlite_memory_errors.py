"""Failure wrapping tests for the local SQLite translation memory."""

from __future__ import annotations

import sqlite3

import pytest

from pptrans.adapters import sqlite_memory
from pptrans.adapters.sqlite_memory import SQLiteTranslationMemory
from pptrans.application.errors import TranslationMemoryError
from pptrans.domain.models import TranslatedSpan


class _FailingInitConnection(sqlite3.Connection):
    close_calls = 0

    def execute(self, *_args: object, **_kwargs: object) -> object:
        raise sqlite3.OperationalError("initialization failed")

    def close(self) -> None:
        self.close_calls += 1
        super().close()


def test_initialization_failure_closes_an_opened_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native_connect = sqlite3.connect
    created: list[_FailingInitConnection] = []

    def failing_connect(_path: str) -> _FailingInitConnection:
        connection = native_connect(":memory:", factory=_FailingInitConnection)
        created.append(connection)
        return connection

    monkeypatch.setattr(sqlite_memory.sqlite3, "connect", failing_connect)

    with pytest.raises(TranslationMemoryError, match="open or initialize") as raised:
        SQLiteTranslationMemory(":memory:")

    assert created[0].close_calls == 1
    assert isinstance(raised.value.__cause__, sqlite3.OperationalError)


def test_put_wraps_closed_database_failure() -> None:
    memory = SQLiteTranslationMemory(":memory:")
    memory._connection.close()

    with pytest.raises(TranslationMemoryError, match="Could not write") as raised:
        memory.put("key", (TranslatedSpan(span_id="span-1", text="translated"),))

    assert isinstance(raised.value.__cause__, sqlite3.Error)


class _FailingCloseConnection:
    @staticmethod
    def close() -> None:
        raise sqlite3.OperationalError("close failed")


def test_close_wraps_database_failure() -> None:
    memory = object.__new__(SQLiteTranslationMemory)
    memory._connection = _FailingCloseConnection()  # type: ignore[assignment]

    with pytest.raises(TranslationMemoryError, match="Could not close") as raised:
        memory.close()

    assert isinstance(raised.value.__cause__, sqlite3.OperationalError)
