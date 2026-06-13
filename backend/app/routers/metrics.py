"""Congestion metrics (M5) — derived in memory from the cached snapshot/history.

Both endpoints read the same caches the map and scrubber use, so they cost no
extra API calls. While the cache is still warming they 503 with Retry-After,
mirroring /snapshot/live.
"""

import asyncio

from fastapi import APIRouter, HTTPException

from ..domain.metrics import congestion_snapshot, convergence_series
from ..jobs.scheduler import refresh_snapshot
from ..models import CongestionSnapshot, ConvergenceSeries
from ..store import cache

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


def _warming(what: str) -> HTTPException:
    asyncio.create_task(refresh_snapshot())
    return HTTPException(
        status_code=503,
        detail=f"{what} warming up, retry shortly",
        headers={"Retry-After": "15"},
    )


@router.get("/congestion", response_model=CongestionSnapshot)
async def get_congestion() -> CongestionSnapshot:
    """Zone-level price spreads (heatmap + leaderboard), descending by spread."""
    snap = cache.get_snapshot()
    if snap is None:
        raise _warming("congestion")
    return congestion_snapshot(snap.data_ts, snap.prices, snap.edges)


@router.get("/convergence", response_model=ConvergenceSeries)
async def get_convergence() -> ConvergenceSeries:
    """Per-MTU price dispersion + share of coupled borders over the 48 h window."""
    hist = cache.get_history()
    if hist is None:
        raise _warming("convergence")
    return convergence_series(hist)
