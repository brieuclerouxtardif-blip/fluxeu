import asyncio

from fastapi import APIRouter, HTTPException

from ..jobs.scheduler import refresh_snapshot
from ..models import LiveSnapshot
from ..store import cache

router = APIRouter(prefix="/api", tags=["snapshot"])


@router.get("/snapshot/live", response_model=LiveSnapshot)
async def get_live_snapshot() -> LiveSnapshot:
    snap = cache.get_snapshot()
    if snap is None:
        # cold start: kick off a warm (the lock in refresh_snapshot dedupes
        # against the startup build) and tell the client to retry shortly,
        # rather than blocking the request for the full build (~minutes).
        asyncio.create_task(refresh_snapshot())
        raise HTTPException(
            status_code=503,
            detail="snapshot warming up, retry shortly",
            headers={"Retry-After": "15"},
        )
    return snap
