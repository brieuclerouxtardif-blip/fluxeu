"""Durable long-history analytics store (M6) — DuckDB.

The JSON cache (store/cache.py) holds only the latest ~48 h window the map and
scrubber need. DuckDB is the *accumulation* substrate: every refresh sweep is
upserted here, so history grows past 48 h and the SQL-shaped analytics that earn
a DB — price **duration curves**, zonal **correlation matrices**, multi-week
series, CSV export (PLAN §4.6) — have something to run on. It is source-agnostic:
it accumulates whatever the active DataSource produces (Energy-Charts now, richer
zone-level ENTSO-E data once the token lands).

Concurrency: one process-wide connection guarded by a lock. The scheduler writes
(off the event loop, via asyncio.to_thread) and the sync analytics endpoints read
(in FastAPI's threadpool) — all serialised through the lock. Contention is nil at
this cadence (hourly ingest, occasional query).

All timestamps are stored UTC (TIMESTAMPTZ); display-tz conversion is the front's
job (PLAN §8.1).
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pandas as pd

from ..config import settings
from ..models import SnapshotHistory

log = logging.getLogger("fluxeu.duckdb")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    zone     VARCHAR     NOT NULL,
    ts       TIMESTAMPTZ NOT NULL,
    eur_mwh  DOUBLE      NOT NULL,
    PRIMARY KEY (zone, ts)
);
CREATE TABLE IF NOT EXISTS flows (
    from_zone     VARCHAR     NOT NULL,
    to_zone       VARCHAR     NOT NULL,
    ts            TIMESTAMPTZ NOT NULL,
    commercial_mw DOUBLE,
    physical_mw   DOUBLE,
    PRIMARY KEY (from_zone, to_zone, ts)
);
"""

_lock = threading.Lock()
_conn: duckdb.DuckDBPyConnection | None = None
_db_path: str | None = None  # overridable for tests (e.g. ":memory:")


def use_database(path: str | Path) -> None:
    """Point the store at a specific DB file (or ':memory:'). For tests."""
    global _conn, _db_path
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None
        _db_path = str(path)


def _get_conn() -> duckdb.DuckDBPyConnection:
    global _conn
    if _conn is None:
        path = _db_path if _db_path is not None else str(settings.duckdb_file)
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        _conn = duckdb.connect(path)
        _conn.execute(_SCHEMA)
        log.info("duckdb opened at %s", path)
    return _conn


def _window(hours: int) -> tuple[datetime, datetime]:
    end = datetime.now(timezone.utc)
    return end - timedelta(hours=hours), end


def _in_clause(values: list[str]) -> tuple[str, list[str]]:
    """('(?, ?, ...)', values) for a parameterised IN list."""
    return "(" + ", ".join("?" for _ in values) + ")", list(values)


# --- ingestion -------------------------------------------------------------


def ingest_history(hist: SnapshotHistory) -> int:
    """Upsert every frame's prices + flows. Idempotent (PK = INSERT OR REPLACE),
    so re-ingesting overlapping sweeps just refreshes the rows. Returns the
    number of price rows written."""
    price_rows: list[tuple[str, datetime, float]] = []
    flow_rows: list[tuple[str, str, datetime, float | None, float | None]] = []
    for f in hist.frames:
        for zone, v in f.prices.items():
            price_rows.append((zone, f.ts, float(v)))
        for e in f.edges:
            flow_rows.append(
                (e.from_zone, e.to_zone, e.ts, e.commercial_mw, e.physical_mw)
            )

    with _lock:
        conn = _get_conn()
        if price_rows:
            df = pd.DataFrame(price_rows, columns=["zone", "ts", "eur_mwh"])
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
            conn.register("_in_prices", df)
            conn.execute(
                "INSERT OR REPLACE INTO prices SELECT zone, ts, eur_mwh FROM _in_prices"
            )
            conn.unregister("_in_prices")
        if flow_rows:
            df = pd.DataFrame(
                flow_rows,
                columns=["from_zone", "to_zone", "ts", "commercial_mw", "physical_mw"],
            )
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
            conn.register("_in_flows", df)
            conn.execute(
                "INSERT OR REPLACE INTO flows "
                "SELECT from_zone, to_zone, ts, commercial_mw, physical_mw FROM _in_flows"
            )
            conn.unregister("_in_flows")
    return len(price_rows)


# --- queries ---------------------------------------------------------------


def coverage() -> dict:
    """How much history has accumulated — drives the front's range hints."""
    with _lock:
        conn = _get_conn()
        p = conn.execute(
            "SELECT count(*), min(ts), max(ts), count(DISTINCT zone) FROM prices"
        ).fetchone()
        zones = [
            r[0] for r in conn.execute("SELECT DISTINCT zone FROM prices ORDER BY zone").fetchall()
        ]
        fcount = conn.execute("SELECT count(*) FROM flows").fetchone()[0]
    return {
        "price_rows": p[0] or 0,
        "flow_rows": fcount or 0,
        "start": p[1],
        "end": p[2],
        "zones": zones,
    }


