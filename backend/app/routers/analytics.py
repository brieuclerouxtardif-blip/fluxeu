"""Analytics over the durable DuckDB history (M6, PLAN §4.6 / API table §3.5).

Unlike the live/metrics routers, these read the DuckDB *accumulation* store, not
the warming snapshot cache — so they never 503. Early on the store is near-empty
(only what's been ingested so far); GET /api/analytics/coverage tells the front
how much history exists. Handlers are sync `def` so FastAPI runs them in its
threadpool, keeping the (blocking) DuckDB calls off the event loop.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from ..config import settings
from ..models import (
    CorrelationMatrix,
    Coverage,
    DurationCurve,
    DurationPoint,
    FlowSeriesPoint,
    FlowSeriesResponse,
    PriceSeriesResponse,
    SeriesPoint,
    ZoneSeries,
)
from ..store import duckdb_store

router = APIRouter(prefix="/api", tags=["analytics"])

DEFAULT_HOURS = 720  # 30 days — where a DB earns its place over the 48 h cache
MAX_HOURS = 24 * 366  # ENTSO-E caps a query at 1 year; generous for the store too


def _clamp(hours: int) -> int:
    return max(1, min(hours, MAX_HOURS))


def _parse_zones(zones: str | None) -> list[str]:
    if not zones:
        return []
    # dedupe, preserve order
    seen: dict[str, None] = {}
    for z in zones.split(","):
        z = z.strip()
        if z:
            seen.setdefault(z, None)
    return list(seen)


def _window(hours: int) -> tuple[datetime, datetime]:
    end = datetime.now(timezone.utc)
    return end - timedelta(hours=hours), end


@router.get("/analytics/coverage", response_model=Coverage)
def get_coverage() -> Coverage:
    """How much durable history has accumulated (rows, span, zones)."""
    c = duckdb_store.coverage()
    return Coverage(**c, source=settings.active_source)


@router.get("/prices", response_model=PriceSeriesResponse)
def get_prices(
    zones: str = Query(..., description="comma-separated zone keys, e.g. FR,DE-LU"),
    hours: int = Query(DEFAULT_HOURS),
) -> PriceSeriesResponse:
    """Zonal day-ahead price series over the last `hours` (from DuckDB)."""
    hours = _clamp(hours)
    start, end = _window(hours)
    series = duckdb_store.price_series(_parse_zones(zones), hours)
    return PriceSeriesResponse(
        start=start,
        end=end,
        hours=hours,
        zones=[
            ZoneSeries(zone=z, points=[SeriesPoint(ts=t, value=v) for t, v in pts])
            for z, pts in series.items()
        ],
    )


@router.get("/flows", response_model=FlowSeriesResponse)
def get_flows(
    from_zone: str = Query(..., alias="from"),
    to_zone: str = Query(..., alias="to"),
    hours: int = Query(DEFAULT_HOURS),
) -> FlowSeriesResponse:
    """Cross-border flow series oriented from -> to (+ = that direction)."""
    hours = _clamp(hours)
    start, end = _window(hours)
    pts = duckdb_store.flow_series(from_zone, to_zone, hours)
    return FlowSeriesResponse(
        from_zone=from_zone,
        to_zone=to_zone,
        start=start,
        end=end,
        hours=hours,
        points=[FlowSeriesPoint(ts=t, commercial_mw=c, physical_mw=p) for t, c, p in pts],
    )


@router.get("/analytics/duration", response_model=DurationCurve)
def get_duration(
    zone: str = Query(...),
    hours: int = Query(DEFAULT_HOURS),
) -> DurationCurve:
    """Price duration curve for a zone — sorted high→low with % of time at/above."""
    hours = _clamp(hours)
    pts = duckdb_store.duration_curve(zone, hours)
    return DurationCurve(
        zone=zone,
        hours=hours,
        n=len(pts),
        points=[DurationPoint(pct=p, eur_mwh=v) for p, v in pts],
    )


@router.get("/analytics/correlation", response_model=CorrelationMatrix)
def get_correlation(
    zones: str = Query(..., description="comma-separated zone keys (>=2)"),
    hours: int = Query(DEFAULT_HOURS),
) -> CorrelationMatrix:
    """Pearson correlation matrix of zonal prices (DuckDB corr(), aligned ts)."""
    hours = _clamp(hours)
    present, matrix, n = duckdb_store.correlation(_parse_zones(zones), hours)
    return CorrelationMatrix(zones=present, matrix=matrix, hours=hours, n_timestamps=n)


@router.get("/export.csv")
def export_csv(
    table: str = Query("prices", pattern="^(prices|flows)$"),
    hours: int = Query(DEFAULT_HOURS),
    zones: str | None = Query(None),
) -> PlainTextResponse:
    """Download accumulated history as CSV (UTC timestamps)."""
    hours = _clamp(hours)
    try:
        df = duckdb_store.export_frame(table, hours, _parse_zones(zones) or None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filename = f"fluxeu_{table}_{hours}h.csv"
    return PlainTextResponse(
        df.to_csv(index=False),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
