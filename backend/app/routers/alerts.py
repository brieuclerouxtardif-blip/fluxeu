"""Alerts / signals (M7, PLAN §4.8). Reads the same cached snapshot + history as
the map and metrics — zero extra API calls — and 503s while the cache warms."""

import asyncio

from fastapi import APIRouter, HTTPException

from ..domain.alerts import compute_alerts
from ..jobs.scheduler import refresh_snapshot
from ..models import AlertsSnapshot
from ..store import cache

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts", response_model=AlertsSnapshot)
async def get_alerts() -> AlertsSnapshot:
    """Negative prices, price spikes, congested borders, near-full NTC."""
    snap = cache.get_snapshot()
    if snap is None:
        asyncio.create_task(refresh_snapshot())
        raise HTTPException(
            status_code=503,
            detail="alerts warming up, retry shortly",
            headers={"Retry-After": "15"},
        )
    return compute_alerts(snap.data_ts, snap.prices, snap.edges, cache.get_history())
