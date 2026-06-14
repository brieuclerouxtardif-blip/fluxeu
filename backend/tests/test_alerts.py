"""M7 alerts — threshold→severity mapping for each signal. border_spreads is
stubbed so the congestion alerts don't depend on the real referential (already
covered in test_metrics)."""

from datetime import datetime, timezone

from app.domain import alerts
from app.models import BorderMetric, FlowEdge, HistoryFrame, SnapshotHistory

TS = datetime(2026, 6, 14, tzinfo=timezone.utc)


def _no_borders(monkeypatch):
    monkeypatch.setattr(alerts, "border_spreads", lambda prices, edges: [])


def _edge(a, b, commercial=None, physical=None, ntc=None):
    return FlowEdge(
        from_zone=a, to_zone=b, ts=TS, commercial_mw=commercial,
        physical_mw=physical, ntc_mw=ntc,
        capacity_regime="NTC" if ntc else "FLOW_BASED",
    )


def test_negative_price_severity(monkeypatch):
    _no_borders(monkeypatch)
    out = alerts.compute_alerts(TS, {"A": -10.0, "B": -60.0, "C": 50.0}, [], None)
    by = {a.key: a for a in out.alerts if a.type == "negative_price"}
    assert set(by) == {"A", "B"}  # C is positive -> no alert
    assert by["A"].severity == "warn"
    assert by["B"].severity == "crit"  # <= -50


def test_absolute_spike_severity(monkeypatch):
    _no_borders(monkeypatch)
    out = alerts.compute_alerts(TS, {"A": 160.0, "B": 320.0, "C": 50.0}, [], None)
    by = {a.key: a for a in out.alerts if a.type == "price_spike"}
    assert by["A"].severity == "warn"  # >= 150
    assert by["B"].severity == "crit"  # >= 300
    assert "C" not in by


def test_statistical_spike_vs_own_distribution(monkeypatch):
    _no_borders(monkeypatch)
    # A normally ~50 (tight); a live 90 is a big z-score outlier though < 150 abs
    frames = [
        HistoryFrame(ts=TS, prices={"A": v, "B": v}, net_positions={}, edges=[])
        for v in [48.0, 50.0, 52.0, 49.0, 51.0, 50.0]
    ]
    hist = SnapshotHistory(
        ts=TS, source="t", granularity={"prices": "bidding_zone", "flows": "country"},
        nodes=[], start=TS, end=TS, frames=frames,
    )
    out = alerts.compute_alerts(TS, {"A": 90.0, "B": 51.0}, [], hist)
    spikes = {a.key for a in out.alerts if a.type == "price_spike"}
    assert "A" in spikes  # statistical outlier
    assert "B" not in spikes  # at its normal level


def test_high_spread_severity(monkeypatch):
    monkeypatch.setattr(
        alerts, "border_spreads",
        lambda prices, edges: [
            BorderMetric(from_zone="A", to_zone="B", spread_eur_mwh=90.0, capacity_regime="NTC"),
            BorderMetric(from_zone="C", to_zone="D", spread_eur_mwh=45.0, capacity_regime="FLOW_BASED"),
            BorderMetric(from_zone="E", to_zone="F", spread_eur_mwh=30.0, capacity_regime="NTC"),
        ],
    )
    out = alerts.compute_alerts(TS, {}, [], None)
    by = {a.key: a for a in out.alerts if a.type == "high_spread"}
    assert by["A–B"].severity == "crit"  # >= 80
    assert by["C–D"].severity == "warn"  # >= 40
    assert "E–F" not in by  # below threshold


def test_near_full_capacity_ntc_only(monkeypatch):
    _no_borders(monkeypatch)
    edges = [
        _edge("A", "B", commercial=980.0, ntc=1000.0),   # 0.98 -> warn
        _edge("C", "D", commercial=1000.0, ntc=1000.0),  # 1.00 -> crit
        _edge("E", "F", commercial=995.0, ntc=None),     # no NTC -> inert
    ]
    out = alerts.compute_alerts(TS, {}, edges, None)
    by = {a.key: a for a in out.alerts if a.type == "near_full_capacity"}
    assert by["A–B"].severity == "warn"
    assert by["C–D"].severity == "crit"
    assert "E–F" not in by  # Energy-Charts never fabricates NTC


def test_counts_and_severity_sorted(monkeypatch):
    _no_borders(monkeypatch)
    out = alerts.compute_alerts(TS, {"A": -60.0, "B": 320.0, "C": -5.0}, [], None)
    # crit: A(neg<=-50), B(spike>=300); warn: C(neg)
    assert out.counts == {"crit": 2, "warn": 1, "info": 0}
    sev_rank = [alerts._SEV_RANK[a.severity] for a in out.alerts]
    assert sev_rank == sorted(sev_rank, reverse=True)  # crit before warn
