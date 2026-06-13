"""Energy-Charts data source — default, no API key (Fraunhofer ISE).

https://api.energy-charts.info/ — JSON, free. Verified against the live API:
- /price?bzn=&start=&end=  -> {unix_seconds[], price[], unit}  (per bidding zone, EUR/MWh)
- /cbet|/cbpf?country=&start=&end=
      -> {unix_seconds[], countries:[{name: <English country>, data[]}]}  (per COUNTRY, GW)
      cbet = commercial exchange, cbpf = physical flow.
      Sign as returned: + = net import into queried country (a net exporter like
      France comes back all-negative). Cross-border values are in GW -> x1000 -> MW.

Prices are zone-level; flows are country-level (PLAN §2.1 / §8.5 limitation).

One sweep returns a whole time RANGE per call, so a 48 h history costs the same
as a single "latest" snapshot — the M4 scrubber reuses this sweep (no separate
backfill job). The live snapshot is just the latest frame (see base.live_from_history).
"""

from __future__ import annotations

import asyncio
import bisect
import random
from datetime import datetime, timedelta, timezone

import httpx

from ..domain.countries import (
    CANONICAL,
    country_pair_regime,
    flow_query_countries,
    load_flow_nodes,
)
from ..models import FlowEdge, HistoryFrame, LiveSnapshot, SnapshotHistory
from .base import live_from_history

BASE_URL = "https://api.energy-charts.info"
GW_TO_MW = 1000.0
LOOKBACK_HOURS = 6   # window for the live snapshot's latest point
HISTORY_HOURS = 48   # window for the scrubber (same call count, wider range)
_GRANULARITY = {"prices": "bidding_zone", "flows": "country"}
# Energy-Charts rate limit, measured live: a small token bucket that refills
# ~1 token / 7.5 s, and a 429 trips a punitive hold that ESCALATES under
# sustained load. So we SERIALIZE (concurrency=1), pace at the refill rate, and
# take no head burst (a burst drains the bucket and rides the 429 edge). Even
# then a full snapshot (~74 calls) takes ~15-25 min — that's a source limit, not
# a tuning bug. The snapshot is therefore persisted (store/cache.py) and
# refreshed well off-cycle so the slow build never blocks a request.
MAX_CONCURRENCY = 1
MAX_RETRIES = 4  # don't hammer a penalised server — that escalates its hold
RATE_PER_SEC = 0.13  # ~1 request / 7.7 s — matches the server's refill rate
BURST = 1  # no head burst: a burst drains the server bucket and rides the 429 edge
RETRY_WAIT = 8.0

# our zone key -> Energy-Charts bzn string for /price (their naming, not EIC).
# GB/IE have no Energy-Charts day-ahead price (GB decoupled, separate market).
ZONE_BZN: dict[str, str] = {
    "FR": "FR", "DE-LU": "DE-LU", "BE": "BE", "NL": "NL", "AT": "AT",
    "PL": "PL", "CZ": "CZ", "SK": "SK", "HU": "HU", "SI": "SI", "HR": "HR",
    "RO": "RO", "CH": "CH", "ES": "ES", "PT": "PT", "GR": "GR", "BG": "BG",
    "RS": "RS", "FI": "FI", "EE": "EE", "LV": "LV", "LT": "LT",
    "IT-NORD": "IT-North", "IT-CNOR": "IT-Centre-North",
    "IT-CSUD": "IT-Centre-South", "IT-SUD": "IT-South",
    "IT-CALA": "IT-Calabria", "IT-SICI": "IT-Sicily", "IT-SARD": "IT-Sardinia",
    "NO1": "NO1", "NO2": "NO2", "NO3": "NO3", "NO4": "NO4", "NO5": "NO5",
    "SE1": "SE1", "SE2": "SE2", "SE3": "SE3", "SE4": "SE4",
    "DK1": "DK1", "DK2": "DK2",
}

# Energy-Charts returns neighbours by full English name -> ISO-2 (canonical).
# Luxembourg folds into DE (shared DE-LU zone); non-modelled neighbours map to
# codes absent from CANONICAL and are dropped.
NAME_TO_CC: dict[str, str] = {
    "Austria": "AT", "Belgium": "BE", "Bulgaria": "BG", "Switzerland": "CH",
    "Czech Republic": "CZ", "Czechia": "CZ", "Germany": "DE", "Denmark": "DK",
    "Estonia": "EE", "Spain": "ES", "Finland": "FI", "France": "FR",
    "United Kingdom": "GB", "Great Britain": "GB", "Greece": "GR",
    "Croatia": "HR", "Hungary": "HU", "Ireland": "IE", "Italy": "IT",
    "Lithuania": "LT", "Luxembourg": "DE", "Latvia": "LV", "Netherlands": "NL",
    "Norway": "NO", "Poland": "PL", "Portugal": "PT", "Romania": "RO",
    "Serbia": "RS", "Sweden": "SE", "Slovenia": "SI", "Slovakia": "SK",
    "Montenegro": "ME", "North Macedonia": "MK", "Bosnia and Herzegovina": "BA",
    "Albania": "AL", "Ukraine": "UA",
}

