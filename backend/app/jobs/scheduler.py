"""Live-snapshot + history refresh.

One Energy-Charts sweep builds a ~48 h history; the live snapshot is just its
latest frame — so the map and the scrubber share a single rate-limited sweep
(no separate backfill job). Results go to the TTL cache and to disk. A refresh
runs once at startup and then on an interval; a lock prevents overlapping builds.
"""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..sources.base import live_from_history
from ..sources.registry import get_source
from ..store import cache, duckdb_store

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
            hist = await source.fetch_history()
        except Exception:  # noqa: BLE001 — never let a refresh kill the scheduler
            log.exception("snapshot refresh failed")
            return
        cache.set_history(hist)
        cache.persist_history(hist)
        # accumulate the sweep into DuckDB (durable long history, M6). Off the
        # event loop, and guarded — a DB hiccup must never kill the refresh.
        try:
            rows = await asyncio.to_thread(duckdb_store.ingest_history, hist)
            log.info("duckdb ingested %d price rows", rows)
        except Exception:  # noqa: BLE001
            log.exception("duckdb ingestion failed (continuing)")
        live = live_from_history(hist)
        if live is not None:
            cache.set_snapshot(live)
            cache.persist_snapshot(live)
        log.info(
            "refreshed: %d frames, %d prices, %d edges, source=%s data_ts=%s",
            len(hist.frames),
            len(live.prices) if live else 0,
            len(live.edges) if live else 0,
            hist.source,
            live.data_ts if live else None,
        )


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    # serve the last persisted snapshot + history immediately (real but possibly
    # stale), then refresh in the background.
    persisted = cache.load_persisted()
    if persisted is not None:
        cache.set_snapshot(persisted)
        log.info("loaded persisted snapshot data_ts=%s", persisted.data_ts)
    hist = cache.load_persisted_history()
    if hist is not None:
        cache.set_history(hist)
        log.info("loaded persisted history: %d frames", len(hist.frames))
        # seed DuckDB from the persisted window so analytics has data at once
        # (the first full sweep is ~15-25 min away); idempotent upsert.
        try:
            duckdb_store.ingest_history(hist)
        except Exception:  # noqa: BLE001
            log.exception("duckdb seed from persisted history failed (continuing)")
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
