from datetime import datetime
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


# --- live snapshot (M2) ----------------------------------------------------
# Energy-Charts gives prices per bidding zone but cross-border flows only per
# *country*. So prices are keyed by zone key; flows live on a country-level
# graph (FlowNode/FlowEdge keyed by ISO-2 code). When ENTSO-E is wired (M6)
# flows become zone-level. All timestamps are UTC.


class PricePoint(BaseModel):
    zone: str  # zone key
    ts: datetime  # UTC
    eur_mwh: float


class FlowNode(BaseModel):
    code: str  # ISO-2 country code, e.g. "FR", "DE", "IT"
    name: str
    centroid: tuple[float, float]  # (lon, lat) — mean of member zones
    zones: list[str]  # member zone keys


class FlowEdge(BaseModel):
    from_zone: str  # FlowNode code (country, demo mode)
    to_zone: str
    ts: datetime  # UTC
    commercial_mw: float | None = None  # signed: + = from_zone -> to_zone
    physical_mw: float | None = None  # signed, same convention
    ntc_mw: float | None = None  # null when FLOW_BASED
    capacity_regime: CapacityRegime


class LiveSnapshot(BaseModel):
    ts: datetime  # UTC — snapshot build time
    source: str  # active data source ("energy_charts" | "entsoe")
    data_ts: datetime | None = None  # UTC — timestamp of the underlying market data
    granularity: dict[str, str]  # {"prices": "bidding_zone", "flows": "country"}
    prices: dict[str, float]  # zone key -> eur_mwh
    nodes: list[FlowNode]  # country-level flow graph nodes
    edges: list[FlowEdge]  # signed cross-border flows
    net_positions: dict[str, float]  # FlowNode code -> MW (+ = net import)


class BorderMetric(BaseModel):
    from_zone: str
    to_zone: str
    spread_eur_mwh: float
    congestion_income_eur: float | None = None
    utilisation: float | None = None  # 0..1, NTC only
