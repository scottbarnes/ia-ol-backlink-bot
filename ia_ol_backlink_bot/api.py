from pathlib import Path
from typing import Iterator

from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from passlib.hash import pbkdf2_sha512
from pydantic import BaseModel

from ia_ol_backlink_bot.constants import API_KEYS_FILE, DB
from ia_ol_backlink_bot.database import populate_db
from ia_ol_backlink_bot.models import BacklinkItemRow


# Models need to be centralized because this is the dataclass BacklinkItem all over again.
class POSTedBacklinkItem(BaseModel):
    edition_id: str
    ocaid: str
    status: int = 0
    id: int = 0


class User(BaseModel):
    username: str
    email: str | None = None
    disabled: bool = False


app = FastAPI()
api_key_header = APIKeyHeader(name="access_token", auto_error=False)


def get_api_hashes(filename: str) -> list[str]:
    """
    Read API key hashes from filename.
    """
    hashes = []
    p = Path(filename)
    with p.open(mode="r") as fp:
        while line := fp.readline().rstrip():
            hashes.append(line)

    return hashes


def parse_json_backlink_items(unprocessed_backlinks: list[POSTedBacklinkItem]) -> Iterator[BacklinkItemRow]:
    """
    Parse items from the /add endpoint to create an iterator for use by populate_db().
    """
    for backlink in unprocessed_backlinks:
        yield (backlink.edition_id, backlink.ocaid, backlink.status)


def api_key_hash_in_db(plain_api_key: str, api_keys_file: str = API_KEYS_FILE) -> bool:
    """
    Hash the plain text API key and check if that hash is in the list of API hashes.

    Generate keys with:
        $ openssl rand -hex 32
    The API keys are unsalted because they're random values with around 165 bits of entropy.

    Generate API key hashes with
        >>> from passlib.hash import pbkdf2_sha512
        >>> pbkdf2_sha512.using(salt_size=0, rounds=1).hash("some_api_key")
        '$pbkdf2-sha512$1$$X/qVkwnrvVc9hqrKUoIW2djrqnSI84KLtCCO.h1AobuCLnU8q3MAbRC8cLnakvR9nKT2Ews/SUN8xw5YZ9.xkw'

    Then place them on their own lines, without quotes, in API_KEYS_FILE (see pyproject.toml)
    """
    api_key_hashes = get_api_hashes(api_keys_file)
    hashed_api_key = pbkdf2_sha512.using(salt_size=0, rounds=1).hash(plain_api_key)
    return hashed_api_key in api_key_hashes


def api_key_auth(api_key: str = Security(api_key_header)):
    """
    Check API key validity. If the key is valid, then allow the user to access the resource.
    If not, return the relevant status code and error.
    """
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You must supply API key with access_token in the request header",
        )

    if not api_key_hash_in_db(api_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate API key",
        )


@app.post("/add/", dependencies=[Depends(api_key_auth)])
async def create_item(unprocessed_backlinks: list[POSTedBacklinkItem]):
    """
    Accept an array of JSON objects. Returns an error if validation of list[POSTedBacklinkItem] fails.
    If validation passes, items are inserted into the database for processing, with status = 0.

    Schema:
    [
        {
            "edition_id": "string",
            "ocaid": "string",
            "status": 0,
            "id": 0
        },
        {...},
    ]

    See https://host/docs for OpenAPI docs.
    """
    parsed_input = parse_json_backlink_items(unprocessed_backlinks)
    populate_db(parsed_input, db=DB)

    return {"status": "success"}
