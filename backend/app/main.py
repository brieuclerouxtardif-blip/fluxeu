from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .jobs.scheduler import shutdown_scheduler, start_scheduler
from .routers import interconnectors, snapshot, zones
from .store import cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()  # warms the snapshot cache + schedules refreshes
    yield
    shutdown_scheduler()


app = FastAPI(title="FluxEU API", version="0.1.0", lifespan=lifespan)

app.include_router(zones.router)
app.include_router(interconnectors.router)
app.include_router(snapshot.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    last = cache.last_refresh()
    return {
        "status": "ok",
        "source": settings.active_source,
        "last_refresh": last.isoformat() if last else None,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