def price_series(zones: list[str], hours: int) -> dict[str, list[tuple[datetime, float]]]:
    """{zone: [(ts, eur_mwh)]} over the last `hours`, ascending by ts."""
    if not zones:
        return {}
    start, end = _window(hours)
    clause, params = _in_clause(zones)
    with _lock:
        conn = _get_conn()
        rows = conn.execute(
            f"SELECT zone, ts, eur_mwh FROM prices "
            f"WHERE zone IN {clause} AND ts >= ? AND ts <= ? ORDER BY zone, ts",
            [*params, start, end],
        ).fetchall()
    out: dict[str, list[tuple[datetime, float]]] = {z: [] for z in zones}
    for zone, ts, v in rows:
        out.setdefault(zone, []).append((ts, v))
    return {z: pts for z, pts in out.items() if pts}


def flow_series(
    from_zone: str, to_zone: str, hours: int
) -> list[tuple[datetime, float | None, float | None]]:
    """Border series oriented from_zone -> to_zone (+ = that direction). Flows are
    stored on a canonical pair; if stored reversed we negate to honour the
    requested orientation (PLAN §8.3 sign convention)."""
    start, end = _window(hours)
    with _lock:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT ts, commercial_mw, physical_mw FROM flows "
            "WHERE from_zone = ? AND to_zone = ? AND ts >= ? AND ts <= ? ORDER BY ts",
            [from_zone, to_zone, start, end],
        ).fetchall()
        if rows:
            return [(ts, c, p) for ts, c, p in rows]
        rev = conn.execute(
            "SELECT ts, commercial_mw, physical_mw FROM flows "
            "WHERE from_zone = ? AND to_zone = ? AND ts >= ? AND ts <= ? ORDER BY ts",
            [to_zone, from_zone, start, end],
        ).fetchall()
    return [
        (ts, -c if c is not None else None, -p if p is not None else None)
        for ts, c, p in rev
    ]


def duration_curve(zone: str, hours: int) -> list[tuple[float, float]]:
    """Price duration curve: [(pct_of_time, eur_mwh)] sorted by price desc, where
    pct = share of the window at or above that price. Pure SQL (window funcs)."""
    start, end = _window(hours)
    with _lock:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT 100.0 * row_number() OVER (ORDER BY eur_mwh DESC) "
            "         / count(*) OVER () AS pct, "
            "       eur_mwh "
            "FROM prices WHERE zone = ? AND ts >= ? AND ts <= ? "
            "ORDER BY eur_mwh DESC",
            [zone, start, end],
        ).fetchall()
    return [(round(pct, 3), v) for pct, v in rows]


def correlation(zones: list[str], hours: int) -> tuple[list[str], list[list[float | None]], int]:
    """Pearson correlation of zonal prices on aligned timestamps, via DuckDB's
    corr() aggregate (DoD §4.6: correlations computed in SQL). Returns
    (ordered zones present, matrix, n_aligned_timestamps)."""
    if len(zones) < 2:
        return [], [], 0
    start, end = _window(hours)
    clause, params = _in_clause(zones)
    with _lock:
        conn = _get_conn()
        # zones actually present in the window, preserving the requested order
        present_set = {
            r[0]
            for r in conn.execute(
                f"SELECT DISTINCT zone FROM prices "
                f"WHERE zone IN {clause} AND ts >= ? AND ts <= ?",
                [*params, start, end],
            ).fetchall()
        }
        present = [z for z in zones if z in present_set]
        if len(present) < 2:
            return present, [], 0
        pclause, pparams = _in_clause(present)
        pairs = conn.execute(
            f"SELECT a.zone, b.zone, corr(a.eur_mwh, b.eur_mwh) "
            f"FROM prices a JOIN prices b ON a.ts = b.ts "
            f"WHERE a.ts >= ? AND a.ts <= ? "
            f"  AND a.zone IN {pclause} AND b.zone IN {pclause} "
            f"GROUP BY a.zone, b.zone",
            [start, end, *pparams, *pparams],
        ).fetchall()
        n = conn.execute(
            "SELECT count(*) FROM ("
            "  SELECT ts FROM prices WHERE zone = ? AND ts >= ? AND ts <= ?"
            ")",
            [present[0], start, end],
        ).fetchone()[0]
    idx = {z: i for i, z in enumerate(present)}
    matrix: list[list[float | None]] = [[None] * len(present) for _ in present]
    for za, zb, c in pairs:
        matrix[idx[za]][idx[zb]] = None if c is None else round(c, 4)
    return present, matrix, int(n or 0)


def export_frame(table: str, hours: int, zones: list[str] | None = None) -> pd.DataFrame:
    """A DataFrame for CSV export. table in {'prices','flows'}; optional zone
    filter (prices: zone; flows: either endpoint)."""
    if table not in ("prices", "flows"):
        raise ValueError(f"unknown table {table!r}")
    start, end = _window(hours)
    with _lock:
        conn = _get_conn()
        if table == "prices":
            sql = "SELECT zone, ts, eur_mwh FROM prices WHERE ts >= ? AND ts <= ?"
            params: list = [start, end]
            if zones:
                clause, zp = _in_clause(zones)
                sql += f" AND zone IN {clause}"
                params += zp
            sql += " ORDER BY ts, zone"
        else:
            sql = (
                "SELECT from_zone, to_zone, ts, commercial_mw, physical_mw "
                "FROM flows WHERE ts >= ? AND ts <= ?"
            )
            params = [start, end]
            if zones:
                clause, zp = _in_clause(zones)
                sql += f" AND (from_zone IN {clause} OR to_zone IN {clause})"
                params += zp + zp
            sql += " ORDER BY ts, from_zone, to_zone"
        return conn.execute(sql, params).df()
