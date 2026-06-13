"""DataSource interface + snapshot derivation.

Energy-Charts (no key) is the default implementation; ENTSO-E (token) is the
authoritative upgrade wired in M6. Both produce the same LiveSnapshot and
SnapshotHistory.
"""

from __future__ import annotations

from typing import Protocol

from ..models import LiveSnapshot, SnapshotHistory


class DataSource(Protocol):
    name: str

    async def fetch_snapshot(self) -> LiveSnapshot:
        """Build the consolidated live snapshot (prices + flows), UTC-dated."""
        ...

    async def fetch_history(self) -> SnapshotHistory:
        """Build a ~48 h window of frames from the same sweep (M4 scrubber)."""
        ...


def live_from_history(hist: SnapshotHistory) -> LiveSnapshot | None:
    """Derive the live snapshot (latest frame) from a history, so one sweep
    feeds both the map and the scrubber. None if the history has no frames."""
    if not hist.frames:
        return None
    last = hist.frames[-1]
    return LiveSnapshot(
        ts=hist.ts,
        source=hist.source,
        data_ts=last.ts,
        granularity=hist.granularity,
        prices=last.prices,
        nodes=hist.nodes,
        edges=last.edges,
        net_positions=last.net_positions,
    )
