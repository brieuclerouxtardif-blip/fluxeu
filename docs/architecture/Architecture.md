---
tags: [moc, architecture, fluxeu]
status: stable
updated: 2026-06-14
---

# 🧱 Architecture

Monorepo **FastAPI + React/TS**, run via `docker-compose.yml`. Spec : `PLAN.md` §3.
Détails par couche : [[Backend]] · [[Frontend]].

## Stack (figée — ne pas dévier sans demander)

- **Back** : FastAPI (py3.11+), `entsoe-py` + `httpx`, `pandas`, **APScheduler** (1 job refresh 60 min), Pydantic v2. Cache JSON disque (live + 48 h) ; **DuckDB** à partir de M6 (analytics durables).
- **Front** : React + TS + **Vite**, **deck.gl** sur **MapLibre GL**, **Tailwind v4**. Polling + rampe couleur **maison**. **ECharts** (wrapper maison) depuis M5 pour les panneaux.

## Pipeline de données (ingestion → API → front)

```
[DataSource active]  Energy-Charts (défaut) | ENTSO-E (token)
        │  sweep sérialisé + pacé (1 req/7.5 s) — 48 h en un passage
        ▼
[scheduler.py]  refresh 60 min ──► cache mémoire + JSON disque (data/*.cache.json)
        │                       └─► DuckDB ingest (M6, idempotent)
        ▼
[routers/]  /api/snapshot/live · /api/history · /api/metrics/* · /api/analytics/* · /api/alerts · /api/model/*
        ▼
[front]  polling snapshot · /api/history rejoué client-side (rAF) · panneaux à la demande
```

Points structurants (voir [[Décisions]]) :
- **un seul sweep** alimente la carte **et** le scrubber 48 h (0 appel en plus).
- **cold-start** = sert le cache persisté instantanément, rafraîchit en fond ; avant le 1er build → `503 + Retry-After`.
- `live = dernier frame de la série` (`live_from_history()` dans `sources/base.py`).

## Schéma du repo

```
fluxeu/
├─ backend/app/   → voir [[Backend]]   (sources/ domain/ store/ jobs/ routers/ models.py config.py main.py)
├─ frontend/src/  → voir [[Frontend]]  (map/ panels/ components/ api/ types.ts App.tsx)
├─ data/          zones.json · interconnectors.json · zones.geojson  (générés M1)
│                 *.cache.json · fluxeu.duckdb (runtime, gitignored)
├─ docs/          ← ce vault Obsidian
├─ docker-compose.yml · PLAN.md · CLAUDE.md · README.md
```

Index fichier-par-fichier : [[Carte des fichiers]].

Voir aussi : [[Sources de données]] · [[DuckDB]] · [[API]]
