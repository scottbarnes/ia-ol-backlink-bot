from dataclasses import dataclass

BacklinkItemRow = tuple[str, str, int]


@dataclass
class BacklinkItem:
    edition_id: str
    ocaid: str
    status: int = 0
    id: int = 0
