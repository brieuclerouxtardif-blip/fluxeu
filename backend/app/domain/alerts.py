"""Alerts / signals (M7, PLAN §4.8) — derived in memory off the cached live
snapshot + 48 h history, like the metrics router (no extra API calls).

Signals:
- negative_price: a zone clears below 0 €/MWh (renewable oversupply).
- price_spike: a zone is abnormally high — absolute thresholds OR a statistical
  outlier vs its own 48 h distribution (z-score), so a normally-cheap zone
  spiking is caught even below the absolute bar.
- high_spread: a congested border (|Δ price| over a threshold) — reuses the M5
  spread computation so the definition stays single-sourced.
- near_full_capacity: |flow| / NTC near 1 — fires only when an NTC exists, i.e.
  under ENTSO-E (M6). Inert on Energy-Charts (ntc is None) — never fabricated.
"""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean, pstdev

from ..models import Alert, AlertsSnapshot, FlowEdge, SnapshotHistory
from .metrics import border_spreads

# negative prices
NEG_CRIT = -50.0  # €/MWh — deeply negative
# absolute spike thresholds
SPIKE_WARN = 150.0
SPIKE_CRIT = 300.0
# statistical spike: z-score vs the zone's own 48 h mean/std
SPIKE_Z = 3.0
SPIKE_Z_MIN_PRICE = 80.0  # don't flag tiny absolute moves in calm zones
MIN_SAMPLES = 6  # need enough history for a meaningful z-score
# congested border (|Δ price|)
SPREAD_WARN = 40.0
SPREAD_CRIT = 80.0
# near-full interconnector (utilisation = |flow| / NTC), ENTSO-E only
UTIL_WARN = 0.95

_SEV_RANK = {"crit": 3, "warn": 2, "info": 1}


def _zone_stats(history: SnapshotHistory | None) -> dict[str, tuple[float, float]]:
    """{zone: (mean, population std)} over the history window, for z-scores."""
    if history is None:
        return {}
    series: dict[str, list[float]] = {}
    for f in history.frames:
        for z, v in f.prices.items():
            series.setdefault(z, []).append(v)
    return {
        z: (mean(vs), pstdev(vs))
        for z, vs in series.items()
        if len(vs) >= MIN_SAMPLES
    }


def _border_label(a: str, b: str) -> str:
    return f"{a}–{b}"  # en dash, matching the congestion panel


def compute_alerts(
    data_ts: datetime | None,
    prices: dict[str, float],
    edges: list[FlowEdge],
    history: SnapshotHistory | None,
) -> AlertsSnapshot:
    alerts: list[Alert] = []

    # negative prices
    for zone, p in prices.items():
        if p < 0:
            alerts.append(
                Alert(
                    type="negative_price",
                    severity="crit" if p <= NEG_CRIT else "warn",
                    scope="zone",
                    key=zone,
                    value=round(p, 2),
                    detail=f"Prix négatif {p:.1f} €/MWh",
                    ts=data_ts,
                )
            )

    # price spikes (absolute or statistical), positive prices only
    stats = _zone_stats(history)
    for zone, p in prices.items():
        if p <= 0:
            continue
        if p >= SPIKE_CRIT:
            sev = "crit"
        elif p >= SPIKE_WARN:
            sev = "warn"
        else:
            m_s = stats.get(zone)
            if (
                m_s
                and m_s[1] > 0
                and p >= SPIKE_Z_MIN_PRICE
                and (p - m_s[0]) / m_s[1] >= SPIKE_Z
            ):
                sev = "warn"
            else:
                continue
        alerts.append(
            Alert(
                type="price_spike",
                severity=sev,
                scope="zone",
                key=zone,
                value=round(p, 2),
                detail=f"Pic de prix {p:.0f} €/MWh",
                ts=data_ts,
            )
        )

    # congested borders (reuse the M5 spread definition)
    for m in border_spreads(prices, edges):
        if m.spread_eur_mwh < SPREAD_WARN:
            continue
        alerts.append(
            Alert(
                type="high_spread",
                severity="crit" if m.spread_eur_mwh >= SPREAD_CRIT else "warn",
                scope="border",
                key=_border_label(m.from_zone, m.to_zone),
                value=m.spread_eur_mwh,
                detail=f"Congestion, spread {m.spread_eur_mwh:.0f} €/MWh",
                ts=data_ts,
            )
        )

    # near-full interconnectors (NTC only — ENTSO-E)
    for e in edges:
        if not e.ntc_mw or e.ntc_mw <= 0:
            continue
        flow = max(abs(e.commercial_mw or 0.0), abs(e.physical_mw or 0.0))
        util = flow / e.ntc_mw
        if util >= UTIL_WARN:
            alerts.append(
                Alert(
                    type="near_full_capacity",
                    severity="crit" if util >= 1.0 else "warn",
                    scope="border",
                    key=_border_label(e.from_zone, e.to_zone),
                    value=round(util, 3),
                    detail=f"Interconnexion à {util * 100:.0f}% de la NTC",
                    ts=data_ts,
                )
            )

    alerts.sort(key=lambda a: (_SEV_RANK[a.severity], abs(a.value)), reverse=True)
    counts = {sev: sum(1 for a in alerts if a.severity == sev) for sev in ("crit", "warn", "info")}
    return AlertsSnapshot(
        ts=datetime.now(timezone.utc), data_ts=data_ts, counts=counts, alerts=alerts
    )
