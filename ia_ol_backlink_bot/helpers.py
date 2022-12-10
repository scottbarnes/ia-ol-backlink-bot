import csv
from pathlib import Path
from typing import Iterator

from rich.progress import track

from ia_ol_backlink_bot.models import BacklinkItem, BacklinkItemRow


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


def parse_tsv(in_tsv: str) -> Iterator[BacklinkItemRow]:
    """
    Read TSV file in_tsv return an iterator for db.executemany().

    This returns an iterator of tuples, each with three field values of BacklinkItem because
    db.executmany() expects a tuple of items that correspond to each database value that's being
    inserted. Here, we are inserting three: the OL edition, the OCAID, and the item's status in terms
    of whether it's been processed.

    TODO: this should use attrs or Pydantic for input validation.
    """
    parsed_data = Path(in_tsv)
    with parsed_data.open(mode="r") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in track(reader, description="Adding items to database..."):
            backlink_item = BacklinkItem(edition_id=row[0], ocaid=row[1])

            yield (backlink_item.edition_id, backlink_item.ocaid, backlink_item.status)
