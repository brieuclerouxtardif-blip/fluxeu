from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ENTSO-E Transparency Platform token (optional — Energy-Charts is the no-key default)
    entsoe_api: str | None = None

    # "auto" picks ENTSO-E when a token is present, Energy-Charts otherwise
    data_source: str = "auto"

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    duckdb_path: str = "data/fluxeu.duckdb"

    @property
    def active_source(self) -> str:
        if self.data_source != "auto":
            return self.data_source
        return "entsoe" if self.entsoe_api else "energy_charts"


settings = Settings()
