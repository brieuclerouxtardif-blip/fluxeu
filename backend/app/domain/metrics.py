"""Congestion metrics — computed in memory off the live snapshot + 48 h history.

No DB: the window is only ~48 h (the Energy-Charts API window) and ~40 zones,
so spreads / convergence are trivial aggregations. DuckDB earns its place at M6,
when the ENTSO-E backfill brings 30+ days of durable, SQL-shaped analytics.

Granularity reality (PLAN §1.2 / §2.1):
- price SPREAD is zone-level — |p_i - p_j| on every modelled border, including
  intra-country ones (NO/SE/IT/DK splits) → the #1 congestion signal.
- congestion RENT needs a flow, which exists only on the country graph, so it is
  filled only where a zone border is the *unique* modelled link of its country
  pair. Otherwise None — we never divide one shared country flow across borders.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import pstdev

from ..models import (
    BorderMetric,
    CongestionSnapshot,
    ConvergencePoint,
    ConvergenceSeries,
    FlowEdge,
    SankeyLink,
    SankeyNode,
    SankeySnapshot,
    SnapshotHistory,
)
from .countries import ZONE_TO_CC
from .interconnectors import load_interconnectors

# Below this spread a border is treated as converged (price coupling held).
CONVERGED_EUR_MWH = 0.5
# Ignore commercial flows below this |MW| as noise (matches the map's arc floor).
MIN_FLOW_MW = 1.0


def _border_pairs() -> list[tuple[str, str, str, bool]]:
    """(from_zone, to_zone, capacity_regime, gb_decoupled) for every modelled border."""
    return [
        (b.from_zone, b.to_zone, b.capacity_regime, b.gb_decoupled)
        for b in load_interconnectors()
    ]


def _unique_country_links() -> set[frozenset[str]]:
    """Country pairs joined by exactly ONE modelled cross-border zone link.

    Only for these is attributing the whole country flow to the single zone
    border unambiguous, so congestion rent is filled only here.
    """
    count: dict[frozenset[str], int] = defaultdict(int)
    for fz, tz, _, _ in _border_pairs():
        ca, cb = ZONE_TO_CC.get(fz), ZONE_TO_CC.get(tz)
        if ca and cb and ca != cb:
            count[frozenset((ca, cb))] += 1
    return {pair for pair, n in count.items() if n == 1}


def _country_commercial_mw(edges: list[FlowEdge]) -> dict[frozenset[str], float]:
    """country pair -> |commercial flow| MW (for rent)."""
    out: dict[frozenset[str], float] = {}
    for e in edges:
        if e.commercial_mw is None:
            continue
        out[frozenset((e.from_zone, e.to_zone))] = abs(e.commercial_mw)
    return out


def border_spreads(
    prices: dict[str, float], edges: list[FlowEdge]
) -> list[BorderMetric]:
    """One BorderMetric per modelled border with both zone prices, by |spread| desc."""
    unique_links = _unique_country_links()
    country_flow = _country_commercial_mw(edges)
    out: list[BorderMetric] = []
    for fz, tz, regime, gb in _border_pairs():
        pf, pt = prices.get(fz), prices.get(tz)
        if pf is None or pt is None:
            continue
        spread = round(abs(pf - pt), 2)
        ca, cb = ZONE_TO_CC.get(fz), ZONE_TO_CC.get(tz)
        internal = ca is not None and ca == cb
        rent: float | None = None
        if not internal and ca and cb:
            pair = frozenset((ca, cb))
            if pair in unique_links and pair in country_flow:
                rent = round(spread * country_flow[pair], 1)
        out.append(
            BorderMetric(
                from_zone=fz,
                to_zone=tz,
                spread_eur_mwh=spread,
                price_from=round(pf, 2),
                price_to=round(pt, 2),
                internal=internal,
                congestion_income_eur_h=rent,
                capacity_regime=regime,
                gb_decoupled=gb,
                utilisation=None,  # NTC only — gated ENTSO-E (M6)
            )
        )
    out.sort(key=lambda m: m.spread_eur_mwh, reverse=True)
    return out


def congestion_snapshot(
    data_ts: datetime | None, prices: dict[str, float], edges: list[FlowEdge]
) -> CongestionSnapshot:
    return CongestionSnapshot(
        ts=datetime.now(timezone.utc),
        data_ts=data_ts,
        borders=border_spreads(prices, edges),
    )


def convergence_series(history: SnapshotHistory) -> ConvergenceSeries:
    """Per-MTU dispersion of zonal prices + share of borders that stayed coupled."""
    pairs = [(fz, tz) for fz, tz, _, _ in _border_pairs()]
    points: list[ConvergencePoint] = []
    converged_pcts: list[float] = []
    for f in history.frames:
        values = [v for v in f.prices.values()]
        std = round(pstdev(values), 2) if len(values) >= 2 else 0.0
        priced = [
            abs(f.prices[a] - f.prices[b])
            for a, b in pairs
            if a in f.prices and b in f.prices
        ]
        if priced:
            conv = sum(1 for s in priced if s < CONVERGED_EUR_MWH) / len(priced) * 100
        else:
            conv = 0.0
        conv = round(conv, 1)
        converged_pcts.append(conv)
        points.append(ConvergencePoint(ts=f.ts, price_std=std, converged_pct=conv))
    mean_conv = round(sum(converged_pcts) / len(converged_pcts), 1) if converged_pcts else 0.0
    return ConvergenceSeries(
        start=history.start,
        end=history.end,
        threshold_eur_mwh=CONVERGED_EUR_MWH,
        mean_converged_pct=mean_conv,
        latest_std=points[-1].price_std if points else None,
        points=points,
    )


def sankey_snapshot(
    data_ts: datetime | None, edges: list[FlowEdge]
) -> SankeySnapshot:
    """Bipartite exporter→importer net-flow Sankey from the country edges.

    Each commercial edge becomes one link from the exporter's export-side node
    to the importer's import-side node, oriented by sign (+ = from→to). Keeping
    the two sides separate makes the graph acyclic and guarantees, per country,
    (Σ import links) − (Σ export links) = net position.
    """
    links: list[SankeyLink] = []
    exporters: set[str] = set()
    importers: set[str] = set()
    total = 0.0
    for e in edges:
        cm = e.commercial_mw
        if cm is None or abs(cm) < MIN_FLOW_MW:
            continue
        exp, imp = (e.from_zone, e.to_zone) if cm > 0 else (e.to_zone, e.from_zone)
        value = round(abs(cm), 1)
        links.append(SankeyLink(source=f"x_{exp}", target=f"m_{imp}", value=value))
        exporters.add(exp)
        importers.add(imp)
        total += value
    nodes = [
        SankeyNode(id=f"x_{c}", country=c, side="export") for c in sorted(exporters)
    ] + [
        SankeyNode(id=f"m_{c}", country=c, side="import") for c in sorted(importers)
    ]
    return SankeySnapshot(
        ts=datetime.now(timezone.utc),
        data_ts=data_ts,
        nodes=nodes,
        links=links,
        total_mw=round(total, 1),
    )
