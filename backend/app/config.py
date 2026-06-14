from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # referential files (zones.json, interconnectors.json, zones.geojson);
    # docker-compose mounts ./data and overrides via DATA_DIR
    data_dir: Path = REPO_ROOT / "data"

    # ENTSO-E Transparency Platform token (optional — Energy-Charts is the no-key default)
    entsoe_api: str | None = None

    # "auto" picks ENTSO-E when a token is present, Energy-Charts otherwise
    data_source: str = "auto"

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # DuckDB analytics store (M6). Docker sets an absolute path on a writable
    # volume; the dev default is relative and anchored to the repo root below
    # (CWD-independent — uvicorn may run from backend/).
    duckdb_path: str = "data/fluxeu.duckdb"

    @property
    def active_source(self) -> str:
        if self.data_source != "auto":
            return self.data_source
        return "entsoe" if self.entsoe_api else "energy_charts"

    @property
    def duckdb_file(self) -> Path:
        p = Path(self.duckdb_path)
        return p if p.is_absolute() else REPO_ROOT / p


settings = Settings()
