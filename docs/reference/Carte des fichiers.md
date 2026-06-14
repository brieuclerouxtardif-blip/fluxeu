---
tags: [reference, index, fluxeu]
status: stable
updated: 2026-06-14
---

# 🗂️ Carte des fichiers (« où est quoi »)

Chemins relatifs à la racine `fluxeu/`. Jalon entre parenthèses. Voir [[Backend]] / [[Frontend]] pour le détail.

## Backend — `backend/app/`

| Fichier | Rôle |
|---|---|
| `main.py` | App FastAPI, CORS, lifespan (scheduler), montage routers, `/api/health` |
| `config.py` | Settings `.env` (`ENTSOE_API`, `DATA_SOURCE`, `duckdb_file`, `cors_origins`) |
| `models.py` | Tous les Pydantic v2 (miroir de `frontend/src/types.ts`) |
| `sources/base.py` | Protocol `DataSource` + `live_from_history()` |
| `sources/energy_charts.py` | Source défaut httpx (no key) |
| `sources/entsoe.py` (M6) | Source `entsoe-py` (token-gated) → [[ENTSO-E]] |
| `sources/registry.py` | `get_source()` auto-select + fallback |
| `domain/zones.py` | `load_zones()`, `load_zones_geojson()` |
| `domain/interconnectors.py` | `load_interconnectors()` |
| `domain/countries.py` | `ZONE_TO_CC` |
| `domain/metrics.py` (M5) | spreads, congestion, convergence, Sankey bipartite |
| `domain/alerts.py` (M7) | `compute_alerts()` |
| `domain/model.py` (M7) | `forward_curve()` seasonal-naive |
| `store/cache.py` | Cache live + 48 h (JSON disque) |
| `store/duckdb_store.py` (M6) | Store analytique durable → [[DuckDB]] |
| `jobs/scheduler.py` | APScheduler : refresh 60 min + ingest DuckDB + seed boot |
| `routers/*.py` | zones · interconnectors · snapshot · metrics · analytics · alerts · model → [[API]] |
| `tests/*.py` | referential · energy_charts · metrics · entsoe · analytics · duckdb_store · alerts · model |

## Frontend — `frontend/src/`

| Fichier | Rôle |
|---|---|
| `main.tsx` / `App.tsx` | Bootstrap / orchestration (poll, panneaux, badge alertes) |
| `types.ts` | Miroir manuel des modèles Pydantic |
| `api/client.ts` | Client HTTP typé |
| `map/MapView.tsx` | deck.gl + MapLibre |
| `map/AnimatedArcLayer.ts` | Shader « comet » maison |
| `map/priceColor.ts` | Rampe couleur prix (négatifs distincts) |
| `map/TimeScrubber.tsx` | Scrubber 48 h (rAF + step) |
| `components/Chart.tsx` | Wrapper ECharts maison |
| `panels/*.tsx` | PanelDock · Congestion · Sankey · Explorer · Zone (M5) · Analytics (M6) · Alerts · Model (M7) |

## Données & config — racine

| Fichier | Rôle |
|---|---|
| `data/zones.json` · `zones.geojson` · `interconnectors.json` | Référentiel (généré M1) |
| `data/*.cache.json` · `data/fluxeu.duckdb(.wal)` | Runtime — **gitignored** |
| `PLAN.md` · `CLAUDE.md` · `README.md` | Spec · règles · vitrine |
| `docker-compose.yml` · `.claude/launch.json` | Run · preview |
| `docs/` | **Ce vault Obsidian** |

Voir aussi : [[Architecture]] · [[API]]
