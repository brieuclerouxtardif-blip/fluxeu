"""Energy-Charts data source — default, no API key (Fraunhofer ISE).

https://api.energy-charts.info/ — JSON, free. Verified against the live API:
- /price?bzn=&start=&end=  -> {unix_seconds[], price[], unit}  (per bidding zone, EUR/MWh)
- /cbet|/cbpf?country=&start=&end=
      -> {unix_seconds[], countries:[{name: <English country>, data[]}]}  (per COUNTRY, GW)
      cbet = commercial exchange, cbpf = physical flow.
      Sign as returned: + = net import into queried country (a net exporter like
      France comes back all-negative). Cross-border values are in GW -> x1000 -> MW.

Prices are zone-level; flows are country-level (PLAN §2.1 / §8.5 limitation).
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, timezone

import httpx

from ..domain.countries import (
    CANONICAL,
    country_pair_regime,
    flow_query_countries,
    load_flow_nodes,
)
from ..models import FlowEdge, LiveSnapshot

BASE_URL = "https://api.energy-charts.info"
GW_TO_MW = 1000.0
LOOKBACK_HOURS = 6
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
        now = datetime.now(timezone.utc)
        now_ts = now.timestamp()
        start = (now - timedelta(hours=LOOKBACK_HOURS)).strftime("%Y-%m-%dT%H:%MZ")
        end = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%MZ")

        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
            sem = asyncio.Semaphore(MAX_CONCURRENCY)
            prices, price_ts = await self._fetch_prices(client, sem, start, end, now_ts)
            comm, comm_ts, net_pos = await self._fetch_flows(client, sem, "/cbet", start, end, now_ts)
            phys, phys_ts, _ = await self._fetch_flows(client, sem, "/cbpf", start, end, now_ts)

        flow_ts = max((t for t in (comm_ts, phys_ts) if t is not None), default=now)
        edges = self._build_edges(comm, phys, flow_ts)
        data_ts = max((t for t in (price_ts, comm_ts, phys_ts) if t is not None), default=now)
        return LiveSnapshot(
            ts=now,
            source=self.name,
            data_ts=data_ts,
            granularity={"prices": "bidding_zone", "flows": "country"},
            prices=prices,
            nodes=list(load_flow_nodes()),
            edges=edges,
            net_positions=net_pos,
        )

    async def _fetch_prices(self, client, sem, start, end, now_ts):
        async def one(key: str, bzn: str):
            d = await self._get(client, sem, "/price", {"bzn": bzn, "start": start, "end": end})
            if not d or "price" not in d:
                return key, None
            return key, _latest(d.get("unix_seconds", []), d.get("price", []), now_ts)

        results = await asyncio.gather(*(one(k, b) for k, b in ZONE_BZN.items()))
        prices: dict[str, float] = {}
        latest_ts: datetime | None = None
        for key, got in results:
            if got is None:
                continue
            ts, val = got
            prices[key] = round(val, 2)
            if latest_ts is None or ts > latest_ts:
                latest_ts = ts
        return prices, latest_ts

    async def _fetch_flows(self, client, sem, path, start, end, now_ts):
        """Return ({(a,b) sorted: signed MW a->b}, latest_ts, net_positions)."""
        async def one(cc: str):
            d = await self._get(client, sem, path, {"country": cc.lower(), "start": start, "end": end})
            return cc, d

        # query a vertex cover of the country graph (each call returns all of a
        # country's borders), not all 28 countries — the rate limit is tight.
        results = await asyncio.gather(*(one(cc) for cc in flow_query_countries()))
        contributions: dict[tuple[str, str], list[float]] = {}
        net_pos: dict[str, float] = {}
        latest_ts: datetime | None = None

        for cc, d in results:
            if not d:
                continue
            unix = d.get("unix_seconds", [])
            for entry in d.get("countries", []):
                name = entry.get("name", "")
                got = _latest(unix, entry.get("data", []), now_ts)
                if got is None:
                    continue
                ts, gw = got
                if latest_ts is None or ts > latest_ts:
                    latest_ts = ts
                if name == "sum":
                    net_pos[cc] = round(gw * GW_TO_MW, 1)  # + = net import
                    continue
                nb = NAME_TO_CC.get(name)
                if nb is None or nb not in _CANON or nb == cc:
                    continue
                # gw = net import into cc from nb -> flow cc->nb = -gw
                flow_cc_to_nb = -gw * GW_TO_MW
                a, b = sorted((cc, nb))
                signed = flow_cc_to_nb if a == cc else -flow_cc_to_nb
                contributions.setdefault((a, b), []).append(signed)

        merged = {pair: round(sum(v) / len(v), 1) for pair, v in contributions.items()}
        return merged, latest_ts, net_pos

    def _build_edges(self, comm: dict, phys: dict, ts: datetime) -> list[FlowEdge]:
        edges = []
        for (a, b) in sorted(set(comm) | set(phys)):
            edges.append(
                FlowEdge(
                    from_zone=a,
                    to_zone=b,
                    ts=ts,
                    commercial_mw=comm.get((a, b)),
                    physical_mw=phys.get((a, b)),
                    ntc_mw=None,  # Energy-Charts exposes no NTC — never fake one
                    capacity_regime=country_pair_regime(a, b),
                )
            )
        return edges
