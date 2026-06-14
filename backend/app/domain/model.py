"""Forward price model (M7, PLAN §4.7) — self-contained baseline.

A **seasonal-naive** forward curve fit on the DuckDB history: the price's
hour-of-day distribution (Europe/Brussels, so the daily peak/trough land on the
right clock hours), as p10/p50/p90 bands, projected over the requested horizon.
The realized spot of the last 48 h is returned alongside so the front can overlay
modelled-vs-cleared (the §4.7 deliverable).

This is deliberately a placeholder for the real merit-order / `peakero-forecaster`
forward model: swap `_hod_bands` / the projection for those and the API contract
(`ForwardCurve`) and the overlay UI stay the same. Hours with too little history
fall back to the global distribution. Pandas does the tz conversion (no extra
tz-data dependency — same stack the ENTSO-E source already uses).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from ..models import ForwardCurve, ForwardPoint, RealizedPoint
from ..store import duckdb_store

DISPLAY_TZ = "Europe/Brussels"
HISTORY_HOURS = 720  # 30 days of fit data when available
REALIZED_HOURS = 48
MIN_TOTAL = 6  # below this there's not enough to model
MIN_PER_HOUR = 2  # else fall back to the global distribution for that hour
METHOD = "seasonal_naive_hod"


def _pct(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolation percentile (q in [0,1]) — robust for small n."""
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    idx = q * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _bands(vals: list[float]) -> tuple[float, float, float]:
    s = sorted(vals)
    return round(_pct(s, 0.10), 2), round(_pct(s, 0.50), 2), round(_pct(s, 0.90), 2)


def _hod_bands(
    points: list[tuple[datetime, float]],
) -> tuple[dict[int, tuple[float, float, float]], tuple[float, float, float]]:
    """Per-Brussels-hour (p10,p50,p90) + a global fallback band."""
    by_hour: dict[int, list[float]] = {}
    allv: list[float] = []
    for ts, v in points:
        hour = pd.Timestamp(ts).tz_convert(DISPLAY_TZ).hour
        by_hour.setdefault(hour, []).append(v)
        allv.append(v)
    glob = _bands(allv)
    hod = {
        h: (_bands(vs) if len(vs) >= MIN_PER_HOUR else glob)
        for h, vs in by_hour.items()
    }
    return hod, glob


def forward_curve(zone: str, horizon_hours: int) -> ForwardCurve:
    now = datetime.now(timezone.utc)
    points = duckdb_store.price_series([zone], HISTORY_HOURS).get(zone, [])
    realized = [
        RealizedPoint(ts=ts, eur_mwh=v)
        for ts, v in points
        if ts >= now - timedelta(hours=REALIZED_HOURS)
    ]
    if len(points) < MIN_TOTAL:
        return ForwardCurve(
            zone=zone, generated_ts=now, method=METHOD,
            n_history=len(points), forward=[], realized=realized,
        )

    hod, glob = _hod_bands(points)
    start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    forward: list[ForwardPoint] = []
    for h in range(horizon_hours):
        ts = start + timedelta(hours=h)
        hour = pd.Timestamp(ts).tz_convert(DISPLAY_TZ).hour
        p10, p50, p90 = hod.get(hour, glob)
        forward.append(ForwardPoint(ts=ts, p10=p10, p50=p50, p90=p90))

    return ForwardCurve(
        zone=zone, generated_ts=now, method=METHOD,
        n_history=len(points), forward=forward, realized=realized,
    )
