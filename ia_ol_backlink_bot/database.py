import sqlite3
from collections.abc import Iterable
from typing import Any


class Database:
    """
    A class for more easily interacting with the database.
    Adapted from https://stackoverflow.com/a/38078544.
    """

    def __init__(self, name: str):

        self._conn = sqlite3.connect(name, timeout=60)
        self._cursor = self._conn.cursor()

    def __enter__(self):  # type: ignore[no-untyped-def]
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):  # type: ignore[no-untyped-def]
        self.close()

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    @property
    def cursor(self) -> sqlite3.Cursor:
        return self._cursor

    def commit(self) -> None:
        self.connection.commit()

    def close(self, commit: bool = True) -> None:
        if commit:
            self.commit()
        self.connection.close()

    def execute(self, sql: str, params: tuple[str] | None = None) -> None:
        self.cursor.execute(sql, params or ())

    def executemany(self, sql: str, params: tuple[str] | Iterable[str] | None = None) -> None:
        self.cursor.executemany(sql, params or ())

    def fetchall(self) -> list[Any]:
        return self.cursor.fetchall()

    def fetchone(self) -> Any:
        return self.cursor.fetchone()

    def query(self, sql: str, params: tuple[str] | None = None) -> list[Any]:
        self.cursor.execute(sql, params or ())
        return self.fetchall()

    def lastrowid(self) -> int | None:
        return self.cursor.lastrowid
