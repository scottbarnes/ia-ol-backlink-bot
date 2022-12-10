import sqlite3
from collections.abc import Iterable, Iterator
from typing import Any

from ia_ol_backlink_bot.helpers import (delete_file, get_input_filename,
                                        parse_tsv)
from ia_ol_backlink_bot.models import BacklinkItemRow


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


def populate_db(parsed_input: Iterator[BacklinkItemRow], db: Database) -> None:
    """
    Populate the DB with items to process. Once in the database, the functions called
    from main() will process them.
    """
    # Create the DB if necessary, or use the existing one.
    try:
        db.execute(
            "CREATE TABLE link_items (rowid INTEGER PRIMARY KEY, edition_id TEXT, \
                ocaid TEXT, status INTEGER)"
        )

        db.executemany("INSERT INTO link_items (edition_id, ocaid, status) VALUES (?, ?, ?)", parsed_input)
        db.execute("CREATE INDEX idx_status ON link_items(status)")
        db.execute("CREATE INDEX idx ON link_items(rowid)")
        db.commit()

    except sqlite3.OperationalError:
        db.executemany("INSERT INTO link_items (edition_id, ocaid, status) VALUES (?, ?, ?)", parsed_input)
        db.commit()


def get_backitems_needing_update(db: Database) -> list[Any]:
    """Get all items where status == 0, which signifies an update should be attempted on Open Library."""
    return db.query("""SELECT * FROM link_items WHERE status = 0""")


def update_backlink_item_status(status: int, rowid: int, db: Database) -> None:
    """
    After processing an Edition, record the status in the database.
        0: unprocessed
        1: added by this script
        2: added elsewhere (i.e. the parsed TSV said the Edition needed linking, but something else updated it.)
        3: there was an error processing this entry.
    """

    db.execute(f"UPDATE link_items SET status = {status} WHERE rowid = {rowid}")
    db.commit()


def add_new_items_from_watch_dir(watch_dir: str, db: Database) -> bool:
    """
    Check for new items on disk, and if there are, populate DB with them.
    The bool return value is so we know whether to query the "status" key for new items in need of updating on OL.
    """
    input_file = get_input_filename(watch_dir)
    if input_file == "":
        return False

    parsed_tsv = parse_tsv(input_file)
    populate_db(parsed_tsv, db)
    delete_file(input_file)

    return True


def db_initalized(db: Database) -> bool:
    """Return True if the DB is initialized--i.e. return True if populate_db() has run."""
    table_count = db.query("SELECT name FROM sqlite_schema WHERE type='table' AND name='link_items'")

    return len(table_count) > 0
