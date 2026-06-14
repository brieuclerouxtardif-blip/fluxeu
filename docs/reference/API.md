---
tags: [reference, api, fluxeu]
status: stable
updated: 2026-06-14
---

# 🔌 API REST

Routes réelles (vérifiées dans `backend/app/routers/` + `main.py`). Réponses **UTC ISO-8601**.
CORS ouvert au front en dev. Modèles : `backend/app/models.py`. Spec : `PLAN.md` §3.5.

| Méthode · Route | Réponse | Jalon | Fichier |
|---|---|---|---|
| `GET /api/health` | `{status, source, last_refresh, ts}` | M0 | `main.py` |
| `GET /api/zones` | `Zone[]` | M1 | `routers/zones.py` |
| `GET /api/zones.geojson` | GeoJSON | M1 | `routers/zones.py` |
| `GET /api/interconnectors` | `Interconnector[]` | M1 | `routers/interconnectors.py` |
| `GET /api/snapshot/live` | `LiveSnapshot` (carte) | M2/M3 | `routers/snapshot.py` |
| `GET /api/history` | `SnapshotHistory` (48 h, **un GET**) | M4 | `routers/snapshot.py` |
| `GET /api/metrics/congestion` | `CongestionSnapshot` | M5 | `routers/metrics.py` |
| `GET /api/metrics/convergence` | `ConvergenceSeries` | M5 | `routers/metrics.py` |
| `GET /api/metrics/sankey` | `SankeySnapshot` (bipartite) | M5 | `routers/metrics.py` |
| `GET /api/prices?zones=FR,DE-LU&hours=` | `PriceSeriesResponse` | M6 | `routers/analytics.py` |
| `GET /api/flows?from=&to=&hours=` | `FlowSeriesResponse` | M6 | `routers/analytics.py` |
| `GET /api/analytics/coverage` | `Coverage` | M6 | `routers/analytics.py` |
| `GET /api/analytics/duration?zone=&hours=` | `DurationCurve` | M6 | `routers/analytics.py` |
| `GET /api/analytics/correlation?zones=` | `CorrelationMatrix` | M6 | `routers/analytics.py` |
| `GET /api/export.csv?table=prices\|flows&...` | text/csv | M6 | `routers/analytics.py` |
| `GET /api/alerts` | `AlertsSnapshot` | M7 | `routers/alerts.py` |
| `GET /api/model/forward?zone=&horizon=` | `ForwardCurve` | M7 | `routers/model.py` |

## Notes

- `analytics` : défauts `DEFAULT_HOURS=720`, `MAX_HOURS=24*366` ; `from`/`to` sont des **alias** de query (`from` réservé Python). Handlers **sync** (threadpool).
- `model` : `MAX_HORIZON=168`.
- **Pas** de `/api/snapshot?ts=` par instant (abandonné) ni de `/api/zones/{key}/dashboard` (le **Zone dashboard** est **client-side** depuis `/api/history`).
- Avant le 1er build : `/api/snapshot/live` et `/api/history` → **`503 + Retry-After`** (cold-start, voir [[Architecture]]).

Voir aussi : [[Backend]] · [[DuckDB]] · [[Modèle de domaine]]