_CANON = set(CANONICAL)


class _RateLimiter:
    """Async token bucket — paces requests under the Energy-Charts limit."""

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


def _latest(unix_seconds: list[int], values: list, now_ts: float) -> tuple[datetime, float] | None:
    """Return (ts_utc, value) at the most recent timestamp <= now with a non-null
    value; fall back to the last non-null value if all lie in the future."""
    best: tuple[int, float] | None = None
    fallback: tuple[int, float] | None = None
    for t, v in zip(unix_seconds, values):
        if v is None:
            continue
        fallback = (t, v)
        if t <= now_ts and (best is None or t > best[0]):
            best = (t, v)
    chosen = best or fallback
    if chosen is None:
        return None
    return datetime.fromtimestamp(chosen[0], tz=timezone.utc), float(chosen[1])


class EnergyChartsSource:
    name = "energy_charts"

    def __init__(self) -> None:
        self._limiter = _RateLimiter(RATE_PER_SEC, BURST)

    async def _get(self, client: httpx.AsyncClient, sem: asyncio.Semaphore, path: str, params: dict) -> dict | None:
        """GET, paced by the token bucket; fixed retry on 429/5xx. None on give-up."""
        async with sem:
            for _attempt in range(MAX_RETRIES):
                await self._limiter.acquire()
                try:
                    r = await client.get(path, params=params)
                except httpx.HTTPError:
                    await asyncio.sleep(RETRY_WAIT + random.random())
                    continue
                if r.status_code == 200:
                    return r.json()
                if r.status_code in (400, 404):
                    return None  # bzn/country unsupported or no data — expected
                if r.status_code == 429 or r.status_code >= 500:
                    retry_after = r.headers.get("Retry-After")
                    wait = max(float(retry_after), RETRY_WAIT) if retry_after else RETRY_WAIT
                    await asyncio.sleep(wait + random.random())
                    continue
                return None
        return None

    async def fetch_snapshot(self) -> LiveSnapshot:
        """Live map snapshot = latest frame of a short-window history."""
        hist = await self._fetch_history(LOOKBACK_HOURS)
        live = live_from_history(hist)
        if live is not None:
            return live
        now = datetime.now(timezone.utc)
        return LiveSnapshot(
            ts=now, source=self.name, data_ts=None, granularity=_GRANULARITY,
            prices={}, nodes=list(load_flow_nodes()), edges=[], net_positions={},
        )

    async def fetch_history(self) -> SnapshotHistory:
        """48 h of frames for the scrubber — same call count as a live snapshot."""
        return await self._fetch_history(HISTORY_HOURS)

    async def _fetch_history(self, hours: int) -> SnapshotHistory:
        now = datetime.now(timezone.utc)
        now_ts = now.timestamp()
        start_dt = now - timedelta(hours=hours)
        start = start_dt.strftime("%Y-%m-%dT%H:%MZ")
        end = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%MZ")

        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
            sem = asyncio.Semaphore(MAX_CONCURRENCY)
            price_series = await self._fetch_price_series(client, sem, start, end)
            comm_series, net_series = await self._fetch_flow_series(client, sem, "/cbet", start, end)
            phys_series, _ = await self._fetch_flow_series(client, sem, "/cbpf", start, end)

        frames = _build_frames(price_series, comm_series, phys_series, net_series, start_dt.timestamp(), now_ts)
        return SnapshotHistory(
            ts=now,
            source=self.name,
            granularity=_GRANULARITY,
            nodes=list(load_flow_nodes()),
            start=start_dt,
            end=now,
            frames=frames,
        )

    async def _fetch_price_series(self, client, sem, start, end) -> dict[str, list[tuple[int, float]]]:
        async def one(key: str, bzn: str):
            d = await self._get(client, sem, "/price", {"bzn": bzn, "start": start, "end": end})
            if not d or "price" not in d:
                return key, None
            pts = [
                (int(t), round(float(v), 2))
                for t, v in zip(d.get("unix_seconds", []), d.get("price", []))
                if v is not None
            ]
            return key, pts

        results = await asyncio.gather(*(one(k, b) for k, b in ZONE_BZN.items()))
        return {k: pts for k, pts in results if pts}

    async def _fetch_flow_series(self, client, sem, path, start, end):
        """Return ({(a,b) sorted: [(ts, signed MW a->b)]}, {country: [(ts, net MW)]})."""
        async def one(cc: str):
            d = await self._get(client, sem, path, {"country": cc.lower(), "start": start, "end": end})
            return cc, d

        # query a vertex cover of the country graph (each call returns all of a
        # country's borders), not all 28 countries — the rate limit is tight.
        results = await asyncio.gather(*(one(cc) for cc in flow_query_countries()))
        contributions: dict[tuple[str, str], dict[int, list[float]]] = {}
        net: dict[str, dict[int, float]] = {}

        for cc, d in results:
            if not d:
                continue
            unix = d.get("unix_seconds", [])
            for entry in d.get("countries", []):
                name = entry.get("name", "")
                data = entry.get("data", [])
                if name == "sum":
                    for t, gw in zip(unix, data):
                        if gw is None:
                            continue
                        net.setdefault(cc, {})[int(t)] = round(gw * GW_TO_MW, 1)  # + = net import
                    continue
                nb = NAME_TO_CC.get(name)
                if nb is None or nb not in _CANON or nb == cc:
                    continue
                a, b = sorted((cc, nb))
                for t, gw in zip(unix, data):
                    if gw is None:
                        continue
                    # gw = net import into cc from nb -> flow cc->nb = -gw
                    flow_cc_to_nb = -gw * GW_TO_MW
                    signed = flow_cc_to_nb if a == cc else -flow_cc_to_nb
                    contributions.setdefault((a, b), {}).setdefault(int(t), []).append(signed)

        merged = {
            pair: sorted((t, round(sum(v) / len(v), 1)) for t, v in tsmap.items())
            for pair, tsmap in contributions.items()
        }
        net_out = {cc: sorted(d.items()) for cc, d in net.items()}
        return merged, net_out


