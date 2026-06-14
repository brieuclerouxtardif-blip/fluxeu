---
tags: [architecture, backend, fluxeu]
status: stable
updated: 2026-06-14
---

# 🐍 Backend (FastAPI)

Racine : `backend/app/`. Entrée : `backend/app/main.py` (app + CORS + lifespan
qui démarre le scheduler + monte les routers). Tests : `backend/tests/` (pytest, **53 passés**).

## Couches

### `sources/` — accès données ([[Sources de données]])
- `base.py` — Protocol `DataSource` (`fetch_snapshot`, `fetch_history`) + `live_from_history()`.
- `energy_charts.py` — impl httpx (défaut, sans clé, sweep pacé).
- `entsoe.py` — impl `entsoe-py` (token-gated, M6) → [[ENTSO-E]].
- `registry.py` — `get_source()` : auto-select entsoe si token, sinon fallback Energy-Charts.

### `domain/` — logique métier pure
- `zones.py` — chargement `Area`/`NEIGHBOURS` + centroïdes → `load_zones()`, `load_zones_geojson()`.
- `interconnectors.py` — graphe frontières + métadonnées DC → `load_interconnectors()`.
- `countries.py` — `ZONE_TO_CC` (zone → pays ISO-2).
- `metrics.py` (M5) — `border_spreads`, `congestion_snapshot`, `convergence_series`, `sankey_snapshot` (bipartite). Constantes : `CONVERGED_EUR_MWH=0.5`, `MIN_FLOW_MW=1.0`.
- `alerts.py` (M7) — `compute_alerts()` → `AlertsSnapshot`. Voir [[Jalon M7]].
- `model.py` (M7) — `forward_curve()` seasonal-naive depuis [[DuckDB]]. Voir [[Jalon M7]].

### `store/` — persistance
- `cache.py` — cache live + 48 h (JSON disque), `last_refresh()`.
- `duckdb_store.py` (M6) — store analytique durable → [[DuckDB]].

### `jobs/`
- `scheduler.py` — APScheduler : 1 job refresh 60 min (sweep → cache + DuckDB ingest) + seed boot.

### `routers/` — surface HTTP ([[API]])
`zones` · `interconnectors` · `snapshot` · `metrics` · `analytics` (M6) · `alerts` (M7) · `model` (M7).
Handlers analytics en **`def` sync** (threadpool) ; le reste async. `/api/health` inline dans `main.py`.

### `models.py` — tous les Pydantic v2 (miroir TS dans `frontend/src/types.ts`). `config.py` — settings `.env` (`ENTSOE_API`, `DATA_SOURCE`, `duckdb_file`, `cors_origins`).

## Tests (`backend/tests/`)

`test_referential` · `test_energy_charts` · `test_metrics` (dont réconciliation Sankey ↔ positions) · `test_entsoe` (M6, offline) · `test_analytics` · `test_duckdb_store` (M6, `:memory:`) · `test_alerts` · `test_model` (M7).

Voir aussi : [[Frontend]] · [[Carte des fichiers]] · [[Conventions et pièges]]
