"""
Some explanation of this.
Status values:
    0: needs updating
    1: this script updated it
    2: something else updated it.
"""
import csv
import os
import sqlite3
import time
from collections import namedtuple
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

# import requests
from constants import SETTINGS
from database import Database
from olclient.openlibrary import OpenLibrary
from rich.progress import track

# Set in .env and load into the env via the shell, or docker-compose if using that.
BOT_USER = os.environ["bot_user"]
BOT_PASSWORD = os.environ["bot_password"]


@dataclass
class BacklinkItem:
    edition_id: str
    ocaid: str
    status: int = 0
    id: int = 0


def can_add_ocaid(edition: Any) -> bool:
    """It's only okay to add an OCAID if no OCAID already exists."""
    if not hasattr(edition, "ocaid"):
        return True

    return edition.ocaid == ""


def can_add_source_record(edition: Any) -> bool:
    """It's only okay to add a source record if there isn't one there already."""
    if not hasattr(edition, "source_records"):
        return True

    return not any(item for item in edition.source_records if "ia:" in item)


def get_ol_connection(user: str, password: str, base_url: str = "https://openlibrary.org") -> OpenLibrary:
    C = namedtuple("Credentials", ["username", "password"])
    credentials = C(user, password)
    return OpenLibrary(base_url=base_url, credentials=credentials)


# This should return an Edition; how can that be done?
def get_edition(id: str, ol: OpenLibrary) -> Any:
    """Get an open library Edition."""
    return ol.Edition.get(id)


def populate_db(in_tsv: str, db: Database) -> None:
    """
    Read in_tsv and populate db.
    TODO: this should use attrs or Pydantic for input validation.
    """

    def get_backlink_items(in_tsv) -> Iterator[tuple[str, str, int]]:
        parsed_data = Path(in_tsv)
        with parsed_data.open(mode="r") as f:
            reader = csv.reader(f, delimiter="\t")
            for row in track(reader, description="Adding items to database..."):
                backlink_item = BacklinkItem(edition_id=row[0], ocaid=row[1])

                yield (backlink_item.edition_id, backlink_item.ocaid, backlink_item.status)

    # Create the DB if necessary, or use the existing one.
    try:
        db.execute(
            "CREATE TABLE link_items (rowid INTEGER PRIMARY KEY, edition_id TEXT, \
                ocaid TEXT, status INTEGER)"
        )

        db.executemany(
            "INSERT INTO link_items (edition_id, ocaid, status) VALUES (?, ?, ?)", get_backlink_items(in_tsv=in_tsv)
        )
        db.execute("CREATE INDEX idx_status ON link_items(status)")
        db.execute("CREATE INDEX idx ON link_items(rowid)")
        db.commit()

    except sqlite3.OperationalError:
        db.executemany(
            "INSERT INTO link_items (edition_id, ocaid, status) VALUES (?, ?, ?)", get_backlink_items(in_tsv=in_tsv)
        )
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
    """

    db.execute(f"UPDATE link_items SET status = {status} WHERE rowid = {rowid}")
    db.commit()


def update_backlink_items(backlink_items: list[Any], ol: OpenLibrary, db: Database) -> None:
    """
    These should be Editions.
    Go through each backlink_item and update it, both on Open Library, and in the local DB.
    """
    for backlink_item in backlink_items:
        _id, edition_id, ocaid, status = backlink_item
        item = BacklinkItem(edition_id, ocaid, status, _id)
        edition = get_edition(item.edition_id, ol)
        print(f"Updating {edition.title} ({edition.olid}) -> ocaid: {item.ocaid}")

        if can_add_ocaid(edition):
            edition.ocaid = item.ocaid
        else:
            update_backlink_item_status(status=2, rowid=item.id, db=db)
            continue

        # This and can_add_ocaid should maybe just be refactored into add_X, and it can return an error/None or something.
        if can_add_source_record(edition):
            if hasattr(edition, "source_records"):
                edition.source_records.append(f"ia:{item.ocaid}")
            else:
                edition.source_records = [f"ia:{item.ocaid}"]

        edition.save(comment="Linking back to Internet Archive.")
        update_backlink_item_status(status=1, rowid=item.id, db=db)

        time.sleep(.8)


def get_input_filename(watch_dir: str) -> str:
    """Check {watch_dir} for any files ending in *.tsv. Returns name of the 'first' one as a string."""
    input_files = Path(watch_dir).glob("*.tsv")
    try:
        filename = str(next(input_files))
    except StopIteration:
        filename = ""

    return filename


def delete_file(filename: str) -> None:
    file = Path(filename)
    if file.is_file():
        file.unlink()


def add_new_items_to_db(watch_dir: str, db: Database) -> bool:
    """
    Check for new items on disk, and if there are, populate DB with them.
    The bool return value is so we know whether to query the "status" key for new items in need of updating on OL.
    """
    input_file = get_input_filename(watch_dir)
    if input_file == "":
        return False

    populate_db(input_file, db)
    delete_file(input_file)

    return True


def db_initalized(db: Database) -> bool:
    """Return True if the DB is initialized--i.e. return True if populate_db() has run."""
    table_count = db.query("SELECT name FROM sqlite_schema WHERE type='table' AND name='link_items'")
    return len(table_count) > 0


def main(watch_dir: str, ol: OpenLibrary, db: Database) -> None:
    """
    Monitor {watch_dir} looking for *.tsv files. If it finds them:
        - populate the SQLite DB with their contents
        - query the SQlite DB looking for items with status == 0
        - go to Open Library and try to update any items with status == 0
        - update the SQLite DB with status == 1 for a successful update, and 2 if t was already updated.
    """
    # The first time this runs, the DB is not yet initialized and doesn't have the link_items table,
    # therefore only try to add existing items if the DB is already initialized (via adding from a file).
    if db_initalized(db):
        print("Checking the database for existing backlink items not yet added to Open Library.")
        existing_items = get_backitems_needing_update(db)

        if existing_items:
            print("Found existing items to update. Updating them now.")
            update_backlink_items(existing_items, ol, db)

    while True:

        new_backlink_items = []
        items_added_to_db = add_new_items_to_db(watch_dir, db)

        if items_added_to_db:
            print("Looking for new backlink items.")
            new_backlink_items = get_backitems_needing_update(db)

        if new_backlink_items:
            print("Unprocessed items found. Updating.")
            update_backlink_items(new_backlink_items, ol, db)

        time.sleep(10)


if __name__ == "__main__":
    watch_dir = SETTINGS["watch_dir"]
    d = Path(watch_dir)
    if not d.exists():
        d.mkdir()

    db = Database(name=SETTINGS["sqlite"])

    # ol = get_ol_connection(user=BOT_USER, password=BOT_PASSWORD, base_url="https://openlibrary.org")
    ol = get_ol_connection(user=BOT_USER, password=BOT_PASSWORD, base_url="http://192.168.0.11:8080")
    main(watch_dir, ol, db)
