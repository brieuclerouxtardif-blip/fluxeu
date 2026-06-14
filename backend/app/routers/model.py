"""Forward model (M7, PLAN §4.7). Reads the DuckDB history (sync `def` →
threadpool), so it doesn't 503; an unseen/empty zone returns an empty curve."""

from fastapi import APIRouter, Query

from ..domain.model import forward_curve
from ..models import ForwardCurve

router = APIRouter(prefix="/api", tags=["model"])

MAX_HORIZON = 168  # 7 days


@router.get("/model/forward", response_model=ForwardCurve)
def get_forward(
    zone: str = Query(...),
    horizon: int = Query(24, description="forecast horizon in hours"),
) -> ForwardCurve:
    """Seasonal-naive forward band (p10/p50/p90) + recent realized spot overlay."""
    return forward_curve(zone, max(1, min(horizon, MAX_HORIZON)))
