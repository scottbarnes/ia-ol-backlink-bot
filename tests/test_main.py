import os
from dataclasses import dataclass
from pathlib import Path, PosixPath
from typing import Iterable

import pytest
from olclient.openlibrary import OpenLibrary

# from ia_ol_backlink_bot.constants import SETTINGS
from ia_ol_backlink_bot.database import Database
from ia_ol_backlink_bot.main import (can_add_ocaid, can_add_source_record,
                                     delete_file, get_backitems_needing_update,
                                     get_edition, get_input_filename,
                                     get_ol_connection, main, populate_db,
                                     update_backlink_items)

USER = os.environ["test_user"]
PASSWORD = os.environ["test_password"]
SEED_DATA = "./tests/seed_data.tsv"


@dataclass
class FakeEdition:
    title: str = "Blob"


@pytest.fixture(scope="session")
def get_ol() -> Iterable[OpenLibrary]:
    ol = get_ol_connection(user=USER, password=PASSWORD, base_url="http://localhost:8080")
    yield ol


@pytest.fixture(scope="session")
def get_db(get_ol, tmp_path_factory) -> Iterable[Database]:
    d = tmp_path_factory.mktemp("data")
    sqlite_db = d / "sqlite_db"
    db = Database(name=sqlite_db)
    ol = get_ol

    # Messing with the development DB, but oh well
    alice = get_edition("OL13517105M", ol)
    gulliver = get_edition("OL24173003M", ol)
    odyssey = get_edition("OL24755423M", ol)
    books = [alice, gulliver, odyssey]

    yield db

    for book in books:
        book.save(comment="reversion to original copy.")


@pytest.fixture
def get_new_db(get_ol, tmp_path) -> Iterable[Database]:
    d = tmp_path / "data"
    d.mkdir()
    sqlite_db = d / "sqlite_db"
    db = Database(name=sqlite_db)
    ol = get_ol

    # Messing with the development DB, but oh well
    alice = get_edition("OL13517105M", ol)
    gulliver = get_edition("OL24173003M", ol)
    odyssey = get_edition("OL24755423M", ol)
    books = [alice, gulliver, odyssey]

    yield db

    for book in books:
        book.save(comment="reversion to original copy.")


def test_can_add_ocaid() -> None:
    """can_add_ocaid should only be True when there's no ocaid or it's an empty string."""
    edition_without_ocaid = FakeEdition()
    assert can_add_ocaid(edition_without_ocaid) is True

    edition_with_null_string_ocaid = FakeEdition()
    edition_with_null_string_ocaid.ocaid = ""
    assert can_add_ocaid(edition_with_null_string_ocaid) is True

    edition_with_ocaid = FakeEdition()
    edition_with_ocaid.ocaid = "existing_ocaid"
    assert can_add_ocaid(edition_with_ocaid) is False


def test_can_get_source_record() -> None:
    """can_add_source_record should only be True when there's no source_records or there's no ia entry."""
    edition_without_source_records = FakeEdition()
    assert can_add_source_record(edition_without_source_records) is True

    edition_without_ia_source_record = FakeEdition()
    edition_without_ia_source_record.source_records = ["blob:what"]
    assert can_add_source_record(edition_without_ia_source_record) is True

    edition_with_ia_source_record = FakeEdition()
    edition_with_ia_source_record.source_records = ["ia:existing_record"]
    assert can_add_source_record(edition_with_ia_source_record) is False


def test_get_edition(get_ol) -> None:
    ol = get_ol
    expected_title = "Alice im Spiegelland"
    edition = get_edition("OL13517105M", ol=ol)
    assert edition.title == expected_title


def test_populate_db(get_db: Database) -> None:
    db = get_db
    expected = [
        (1, "OL13517105M", "aliceimspiegella00carrrich", 0),
        (2, "OL24173003M", "cu31924013200609", 0),
        (3, "OL24755423M", "odysseybookiv00home", 0),
    ]

    populate_db(SEED_DATA, db)
    assert db.query("""SELECT * FROM link_items""") == expected


def test_update_backlink_items(get_ol: OpenLibrary, get_db: Database) -> None:
    db = get_db
    ol = get_ol
    expected = [
        (1, "OL13517105M", "aliceimspiegella00carrrich", 1),
        (2, "OL24173003M", "cu31924013200609", 1),
        (3, "OL24755423M", "odysseybookiv00home", 2),
    ]

    if unprocessed_items := get_backitems_needing_update(db):
        update_backlink_items(backlink_items=unprocessed_items, ol=ol, db=db)

    alice = get_edition("OL13517105M", ol)
    gulliver = get_edition("OL24173003M", ol)
    odyssey = get_edition("OL24755423M", ol)

    assert alice.ocaid == "aliceimspiegella00carrrich"
    assert alice.source_records == ["ia:aliceimspiegella00carrrich"]

    assert gulliver.ocaid == "cu31924013200609"
    assert gulliver.source_records == ["blob:what", "ia:cu31924013200609"]

    assert odyssey.ocaid == "odysseybookiv00home"
    assert odyssey.source_records == ["ia:odysseybookiv00home"]

    assert db.query("SELECT * FROM link_items") == expected


def test_get_input_filename(tmp_path) -> None:
    """
    Populate a directory with two test files, and return them one at a time, deleting each one in turn.
    """
    input_files: PosixPath = tmp_path / "input_files"
    input_files.mkdir()
    first = input_files / "first.tsv"
    second = input_files / "second.tsv"

    first.write_text("OL13517105M\taliceimspiegella00carrrich")
    second.write_text("OL24173003M\tcu31924013200609")

    input_file = get_input_filename(str(input_files))
    assert input_file.split("/")[-1] == second.name

    delete_file(str(second))
    input_file = get_input_filename(str(input_files))
    assert input_file.split("/")[-1] == first.name

    delete_file(str(first))
    input_file = get_input_filename(str(input_files))
    assert input_file == ""


# Because this uses 'live' local development data, this test fails if other tests run
# because they change the local development data until all tests are done.

# def test_main(tmp_path, get_ol: OpenLibrary, get_new_db: Database) -> None:
#     """Test it all."""
#     db = get_new_db
#     ol = get_ol
#     expected_first = [
#         (1, "OL13517105M", "aliceimspiegella00carrrich", 1),
#     ]
#     expected_second = [
#         (1, "OL13517105M", "aliceimspiegella00carrrich", 1),
#         (2, "OL24173003M", "cu31924013200609", 1),
#     ]
#     expected_third = [
#         (1, "OL13517105M", "aliceimspiegella00carrrich", 1),
#         (2, "OL24173003M", "cu31924013200609", 1),
#         (3, "OL24755423M", "odysseybookiv00home", 2),
#     ]

#     watch_dir: PosixPath = tmp_path / "watch_dir"
#     watch_dir.mkdir()
#     first = watch_dir / "first.tsv"
#     second = watch_dir / "second.tsv"
#     third = watch_dir / "third.tsv"

#     first.write_text("OL13517105M\taliceimspiegella00carrrich")
#     main(watch_dir=str(watch_dir), ol=ol, db=db)
#     assert db.query("SELECT * FROM link_items") == expected_first

#     second.write_text("OL24173003M\tcu31924013200609")
#     main(watch_dir=str(watch_dir), ol=ol, db=db)
#     assert db.query("SELECT * FROM link_items") == expected_second

#     third.write_text("OL24755423M\todysseybookiv00home")
#     main(watch_dir=str(watch_dir), ol=ol, db=db)
#     assert db.query("SELECT * FROM link_items") == expected_third
