"""M6 analytics router — endpoints over the DuckDB store, via a minimal app so
the scheduler/lifespan never runs (no network). DB seeded in memory."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models import FlowEdge, HistoryFrame, SnapshotHistory
from app.routers import analytics
from app.store import duckdb_store


def _seed():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    ts = [now - timedelta(hours=2), now - timedelta(hours=1), now]
    fr, be, comm = [50.0, -10.0, 40.0], [55.0, -5.0, 45.0], [500.0, 600.0, 400.0]
    frames = [
        HistoryFrame(
            ts=t, prices={"FR": pf, "BE": pb}, net_positions={},
            edges=[FlowEdge(from_zone="BE", to_zone="FR", ts=t, commercial_mw=c,
                            physical_mw=None, ntc_mw=None, capacity_regime="FLOW_BASED")],
        )
        for t, pf, pb, c in zip(ts, fr, be, comm)
    ]
    return SnapshotHistory(
        ts=now, source="test",
        granularity={"prices": "bidding_zone", "flows": "country"},
        nodes=[], start=ts[0], end=ts[-1], frames=frames,
    )


@pytest.fixture
def client():
    duckdb_store.use_database(":memory:")
    duckdb_store.ingest_history(_seed())
    app = FastAPI()
    app.include_router(analytics.router)
    yield TestClient(app)
    duckdb_store.use_database(":memory:")


def test_coverage(client):
    r = client.get("/api/analytics/coverage")
    assert r.status_code == 200
    body = r.json()
    assert body["price_rows"] == 6
    assert body["flow_rows"] == 3
    assert set(body["zones"]) == {"BE", "FR"}
    assert "source" in body


def test_prices(client):
    r = client.get("/api/prices", params={"zones": "FR,BE", "hours": 48})
    assert r.status_code == 200
    body = r.json()
    by_zone = {z["zone"]: z for z in body["zones"]}
    assert set(by_zone) == {"FR", "BE"}
    fr = [p["value"] for p in by_zone["FR"]["points"]]
    assert fr == [50.0, -10.0, 40.0]  # ascending by ts


def test_duration(client):
    r = client.get("/api/analytics/duration", params={"zone": "FR", "hours": 48})
    assert r.status_code == 200
    body = r.json()
    assert body["n"] == 3
    prices = [p["eur_mwh"] for p in body["points"]]
    assert prices == [50.0, 40.0, -10.0]  # high -> low, negative kept
    assert body["points"][-1]["pct"] == 100.0


def test_correlation(client):
    r = client.get("/api/analytics/correlation", params={"zones": "FR,BE", "hours": 48})
    assert r.status_code == 200
    body = r.json()
    assert body["zones"] == ["FR", "BE"]
    assert body["n_timestamps"] == 3
    assert body["matrix"][0][1] == pytest.approx(1.0)  # BE = FR + 5


def test_flows_orientation(client):
    fwd = client.get("/api/flows", params={"from": "BE", "to": "FR", "hours": 48}).json()
    assert [p["commercial_mw"] for p in fwd["points"]] == [500.0, 600.0, 400.0]
    rev = client.get("/api/flows", params={"from": "FR", "to": "BE", "hours": 48}).json()
    assert [p["commercial_mw"] for p in rev["points"]] == [-500.0, -600.0, -400.0]


def test_export_csv(client):
    r = client.get("/api/export.csv", params={"table": "prices", "hours": 48})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    lines = r.text.strip().splitlines()
    assert lines[0] == "zone,ts,eur_mwh"
    assert len(lines) == 1 + 6  # header + 6 rows


def test_export_csv_rejects_bad_table(client):
    r = client.get("/api/export.csv", params={"table": "bogus"})
    assert r.status_code == 422  # blocked by the route's regex pattern
