from typing import Literal

from pydantic import BaseModel

CapacityRegime = Literal["NTC", "FLOW_BASED"]


class Zone(BaseModel):
    code: str  # EIC, e.g. "10YFR-RTE------C"
    key: str  # short key, e.g. "FR", "IT-NORD", "SE3"
    name: str
    country: str
    centroid: tuple[float, float]  # (lon, lat)
    tso: list[str] = []
    capacity_regime: CapacityRegime
    region: str | None = None
    has_geometry: bool = True


class Cable(BaseModel):
    name: str
    mw: float | None = None
    tech: str | None = None
    year: str | None = None
    note: str | None = None
    commissioned: bool = True


class Interconnector(BaseModel):
    from_zone: str
    to_zone: str
    capacity_regime: CapacityRegime
    gb_decoupled: bool = False
    cables: list[Cable] = []
