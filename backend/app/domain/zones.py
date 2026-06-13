import json
from functools import lru_cache

from ..config import settings
from ..models import Zone


@lru_cache(maxsize=1)
def load_zones() -> tuple[Zone, ...]:
    raw = json.loads((settings.data_dir / "zones.json").read_text(encoding="utf-8"))
    return tuple(Zone(**z) for z in raw["zones"])


@lru_cache(maxsize=1)
def load_zones_geojson() -> dict:
    return json.loads((settings.data_dir / "zones.geojson").read_text(encoding="utf-8"))


def zone_by_key(key: str) -> Zone | None:
    return next((z for z in load_zones() if z.key == key), None)
