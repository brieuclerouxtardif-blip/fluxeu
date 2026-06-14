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


# --- history / scrubber (M4) ----------------------------------------------
# A 48 h window of frames, one per market timestamp. Built from the SAME sweep
# as the live snapshot (Energy-Charts returns a whole range per call), so it
# costs no extra API calls. Prices step per MTU (never interpolated).


class HistoryFrame(BaseModel):
    ts: datetime  # UTC — market time of this frame
    prices: dict[str, float]  # zone key -> eur_mwh (stepped)
    net_positions: dict[str, float]  # FlowNode code -> MW (+ = net import)
    edges: list[FlowEdge]  # signed cross-border flows at this instant


class SnapshotHistory(BaseModel):
    ts: datetime  # UTC — build time
    source: str
    granularity: dict[str, str]
    nodes: list[FlowNode]  # static across frames — sent once
    start: datetime  # UTC — window start
    end: datetime  # UTC — window end (≈ now)
    frames: list[HistoryFrame]  # ascending by ts; ~hourly over ~48 h


# --- metrics (M5) ----------------------------------------------------------
# Congestion is read off the live snapshot + 48 h history in memory (no DB):
# spreads are ZONE-level (richer — captures internal NO/SE/IT splits too),
# while congestion rent needs a flow, which only exists on the COUNTRY graph,
# so it is filled only where a zone border is the unique link of its country
# pair (otherwise None — never split a shared country flow across zone borders).


class BorderMetric(BaseModel):
    from_zone: str  # zone key
    to_zone: str  # zone key
    spread_eur_mwh: float  # |price_from - price_to|
    price_from: float | None = None
    price_to: float | None = None
    internal: bool = False  # both zones in the same country (intra-country congestion)
    congestion_income_eur_h: float | None = None  # spread × |commercial flow| (€/h); None unless unambiguous
    capacity_regime: CapacityRegime
    gb_decoupled: bool = False
    utilisation: float | None = None  # 0..1, NTC only — gated ENTSO-E (M6)


class CongestionSnapshot(BaseModel):
    ts: datetime  # UTC — when these metrics were computed
    data_ts: datetime | None = None  # UTC — market time of the underlying prices
    borders: list[BorderMetric]  # descending by spread


class ConvergencePoint(BaseModel):
    ts: datetime  # UTC — market time of this MTU
    price_std: float  # dispersion (population std) of zonal prices, €/MWh
    converged_pct: float  # share of priced borders with spread < threshold, 0..100


class ConvergenceSeries(BaseModel):
    start: datetime  # UTC
    end: datetime  # UTC
    threshold_eur_mwh: float  # a border counts as "converged" below this spread
    mean_converged_pct: float  # window headline
    latest_std: float | None = None  # dispersion at the most recent MTU
    points: list[ConvergencePoint]  # ascending by ts


# Net-flow Sankey (PLAN §4.5). Modelled bipartite — each country has an export
# side node and an import side node — so the graph is acyclic (ECharts needs a
# DAG; the grid has loop flows) and per-country (in − out) equals net position.


class SankeyNode(BaseModel):
    id: str  # unique node id: "x_FR" (export side) / "m_DE" (import side)
    country: str  # ISO-2
    side: Literal["export", "import"]


class SankeyLink(BaseModel):
    source: str  # SankeyNode id (export side)
    target: str  # SankeyNode id (import side)
    value: float  # MW — commercial net flow exporter -> importer


class SankeySnapshot(BaseModel):
    ts: datetime  # UTC — compute time
    data_ts: datetime | None = None  # UTC — market time of the flows
    nodes: list[SankeyNode]
    links: list[SankeyLink]
    total_mw: float  # total cross-border commercial exchange


# --- analytics (M6) --------------------------------------------------------
# Served from the durable DuckDB store (store/duckdb_store.py), which accumulates
# every refresh sweep — so these span far past the 48 h scrubber window. Source-
# agnostic: Energy-Charts data now, richer zone-level ENTSO-E data once a token
# is present. All timestamps UTC.


