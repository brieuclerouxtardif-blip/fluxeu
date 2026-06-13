"""M5 congestion metrics — spreads (zone-level), rent (only where unambiguous),
and the 48 h convergence series. The zone/border referential is monkeypatched
so the assertions don't drift when the real data files change."""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.domain import metrics
from app.models import FlowEdge, HistoryFrame, SnapshotHistory

# synthetic referential: countries X={A,A2}, Y={B}, Z={C,C2}
#  A-B   : X-Y, the ONLY X-Y link        -> rent fillable
#  B-C   : Y-Z, one of TWO Y-Z links     -> rent ambiguous -> None
#  B-C2  : Y-Z, the other one            -> rent None
#  A-A2  : X-X, intra-country            -> internal, rent None
_BORDERS = [
    ("A", "B", "NTC", False),
    ("B", "C", "FLOW_BASED", False),
    ("B", "C2", "FLOW_BASED", False),
    ("A", "A2", "NTC", False),
]
_ZONE_TO_CC = {"A": "X", "A2": "X", "B": "Y", "C": "Z", "C2": "Z"}


def _patch_referential(monkeypatch):
    monkeypatch.setattr(
        metrics,
        "load_interconnectors",
        lambda: [
            SimpleNamespace(
                from_zone=fz, to_zone=tz, capacity_regime=reg, gb_decoupled=gb
            )
            for fz, tz, reg, gb in _BORDERS
        ],
    )
    monkeypatch.setattr(metrics, "ZONE_TO_CC", _ZONE_TO_CC)


def _edge(cc_from, cc_to, commercial):
    return FlowEdge(
        from_zone=cc_from,
        to_zone=cc_to,
        ts=datetime(2026, 6, 13, tzinfo=timezone.utc),
        commercial_mw=commercial,
        physical_mw=None,
        ntc_mw=None,
        capacity_regime="NTC",
    )


def test_border_spreads_rent_and_internal(monkeypatch):
    _patch_referential(monkeypatch)
    prices = {"A": 50.0, "A2": 55.0, "B": 40.0, "C": 30.0, "C2": 30.0}
    edges = [_edge("X", "Y", 1000.0), _edge("Y", "Z", 500.0)]

    out = metrics.border_spreads(prices, edges)
    by_pair = {(m.from_zone, m.to_zone): m for m in out}

    # descending by spread; A-A2 (5) is last
    assert [round(m.spread_eur_mwh, 1) for m in out] == [10.0, 10.0, 10.0, 5.0]
    assert out[-1].from_zone == "A" and out[-1].to_zone == "A2"

    ab = by_pair[("A", "B")]
    assert ab.spread_eur_mwh == 10.0
    assert ab.internal is False
    assert ab.congestion_income_eur_h == 10000.0  # 10 €/MWh × 1000 MW
    assert ab.utilisation is None  # gated ENTSO-E (M6)

    # Y-Z has two modelled links -> rent not attributable -> None
    assert by_pair[("B", "C")].congestion_income_eur_h is None
    assert by_pair[("B", "C2")].congestion_income_eur_h is None

    # intra-country border flagged, no rent
    aa = by_pair[("A", "A2")]
    assert aa.internal is True
    assert aa.spread_eur_mwh == 5.0
    assert aa.congestion_income_eur_h is None


def test_border_spreads_skips_missing_prices(monkeypatch):
    _patch_referential(monkeypatch)
    # only A and B priced -> only the A-B border survives
    out = metrics.border_spreads({"A": 50.0, "B": 30.0}, [])
    assert len(out) == 1
    assert (out[0].from_zone, out[0].to_zone) == ("A", "B")
    assert out[0].congestion_income_eur_h is None  # no flow given


def _history(*frame_prices):
    frames = [
        HistoryFrame(
            ts=datetime(2026, 6, 13, h, tzinfo=timezone.utc),
            prices=p,
            net_positions={},
            edges=[],
        )
        for h, p in enumerate(frame_prices)
    ]
    return SnapshotHistory(
        ts=datetime(2026, 6, 13, tzinfo=timezone.utc),
        source="test",
        granularity={"prices": "bidding_zone", "flows": "country"},
        nodes=[],
        start=frames[0].ts,
        end=frames[-1].ts,
        frames=frames,
    )


def test_convergence_series(monkeypatch):
    _patch_referential(monkeypatch)
    hist = _history(
        {"A": 50.0, "B": 50.0, "C": 50.0},  # fully converged
        {"A": 50.0, "B": 40.0, "C": 40.0},  # A-B diverged, B-C still coupled
    )
    cs = metrics.convergence_series(hist)

    assert len(cs.points) == 2
    assert cs.threshold_eur_mwh == metrics.CONVERGED_EUR_MWH
    # frame 0: all equal -> std 0, both priced borders converged
    assert cs.points[0].price_std == 0.0
    assert cs.points[0].converged_pct == 100.0
    # frame 1: 1 of 2 priced borders converged
    assert cs.points[1].converged_pct == 50.0
    assert cs.points[1].price_std > 0
    assert cs.mean_converged_pct == 75.0
    assert cs.latest_std == cs.points[1].price_std
