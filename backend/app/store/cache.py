"""Live-snapshot cache (in-memory + disk persistence).

The APScheduler refresh job (and a lazy build on first request) writes here;
the /api/snapshot/live endpoint reads here. TTL guards against serving a
stale snapshot if the refresh job dies.

The Energy-Charts rate limit makes a cold build slow (~9 min, see
sources/energy_charts.py), so each successful build is also persisted to disk
and reloaded on startup — cold start then serves real, slightly-stale data
instantly while a fresh build runs in the background.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..config import settings
from ..models import LiveSnapshot

log = logging.getLogger("fluxeu.cache")

# refreshed every ~30 min; treat older than 1 h as stale
TTL_SECONDS = 3600

# single-file cache of the LATEST snapshot (not history — that's DuckDB, M4)
_CACHE_FILE = settings.data_dir / "snapshot.cache.json"

_snapshot: LiveSnapshot | None = None
_stored_at: datetime | None = None


def set_snapshot(snap: LiveSnapshot) -> None:
    global _snapshot, _stored_at
    _snapshot = snap
    _stored_at = datetime.now(timezone.utc)


def persist_snapshot(snap: LiveSnapshot) -> None:
    """Write the snapshot to disk so the next cold start serves it instantly."""
    try:
        _CACHE_FILE.write_text(snap.model_dump_json(), encoding="utf-8")
    except OSError:
        log.exception("could not persist snapshot to %s", _CACHE_FILE)


def load_persisted() -> LiveSnapshot | None:
    """Load the last persisted snapshot, or None if absent/unreadable."""
    if not _CACHE_FILE.exists():
        return None
    try:
        return LiveSnapshot.model_validate_json(_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.exception("could not load persisted snapshot from %s", _CACHE_FILE)
        return None


def get_snapshot() -> LiveSnapshot | None:
    return _snapshot


def last_refresh() -> datetime | None:
    return _stored_at


def is_fresh() -> bool:
    if _stored_at is None:
        return False
    return (datetime.now(timezone.utc) - _stored_at).total_seconds() < TTL_SECONDS
