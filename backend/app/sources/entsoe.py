"""ENTSO-E Transparency Platform data source (M6 upgrade) — entsoe-py.

Authoritative and **zone-level**. Written and wired, but DORMANT until a token
is present: the registry falls back to Energy-Charts when there's no token or the
import fails, so this never runs by accident. Where the Energy-Charts demo gives
country-level flows and no capacities, this yields:
  - zone→zone cross-border flows: scheduled (commercial) and physical,
  - real **NTC** (day-ahead net transfer capacity) → unlocks utilisation,
  - prices per bidding zone.

Grounding (PLAN §2.2 / CLAUDE.md, hard rule): zones, EIC codes and adjacencies
come from entsoe-py's own `Area` enum + `NEIGHBOURS` dict — never hardcoded from
memory. Our hyphenated zone keys (DE-LU, NO2) are bridged to Area names (DE_LU,
NO_2) by a transform verified against `Area.__members__` at import; the EIC is
read back from `Area[...].code`.

entsoe-py is synchronous (pandas/XML), so each call runs in a worker thread,
bounded by a semaphore and paced under a token bucket (ENTSO-E allows ~400
req/min; we stay well under). Like the Energy-Charts path, one ranged sweep
builds the 48 h history and the live snapshot is its latest frame.

⚠️ Not verifiable end-to-end without a token. The networked orchestration is kept
thin; the zone graph and the pure transforms (`zone_area_map`, `modelled_borders`,
`series_points`, frame building) are unit-tested offline. The token is NEVER
logged. Sign convention matches the rest of the app: + = from_zone → to_zone.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import pandas as pd

from ..models import FlowEdge, HistoryFrame, LiveSnapshot, SnapshotHistory
from ..domain.zones import load_zones
from .base import live_from_history

log = logging.getLogger("fluxeu.sources.entsoe")

LOOKBACK_HOURS = 6
HISTORY_HOURS = 48
_GRANULARITY = {"prices": "bidding_zone", "flows": "bidding_zone"}

# ENTSO-E rate limit ~400 req/min (6.67/s). Stay comfortably under and bound
# concurrency — a 48 h zonal sweep is hundreds of calls.
MAX_CONCURRENCY = 4
RATE_PER_SEC = 5.0
BURST = 5


# --- zone graph from entsoe-py mappings (offline-testable) -----------------


def _area_candidates(zone_key: str) -> list[str]:
    """Area-name spellings to try for one of our zone keys (most specific first)."""
    out = [zone_key.replace("-", "_")]
    m = re.match(r"^([A-Za-z]+)(\d+)$", zone_key)  # NO2 -> NO_2, SE4 -> SE_4
    if m:
        out.append(f"{m.group(1)}_{m.group(2)}")
    out.append(zone_key)
    return out


@lru_cache(maxsize=1)
def zone_area_map() -> dict[str, str]:
    """{our zone key -> entsoe Area name}, verified against Area.__members__.

    Unknown keys are dropped with a warning rather than raising — the app must
    still boot on Energy-Charts if a future zone has no Area member yet."""
    from entsoe.mappings import Area

    members = set(Area.__members__)
    mapping: dict[str, str] = {}
    for z in load_zones():
        hit = next((c for c in _area_candidates(z.key) if c in members), None)
        if hit:
            mapping[z.key] = hit
        else:
            log.warning("no entsoe Area for zone %s (tried %s)", z.key, _area_candidates(z.key))
    return mapping


@lru_cache(maxsize=1)
def _area_to_zone() -> dict[str, str]:
    return {area: key for key, area in zone_area_map().items()}


@lru_cache(maxsize=1)
def modelled_borders() -> tuple[tuple[str, str], ...]:
    """Unique (a, b) zone-key border pairs from entsoe-py NEIGHBOURS, restricted
    to zones we model (virtual/aggregate Areas like DE_AT_LU, IT_NORD_FR and any
    non-modelled neighbour are dropped). Sorted, deduped."""
    from entsoe.mappings import NEIGHBOURS

    a2z = _area_to_zone()
    pairs: set[tuple[str, str]] = set()
    for area, neighbours in NEIGHBOURS.items():
        za = a2z.get(area)
        if za is None:
            continue
        for nb in neighbours:
            zb = a2z.get(nb)
            if zb is None or zb == za:
                continue
            pairs.add(tuple(sorted((za, zb))))  # type: ignore[arg-type]
    return tuple(sorted(pairs))


@lru_cache(maxsize=1)
def _zone_nodes() -> tuple:
    """One FlowNode per modelled zone (zone-level graph — the M6 unlock)."""
    from ..models import FlowNode

    nodes = []
    for z in load_zones():
        if z.key not in zone_area_map():
            continue
        nodes.append(
            FlowNode(code=z.key, name=z.name, centroid=z.centroid, zones=[z.key])
        )
    return tuple(nodes)


# --- pure transforms (offline-testable) ------------------------------------


def series_points(s: "pd.Series | None") -> list[tuple[int, float]]:
    """A tz-aware entsoe-py Series -> [(unix_seconds_utc, value)], NaNs dropped.

    entsoe-py returns a local-tz DatetimeIndex; we normalise to UTC (PLAN §8.1)."""
    if s is None or len(s) == 0:
        return []
    out: list[tuple[int, float]] = []
    for idx, v in s.items():
        if v is None or pd.isna(v):
            continue
        ts = idx
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        out.append((int(ts.timestamp()), round(float(v), 2)))
    return out


def _net_signed(
    a_to_b: list[tuple[int, float]], b_to_a: list[tuple[int, float]]
) -> list[tuple[int, float]]:
    """Two directional series -> one signed a→b series (a→b minus b→a) by ts."""
    acc: dict[int, float] = {}
    for t, v in a_to_b:
        acc[t] = acc.get(t, 0.0) + v
    for t, v in b_to_a:
        acc[t] = acc.get(t, 0.0) - v
    return sorted(acc.items())


# frame building mirrors energy_charts: prices step per MTU (floor lookup),
# never interpolated; flows/NTC are floored to the same timeline.
import bisect  # noqa: E402


def _step(series: dict) -> dict:
    out = {}
    for k, pts in series.items():
        s = sorted(pts)
        out[k] = ([p[0] for p in s], [p[1] for p in s])
    return out


def _floor(arr: tuple[list[int], list[float]], t: int) -> float | None:
    ts_list, val_list = arr
    i = bisect.bisect_right(ts_list, t) - 1
    return val_list[i] if i >= 0 else None


def build_history(
    price_series: dict[str, list[tuple[int, float]]],
    comm_series: dict[tuple[str, str], list[tuple[int, float]]],
    phys_series: dict[tuple[str, str], list[tuple[int, float]]],
    ntc_series: dict[tuple[str, str], list[tuple[int, float]]],
    start_ts: float,
    now_ts: float,
) -> list[HistoryFrame]:
    """Assemble zone-level frames (prices + signed flows + NTC + net positions).

    net_positions[z] = Σ inflows − Σ outflows of commercial flow (+ = net import),
    derived from the edges so the graph stays internally consistent."""
    price_step = _step(price_series)
    comm_step = _step(comm_series)
    phys_step = _step(phys_series)
    ntc_step = _step(ntc_series)

    grid: set[int] = set()
    for step in (price_step, comm_step, phys_step):
        for ts_list, _ in step.values():
            grid.update(ts_list)
    timeline = sorted(t for t in grid if start_ts <= t <= now_ts)

    pairs = sorted(set(comm_step) | set(phys_step) | set(ntc_step))
    frames: list[HistoryFrame] = []
    for t in timeline:
        prices = {z: v for z, arr in price_step.items() if (v := _floor(arr, t)) is not None}
        dt = datetime.fromtimestamp(t, tz=timezone.utc)
        edges: list[FlowEdge] = []
        net: dict[str, float] = {}
        for (a, b) in pairs:
            cm = _floor(comm_step[(a, b)], t) if (a, b) in comm_step else None
            pm = _floor(phys_step[(a, b)], t) if (a, b) in phys_step else None
            ntc = _floor(ntc_step[(a, b)], t) if (a, b) in ntc_step else None
            if cm is None and pm is None and ntc is None:
                continue
            edges.append(
                FlowEdge(
                    from_zone=a, to_zone=b, ts=dt,
                    commercial_mw=cm, physical_mw=pm, ntc_mw=ntc,
                    capacity_regime="NTC" if ntc is not None else "FLOW_BASED",
                )
            )
            if cm is not None:
                net[b] = net.get(b, 0.0) + cm
                net[a] = net.get(a, 0.0) - cm
        frames.append(
            HistoryFrame(
                ts=dt,
                prices=prices,
                net_positions={z: round(v, 1) for z, v in net.items()},
                edges=edges,
            )
        )
    return frames


# --- source ----------------------------------------------------------------


class _RateLimiter:
    """Async token bucket — paces entsoe-py calls under the ENTSO-E limit."""

    def __init__(self, rate: float, burst: int):
        self.rate = rate
        self.capacity = float(burst)
        self.tokens = float(burst)
        self.updated: float | None = None
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            if self.updated is None:
                self.updated = now
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
            self.updated = now
            if self.tokens < 1:
                await asyncio.sleep((1 - self.tokens) / self.rate)
                self.tokens = 0.0
                self.updated = loop.time()
            else:
                self.tokens -= 1


class EntsoeSource:
    name = "entsoe"

    def __init__(self, token: str) -> None:
        from entsoe import EntsoePandasClient

        self._client = EntsoePandasClient(api_key=token)
        self._limiter = _RateLimiter(RATE_PER_SEC, BURST)
        self._sem = asyncio.Semaphore(MAX_CONCURRENCY)

    async def _call(self, fn, *args) -> "pd.Series | None":
        """Run one synchronous entsoe-py query in a thread, paced + bounded.
        Returns None on any per-query failure (e.g. no data for a border) so a
        single gap never aborts the sweep."""
        async with self._sem:
            await self._limiter.acquire()
            try:
                return await asyncio.to_thread(fn, *args)
            except Exception as exc:  # noqa: BLE001 — incl. NoMatchingDataError
                log.debug("entsoe query failed (%s): %s", getattr(fn, "__name__", fn), exc)
                return None

    async def fetch_snapshot(self) -> LiveSnapshot:
        hist = await self._fetch_history(LOOKBACK_HOURS)
        live = live_from_history(hist)
        if live is not None:
            return live
        now = datetime.now(timezone.utc)
        return LiveSnapshot(
            ts=now, source=self.name, data_ts=None, granularity=_GRANULARITY,
            prices={}, nodes=list(_zone_nodes()), edges=[], net_positions={},
        )

    async def fetch_history(self) -> SnapshotHistory:
        return await self._fetch_history(HISTORY_HOURS)

    async def _fetch_history(self, hours: int) -> SnapshotHistory:
        now = datetime.now(timezone.utc)
        start_dt = now - timedelta(hours=hours)
        start = pd.Timestamp(start_dt)
        end = pd.Timestamp(now + timedelta(hours=1))
        area_of = zone_area_map()

        # prices per zone
        async def price_one(key: str, area: str):
            s = await self._call(self._client.query_day_ahead_prices, area, start, end)
            return key, series_points(s)

        price_results = await asyncio.gather(
            *(price_one(k, a) for k, a in area_of.items())
        )
        price_series = {k: pts for k, pts in price_results if pts}

        # flows + NTC per border (both directions -> signed a→b)
        async def border_one(a: str, b: str):
            aa, ab = area_of[a], area_of[b]
            comm_ab, comm_ba, phys_ab, phys_ba, ntc_ab = await asyncio.gather(
                self._call(self._scheduled, aa, ab, start, end),
                self._call(self._scheduled, ab, aa, start, end),
                self._call(self._client.query_crossborder_flows, aa, ab, start, end),
                self._call(self._client.query_crossborder_flows, ab, aa, start, end),
                self._call(self._client.query_net_transfer_capacity_dayahead, aa, ab, start, end),
            )
            return (
                (a, b),
                _net_signed(series_points(comm_ab), series_points(comm_ba)),
                _net_signed(series_points(phys_ab), series_points(phys_ba)),
                series_points(ntc_ab),
            )

        border_results = await asyncio.gather(
            *(border_one(a, b) for a, b in modelled_borders())
        )
        comm_series = {pair: c for pair, c, _, _ in border_results if c}
        phys_series = {pair: p for pair, _, p, _ in border_results if p}
        ntc_series = {pair: n for pair, _, _, n in border_results if n}

        frames = build_history(
            price_series, comm_series, phys_series, ntc_series,
            start_dt.timestamp(), now.timestamp(),
        )
        return SnapshotHistory(
            ts=now,
            source=self.name,
            granularity=_GRANULARITY,
            nodes=list(_zone_nodes()),
            start=start_dt,
            end=now,
            frames=frames,
        )

    def _scheduled(self, frm, to, start, end):
        # day-ahead scheduled commercial exchange (A09), the commercial flow
        return self._client.query_scheduled_exchanges(frm, to, start, end, dayahead=True)