# --- frame building (step semantics) --------------------------------------
# Day-ahead prices are piecewise-constant per MTU, so frames STEP (floor lookup),
# never interpolate — interpolating would invent prices that never cleared.


def _as_step(series: dict) -> dict:
    """{key: [(ts, val)]} -> {key: (ts_list, val_list)} sorted ascending, for bisect."""
    out = {}
    for k, pts in series.items():
        s = sorted(pts)
        out[k] = ([p[0] for p in s], [p[1] for p in s])
    return out


def _floor(arr: tuple[list[int], list[float]], t: int) -> float | None:
    """Value at the most recent ts <= t (None if t precedes the series)."""
    ts_list, val_list = arr
    i = bisect.bisect_right(ts_list, t) - 1
    return val_list[i] if i >= 0 else None


def _build_frames(price_series, comm_series, phys_series, net_series, start_ts, now_ts) -> list[HistoryFrame]:
    price_step = _as_step(price_series)
    comm_step = _as_step(comm_series)
    phys_step = _as_step(phys_series)
    net_step = _as_step(net_series)

    grid: set[int] = set()
    for step in (price_step, comm_step, phys_step, net_step):
        for ts_list, _ in step.values():
            grid.update(ts_list)
    timeline = sorted(t for t in grid if start_ts <= t <= now_ts)

    pairs = sorted(set(comm_step) | set(phys_step))
    frames: list[HistoryFrame] = []
    for t in timeline:
        prices = {z: v for z, arr in price_step.items() if (v := _floor(arr, t)) is not None}
        net = {cc: v for cc, arr in net_step.items() if (v := _floor(arr, t)) is not None}
        dt = datetime.fromtimestamp(t, tz=timezone.utc)
        edges: list[FlowEdge] = []
        for (a, b) in pairs:
            cm = _floor(comm_step[(a, b)], t) if (a, b) in comm_step else None
            pm = _floor(phys_step[(a, b)], t) if (a, b) in phys_step else None
            if cm is None and pm is None:
                continue
            edges.append(
                FlowEdge(
                    from_zone=a, to_zone=b, ts=dt,
                    commercial_mw=cm, physical_mw=pm,
                    ntc_mw=None,  # Energy-Charts exposes no NTC — never fake one
                    capacity_regime=country_pair_regime(a, b),
                )
            )
        frames.append(HistoryFrame(ts=dt, prices=prices, net_positions=net, edges=edges))
    return frames
