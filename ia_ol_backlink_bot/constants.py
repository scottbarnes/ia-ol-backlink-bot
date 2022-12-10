from pathlib import Path

import toml
from database import Database
from olclient.openlibrary import OpenLibrary

SETTINGS: dict[str, str] = toml.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["tool"]["backlink"]
API_KEYS_FILE = SETTINGS["api_key_file"]
DB_NAME = "files/" + SETTINGS["sqlite"]
DB = Database(name=DB_NAME)
