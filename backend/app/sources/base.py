"""DataSource interface.

Energy-Charts (no key) is the default implementation; ENTSO-E (token) is the
authoritative upgrade wired in M6. Both produce the same LiveSnapshot.
"""

from __future__ import annotations

from typing import Protocol

from ..models import LiveSnapshot


class DataSource(Protocol):
    name: str

    async def fetch_snapshot(self) -> LiveSnapshot:
        """Build the consolidated live snapshot (prices + flows), UTC-dated."""
        ...
