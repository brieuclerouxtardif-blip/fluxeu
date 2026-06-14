---
tags: [architecture, frontend, fluxeu]
status: stable
updated: 2026-06-14
---

# ⚛️ Frontend (React + Vite)

Racine : `frontend/src/`. Entrée : `main.tsx` → `App.tsx`. Build : `tsc` + `vite` (vert).
Preview : entrée `fluxeu-frontend` dans `.claude/launch.json` (port 5173, proxy `/api` → `:8000`).

## `App.tsx` — orchestration

- Polling du snapshot + `/api/history` (une fois, rejoué côté client).
- Union de panneaux : `congestion | sankey | explorer | zone | analytics | alerts | model`.
- Effet de poll **alertes** → `alertCount`/`alertColor` → **badge d'en-tête** (`⚠ N alertes`).
- Lanceurs (∿ Analytics, ⚠ Alertes, ⟐ Modèle) + `PanelDock` + `PANEL_META`.

## `map/` — la carte (hero, M3)
- `MapView.tsx` — deck.gl (`GeoJsonLayer` zones + arcs) sur MapLibre dark via `MapboxOverlay`.
- `AnimatedArcLayer.ts` — **shader « comet » maison** piloté sur l'horloge murale (**pas** `TripsLayer`).
- `priceColor.ts` — rampe couleur prix **maison** (prix négatifs distincts — voir [[Conventions et pièges]]).
- `TimeScrubber.tsx` — slider 48 h, **rAF + step**, refs impératives (pas de state par frame).

## `panels/` — dock latéral
- M5 : `CongestionPanel` · `SankeyPanel` (bipartite) · `ExplorerPanel` (frontières cherchables) · `ZonePanel` (prix 48 h + position nette + voisins, **100 % client-side**, pas d'endpoint dédié).
- M6 : `AnalyticsPanel` — compare multi-zones, monotone, heatmap corrélation daltonien-safe, export CSV, fenêtre 24 h/7 j/30 j.
- M7 : `AlertsPanel` (prop-driven `{data, warming}`, feed trié) · `ModelPanel` (overlay forward p10–p90 + p50 vs réalisé). Voir [[Jalon M7]].
- `PanelDock.tsx` — conteneur dock.

## Transverse
- `components/Chart.tsx` — wrapper **ECharts maison** (pas de lib react-binding).
- `api/client.ts` — client typé : `fetchSnapshot`, `fetchHistory`, `fetchCoverage`, `fetchPriceSeries`, `fetchDuration`, `fetchCorrelation`, `exportCsvUrl`, `fetchAlerts`, `fetchForward`…
- `types.ts` — **miroir manuel strict** des modèles Pydantic (`backend/app/models.py`).

## Design (PLAN §5)
Terminal de marché énergie : sombre (`#0B0E14`–`#11151F`), accent cyan `#3DE0E0`, mono pour les chiffres, **export = teinte A / import = teinte B** constants, palettes **daltonien-safe**.

Voir aussi : [[Backend]] · [[API]] · [[Carte des fichiers]]
