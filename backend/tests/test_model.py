"""M7 forward model — the seasonal-naive baseline must learn the hour-of-day
shape from the DuckDB history. In-memory DB, deterministic price-by-hour."""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.domain import model
from app.models import HistoryFrame, SnapshotHistory
from app.store import duckdb_store

NIGHT = {0, 1, 2, 3, 4, 5}
MIDDAY = {11, 12, 13, 14, 15}


@pytest.fixture(autouse=True)
def fresh_db():
    duckdb_store.use_database(":memory:")
    yield
    duckdb_store.use_database(":memory:")


def _price_for_hour(h: int) -> float:
    if h in NIGHT:
        return 100.0
    if h in MIDDAY:
        return -20.0  # solar-driven midday dip (incl. negative)
    return 40.0


def _seed_pattern(zone: str = "FR", hours: int = 72):
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    frames = []
    for k in range(hours, 0, -1):
        ts = now - timedelta(hours=k)
        h = pd.Timestamp(ts).tz_convert("Europe/Brussels").hour
        frames.append(
            HistoryFrame(ts=ts, prices={zone: _price_for_hour(h)}, net_positions={}, edges=[])
        )
    duckdb_store.ingest_history(
        SnapshotHistory(
            ts=now, source="t",
            granularity={"prices": "bidding_zone", "flows": "country"},
            nodes=[], start=frames[0].ts, end=frames[-1].ts, frames=frames,
        )
    )


def test_forward_learns_hour_of_day_shape():
    _seed_pattern("FR")
    fc = model.forward_curve("FR", 24)
    assert fc.zone == "FR"
    assert fc.method == "seasonal_naive_hod"
    assert fc.n_history == 72
    assert len(fc.forward) == 24
    assert all(p.p10 <= p.p50 <= p.p90 for p in fc.forward)

    bhour = lambda ts: pd.Timestamp(ts).tz_convert("Europe/Brussels").hour
    night = [p.p50 for p in fc.forward if bhour(p.ts) in NIGHT]
    midday = [p.p50 for p in fc.forward if bhour(p.ts) in MIDDAY]
    assert night and midday
    # the model recovered the shape: midday cheaper than night
    assert max(midday) < min(night)
    assert min(midday) < 0  # negative midday prices preserved


def test_realized_window_is_recent():
    _seed_pattern("FR")
    fc = model.forward_curve("FR", 24)
    # realized = last ~48 h of the 72 h seeded (boundary ±1 by wall-clock minute)
    assert 47 <= len(fc.realized) <= 48
    now = datetime.now(timezone.utc)
    assert all(r.ts >= now - timedelta(hours=49) for r in fc.realized)


def test_forward_empty_without_history():
    fc = model.forward_curve("ZZ", 24)
    assert fc.forward == []
    assert fc.realized == []
    assert fc.n_history == 0
