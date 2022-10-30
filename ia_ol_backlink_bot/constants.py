from pathlib import Path
from olclient.openlibrary import OpenLibrary

import toml

SETTINGS: dict[str, str] = toml.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["tool"]["backlink"]
