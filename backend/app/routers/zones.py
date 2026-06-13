from fastapi import APIRouter

from ..domain.zones import load_zones, load_zones_geojson
from ..models import Zone

router = APIRouter(prefix="/api", tags=["zones"])


@router.get("/zones", response_model=list[Zone])
def get_zones() -> list[Zone]:
    return list(load_zones())


@router.get("/zones.geojson")
def get_zones_geojson() -> dict:
    return load_zones_geojson()
