from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import interconnectors, zones

app = FastAPI(title="FluxEU API", version="0.1.0")

app.include_router(zones.router)
app.include_router(interconnectors.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "source": settings.active_source,
        "last_refresh": None,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
