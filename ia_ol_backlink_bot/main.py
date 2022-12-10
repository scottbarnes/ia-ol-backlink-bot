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
from pathlib import Path
from threading import Thread
from typing import Any, Iterator, NoReturn

import uvicorn
# uvicorn reads this.
from api import app
from olclient.openlibrary import OpenLibrary
from requests.exceptions import HTTPError

# import requests
from ia_ol_backlink_bot.constants import DB, DB_NAME, SETTINGS
from ia_ol_backlink_bot.database import (Database,
                                         add_new_items_from_watch_dir,
                                         db_initalized,
                                         get_backitems_needing_update,
                                         update_backlink_item_status)
from ia_ol_backlink_bot.models import BacklinkItem, BacklinkItemRow

# Set in .env and load into the env via the shell, or docker-compose if using that.
BOT_USER = os.environ["bot_user"]
BOT_PASSWORD = os.environ["bot_password"]


def can_add_ocaid(edition: Any) -> bool:
    """It's only okay to add an OCAID if no OCAID already exists."""
    if not hasattr(edition, "ocaid"):
        return True

    return edition.ocaid == ""


def get_ol_connection(user: str, password: str, base_url: str = "https://openlibrary.org") -> OpenLibrary:
    C = namedtuple("Credentials", ["username", "password"])
    credentials = C(user, password)
    return OpenLibrary(base_url=base_url, credentials=credentials)


# This should return an Edition; how can that be done?
def get_edition(id: str, ol: OpenLibrary) -> Any:
    """Get an open library Edition."""
    return ol.Edition.get(id)


def update_backlink_items(backlink_items: list[Any], ol: OpenLibrary, db: Database) -> None:
    """
    These should be Editions.
    Go through each backlink_item and update it, both on Open Library, and in the local DB.
    """
    for backlink_item in backlink_items:
        _id, edition_id, ocaid, status = backlink_item
        item = BacklinkItem(edition_id, ocaid, status, _id)

        try:
            edition = get_edition(item.edition_id, ol)
        except HTTPError:
            update_backlink_item_status(status=3, rowid=item.id, db=db)
            continue

        print(f"Updating {edition.title} ({edition.olid}) -> ocaid: {item.ocaid}")

        if can_add_ocaid(edition):
            edition.ocaid = item.ocaid
        else:
            update_backlink_item_status(status=2, rowid=item.id, db=db)
            continue

        if hasattr(edition, "source_records") and f"ia:{item.ocaid}" not in edition.source_records:
            edition.source_records.append(f"ia:{item.ocaid}")
        else:
            edition.source_records = [f"ia:{item.ocaid}"]

        edition.save(comment="Linking back to Internet Archive.")
        update_backlink_item_status(status=1, rowid=item.id, db=db)

        time.sleep(float(SETTINGS["ocaid_add_delay"]))


class WatchAndProcessItems(Thread):
    """
    Continually try to add items from the database.

    Also, monitor {watch_dir} looking for *.tsv files. If it finds them:
        - populate the SQLite DB with their contents
        - query the SQlite DB looking for items with status == 0
        - go to Open Library and try to update any items with status == 0
        - update the SQLite DB with status == 1 for a successful update, and 2 if t was already updated.

    Note: this is only its own class to inherit from Thread.
    """

    def __init__(self, watch_dir: str, ol: OpenLibrary, db_name: str) -> None:
        Thread.__init__(self)
        self.watch_dir = watch_dir
        self.ol = ol
        self.db_name = db_name

    def run(self):
        # The first time IA <-> OL linker script runs, the DB is not yet initialized and doesn't have the
        # link_items table, therefore only try to add existing items on-start if the DB is already
        # initialized, and therefore might have unprocessed items that should be processed on-start.

        db = Database(name=self.db_name)

        if db_initalized(db):
            print("Checking the database for existing backlink items not yet added to Open Library.")
            existing_items = get_backitems_needing_update(db)

            if existing_items:
                print("Found existing items to update. Updating them now.")
                update_backlink_items(existing_items, self.ol, db)

        # Enter watch-mode and continually monitor the watch dir for new files/entries.
        while True:

            new_backlink_items = []
            add_new_items_from_watch_dir(self.watch_dir, db)

            # if has_added_new_items:
            #     print("Looking for new backlink items.")
            print("Looking for new backlink items.")
            new_backlink_items = get_backitems_needing_update(db)

            if new_backlink_items:
                print("Unprocessed items found. Updating.")
                update_backlink_items(new_backlink_items, self.ol, db)

            time.sleep(10)


def start() -> None:
    """
    Main entry point.

    Create watch dir if needed, get on openlibrary-client connection, monitor the watch dir,
    repeatedly try to add any new or existing link items, and start up the API.
    """
    watch_dir = SETTINGS["watch_dir"]
    d = Path(watch_dir)
    if not d.exists():
        d.mkdir()

    # ol = get_ol_connection(user=BOT_USER, password=BOT_PASSWORD, base_url="https://openlibrary.org")
    ol = get_ol_connection(user=BOT_USER, password=BOT_PASSWORD, base_url="http://192.168.0.11:8080")
    watch_and_process_items = WatchAndProcessItems(watch_dir=watch_dir, ol=ol, db_name=DB_NAME)

    # Monitor the watch dir and repeatdly try to add items on a thread so as not to block uvicorn.
    watch_and_process_items.start()

    # Load the API from api.py.
    uvicorn.run("ia_ol_backlink_bot.main:app", host="0.0.0.0", port=5000, reload=True)