class SeriesPoint(BaseModel):
    ts: datetime  # UTC
    value: float


class ZoneSeries(BaseModel):
    zone: str  # zone key
    points: list[SeriesPoint]  # ascending by ts


class PriceSeriesResponse(BaseModel):
    start: datetime  # UTC — window start
    end: datetime  # UTC — window end (≈ now)
    hours: int
    zones: list[ZoneSeries]


class FlowSeriesPoint(BaseModel):
    ts: datetime  # UTC
    commercial_mw: float | None = None  # signed: + = from_zone -> to_zone
    physical_mw: float | None = None  # signed, same convention


class FlowSeriesResponse(BaseModel):
    from_zone: str
    to_zone: str
    start: datetime
    end: datetime
    hours: int
    points: list[FlowSeriesPoint]  # ascending by ts


class DurationPoint(BaseModel):
    pct: float  # 0..100 — share of the window at or above eur_mwh
    eur_mwh: float


class DurationCurve(BaseModel):
    zone: str
    hours: int
    n: int  # number of observations in the window
    points: list[DurationPoint]  # descending by price (duration-curve order)


class CorrelationMatrix(BaseModel):
    zones: list[str]  # zones actually present, in request order
    matrix: list[list[float | None]]  # row i / col j = Pearson corr(zones[i], zones[j])
    hours: int
    n_timestamps: int  # aligned timestamps the correlation ran on


class Coverage(BaseModel):
    price_rows: int
    flow_rows: int
    start: datetime | None = None  # UTC — earliest accumulated point
    end: datetime | None = None  # UTC — latest
    zones: list[str]  # zones with at least one price row
    source: str  # active data source feeding the store


# --- alerts / signals (M7, PLAN §4.8) -------------------------------------
# Derived in memory off the cached live snapshot + 48 h history (no extra API
# calls, mirrors the metrics router). Negative prices, price spikes (absolute +
# statistical vs the zone's own 48 h distribution), congested borders; near-full
# capacity only fires when an NTC exists (ENTSO-E), inert on Energy-Charts.

AlertType = Literal[
    "negative_price", "price_spike", "high_spread", "near_full_capacity"
]
AlertSeverity = Literal["info", "warn", "crit"]


class Alert(BaseModel):
    type: AlertType
    severity: AlertSeverity
    scope: Literal["zone", "border"]
    key: str  # zone key, or "A–B" for a border
    value: float  # the triggering quantity (€/MWh, or utilisation 0..1)
    detail: str  # short human-readable message
    ts: datetime | None = None  # UTC — market time of the underlying data


class AlertsSnapshot(BaseModel):
    ts: datetime  # UTC — compute time
    data_ts: datetime | None = None  # UTC — market time of the data
    counts: dict[str, int]  # severity -> count ({"crit","warn","info"})
    alerts: list[Alert]  # severity desc, then |value| desc


# --- forward model (M7, PLAN §4.7) ----------------------------------------
# Self-contained seasonal-naive baseline from the DuckDB history (hour-of-day
# p10/p50/p90, Europe/Brussels). A placeholder for the real merit-order / peakero
# forward model: the band overlays the realized spot to compare modelled vs cleared.


class ForwardPoint(BaseModel):
    ts: datetime  # UTC — forecast MTU
    p10: float
    p50: float  # median modelled price
    p90: float


class RealizedPoint(BaseModel):
    ts: datetime  # UTC
    eur_mwh: float


class ForwardCurve(BaseModel):
    zone: str
    generated_ts: datetime  # UTC — when this curve was built
    method: str  # e.g. "seasonal_naive_hod"
    n_history: int  # observations the model was fit on
    forward: list[ForwardPoint]  # ascending by ts
    realized: list[RealizedPoint]  # recent spot, ascending by ts
