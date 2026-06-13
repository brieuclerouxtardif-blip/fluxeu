from fastapi import APIRouter

from ..domain.interconnectors import load_interconnectors
from ..models import Interconnector

router = APIRouter(prefix="/api", tags=["interconnectors"])


@router.get("/interconnectors", response_model=list[Interconnector])
def get_interconnectors() -> list[Interconnector]:
    return list(load_interconnectors())
