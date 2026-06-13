"""Live-snapshot refresh.

Builds the snapshot from the active source and stores it in the TTL cache.
A refresh runs once at startup (so the first request is served from cache) and
then on an interval via APScheduler. A lock prevents overlapping builds.
"""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..sources.registry import get_source
from ..store import cache

log = logging.getLogger("fluxeu.jobs")

# A full Energy-Charts build takes ~15-25 min (rate limit), so refresh well off
# that cadence — day-ahead data barely moves intraday, and this leaves ample
# margin so warms never overlap (the lock also skips overlaps as a backstop).
REFRESH_MINUTES = 60

_scheduler: AsyncIOScheduler | None = None
_lock = asyncio.Lock()


async def refresh_snapshot() -> None:
    if _lock.locked():
        log.info("refresh already in progress — skipping")
        return
    async with _lock:
        source = get_source()
        try:
            snap = await source.fetch_snapshot()
        except Exception:  # noqa: BLE001 — never let a refresh kill the scheduler
            log.exception("snapshot refresh failed")
            return
        cache.set_snapshot(snap)
        cache.persist_snapshot(snap)  # survive restarts -> instant cold start
        log.info(
            "snapshot refreshed: %d prices, %d edges, source=%s data_ts=%s",
            len(snap.prices), len(snap.edges), snap.source, snap.data_ts,
        )


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    # serve the last persisted snapshot immediately (real but possibly stale),
    # then refresh in the background.
    persisted = cache.load_persisted()
    if persisted is not None:
        cache.set_snapshot(persisted)
        log.info("loaded persisted snapshot data_ts=%s", persisted.data_ts)
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(refresh_snapshot, "interval", minutes=REFRESH_MINUTES, id="refresh")
    _scheduler.start()
    # warm the cache without blocking startup
    asyncio.create_task(refresh_snapshot())


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
