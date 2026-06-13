"""Live-snapshot + short-history cache (in-memory + disk persistence).

The APScheduler refresh job (and a lazy build on first request) writes here;
the /api/snapshot/live and /api/history endpoints read here. TTL guards the
live snapshot against serving stale data if the refresh job dies.

The Energy-Charts rate limit makes a cold build slow (~15-25 min, see
sources/energy_charts.py), so each successful build is also persisted to disk
and reloaded on startup — cold start then serves real, slightly-stale data
(map + 48 h scrubber) instantly while a fresh build runs in the background.

Long-horizon history / SQL analytics is DuckDB territory, deferred to M5/M6;
here we keep only the latest 48 h window the scrubber needs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..config import settings
from ..models import LiveSnapshot, SnapshotHistory

log = logging.getLogger("fluxeu.cache")

# refreshed every ~60 min; treat older than 1 h as stale
TTL_SECONDS = 3600

_CACHE_FILE = settings.data_dir / "snapshot.cache.json"
_HISTORY_FILE = settings.data_dir / "history.cache.json"

_snapshot: LiveSnapshot | None = None
_stored_at: datetime | None = None
_history: SnapshotHistory | None = None


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


# --- 48 h history (M4 scrubber) -------------------------------------------


def set_history(hist: SnapshotHistory) -> None:
    global _history
    _history = hist


def get_history() -> SnapshotHistory | None:
    return _history


def persist_history(hist: SnapshotHistory) -> None:
    try:
        _HISTORY_FILE.write_text(hist.model_dump_json(), encoding="utf-8")
    except OSError:
        log.exception("could not persist history to %s", _HISTORY_FILE)


def load_persisted_history() -> SnapshotHistory | None:
    if not _HISTORY_FILE.exists():
        return None
    try:
        return SnapshotHistory.model_validate_json(_HISTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.exception("could not load persisted history from %s", _HISTORY_FILE)
        return None
