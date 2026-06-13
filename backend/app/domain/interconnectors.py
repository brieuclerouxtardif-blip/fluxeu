import json
from functools import lru_cache

from ..config import settings
from ..models import Interconnector


@lru_cache(maxsize=1)
def load_interconnectors() -> tuple[Interconnector, ...]:
    raw = json.loads(
        (settings.data_dir / "interconnectors.json").read_text(encoding="utf-8")
    )
    return tuple(Interconnector(**b) for b in raw["borders"])
