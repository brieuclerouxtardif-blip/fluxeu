---
tags: [milestone, fluxeu, gated]
status: done
updated: 2026-06-14
commit: 095af0e
---

# 📊 M6 — Analytics + DuckDB + ENTSO-E

Substrat analytique durable + montée en puissance vers la source autoritaire.
**Poussé** (`095af0e`). Spec : `PLAN.md` §7 (M6), §4.6. DoD global §10.

## Fait (indépendant du token) ✅

- **DuckDB** — `store/duckdb_store.py` : schéma prix/flux, upsert idempotent, ingestion par sweep + seed boot du cache 48 h. Détail : [[DuckDB]].
- **Endpoints analytics** — `/api/prices`, `/api/flows`, `/api/analytics/{coverage,duration,correlation}`, `/api/export.csv` (monotone via window-func, corrélation via `corr()` SQL). Voir [[API]].
- **Panneau Analytics** (front) — compare multi-zones, monotone de prix, **heatmap corrélation daltonien-safe**, export CSV, sélecteur de fenêtre 24 h/7 j/30 j. (`frontend/src/panels/AnalyticsPanel.tsx`)
- **`entsoe.py` écrit & câblé** — graphe zone + EIC depuis `entsoe-py`, **79 frontières zone→zone**, flux signés + NTC, pacing + threadpool ; `registry.py` auto-select + fallback. Tests offline (graphe, transforms, fallback). Détail : [[ENTSO-E]].
- **Tests** : pytest **44 vert** (à ce jalon) ; build front vert ; panneau vérifié live en preview.

## Reste (⏳ token requis)

- Vérifier le **chemin live ENTSO-E** : NTC réels + flux zone→zone **end-to-end** à réception du token (demandé 2026-06-14). → [[ENTSO-E]].
- Vitest non câblé (build `tsc`+`vite` vert en attendant).

## Vérifié en preview

Coverage « 7 678 pts », 3 canvases ECharts rendus, les 4 endpoints analytics passent par le proxy, 0 erreur console.

Voir aussi : [[Jalon M7]] · [[Jalons]] · [[Décisions]]
