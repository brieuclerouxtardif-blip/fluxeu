"""M6 DuckDB store — idempotent ingest + SQL analytics (duration, correlation,
series, coverage, CSV). Runs on an in-memory DB; no network, no disk."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import FlowEdge, HistoryFrame, SnapshotHistory
from app.store import duckdb_store


@pytest.fixture(autouse=True)
def fresh_db():
    duckdb_store.use_database(":memory:")
    yield
    duckdb_store.use_database(":memory:")  # reset between tests


def _history():
    """3 recent MTUs. BE = FR + 5 everywhere (perfectly correlated, incl. a
    negative price). One signed border BE->FR commercial flow."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    ts = [now - timedelta(hours=2), now - timedelta(hours=1), now]
    fr = [50.0, -10.0, 40.0]
    be = [55.0, -5.0, 45.0]
    comm = [500.0, 600.0, 400.0]  # + = BE -> FR
    frames = []
    for t, pf, pb, c in zip(ts, fr, be, comm):
        frames.append(
            HistoryFrame(
                ts=t,
                prices={"FR": pf, "BE": pb},
                net_positions={},
                edges=[
                    FlowEdge(
                        from_zone="BE", to_zone="FR", ts=t,
                        commercial_mw=c, physical_mw=None, ntc_mw=None,
                        capacity_regime="FLOW_BASED",
                    )
                ],
            )
        )
    return SnapshotHistory(
        ts=now, source="test",
        granularity={"prices": "bidding_zone", "flows": "country"},
        nodes=[], start=ts[0], end=ts[-1], frames=frames,
    )


def test_ingest_is_idempotent():
    hist = _history()
    n1 = duckdb_store.ingest_history(hist)
    assert n1 == 6  # 2 zones x 3 frames
    duckdb_store.ingest_history(hist)  # re-ingest same window
    cov = duckdb_store.coverage()
    assert cov["price_rows"] == 6  # upsert by PK — no duplication
    assert cov["flow_rows"] == 3
    assert set(cov["zones"]) == {"BE", "FR"}
    assert cov["start"] is not None and cov["end"] is not None


def test_price_series_ascending_and_filtered():
    duckdb_store.ingest_history(_history())
    s = duckdb_store.price_series(["FR", "XX"], hours=48)
    assert set(s) == {"FR"}  # unknown zone dropped
    pts = s["FR"]
    assert [v for _, v in pts] == [50.0, -10.0, 40.0]  # ascending by ts
    assert pts[0][0] < pts[-1][0]


def test_duration_curve_sorted_desc_keeps_negative():
    duckdb_store.ingest_history(_history())
    dc = duckdb_store.duration_curve("FR", hours=48)
    prices = [v for _, v in dc]
    assert prices == [50.0, 40.0, -10.0]  # high -> low
    assert dc[0][0] == pytest.approx(100.0 / 3, abs=0.01)  # first point ~33%
    assert dc[-1][0] == 100.0  # last point = 100% of time at/above the min
    assert min(prices) == -10.0  # negative price preserved, not clipped


def test_correlation_perfect_linear():
    duckdb_store.ingest_history(_history())
    zones, matrix, n = duckdb_store.correlation(["FR", "BE"], hours=48)
    assert zones == ["FR", "BE"]
    assert n == 3
    assert matrix[0][0] == pytest.approx(1.0)
    assert matrix[1][1] == pytest.approx(1.0)
    # BE = FR + 5 -> Pearson correlation is exactly 1
    assert matrix[0][1] == pytest.approx(1.0)
    assert matrix[1][0] == pytest.approx(1.0)


def test_correlation_needs_two_present_zones():
    duckdb_store.ingest_history(_history())
    zones, matrix, n = duckdb_store.correlation(["FR"], hours=48)
    assert zones == [] and matrix == [] and n == 0


def test_flow_series_orientation_and_sign():
    duckdb_store.ingest_history(_history())
    # stored as BE->FR (+). Querying BE->FR returns it as-is...
    fwd = duckdb_store.flow_series("BE", "FR", hours=48)
    assert [c for _, c, _ in fwd] == [500.0, 600.0, 400.0]
    # ...querying FR->BE negates to honour the requested orientation.
    rev = duckdb_store.flow_series("FR", "BE", hours=48)
    assert [c for _, c, _ in rev] == [-500.0, -600.0, -400.0]


def test_export_frame_columns():
    duckdb_store.ingest_history(_history())
    pf = duckdb_store.export_frame("prices", hours=48)
    assert list(pf.columns) == ["zone", "ts", "eur_mwh"]
    assert len(pf) == 6
    ff = duckdb_store.export_frame("flows", hours=48, zones=["FR"])
    assert list(ff.columns) == ["from_zone", "to_zone", "ts", "commercial_mw", "physical_mw"]
    assert len(ff) == 3  # FR appears on every flow row
    with pytest.raises(ValueError):
        duckdb_store.export_frame("bogus", hours=48)


def test_window_excludes_old_rows():
    """A frame older than the window must not appear."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    old = now - timedelta(hours=100)
    hist = SnapshotHistory(
        ts=now, source="test",
        granularity={"prices": "bidding_zone", "flows": "country"},
        nodes=[], start=old, end=old,
        frames=[HistoryFrame(ts=old, prices={"FR": 99.0}, net_positions={}, edges=[])],
    )
    duckdb_store.ingest_history(hist)
    assert duckdb_store.price_series(["FR"], hours=48) == {}  # outside 48 h window
    assert duckdb_store.coverage()["price_rows"] == 1  # but still stored
