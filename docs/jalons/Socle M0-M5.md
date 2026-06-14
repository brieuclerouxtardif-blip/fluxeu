---
tags: [milestone, fluxeu]
status: done
updated: 2026-06-14
---

# 🏗️ Socle M0–M5 (livré & poussé)

Les fondations, toutes ✅ sur `main`. Détail dans `git log` + `PLAN.md` §7. Le détail
vivant des fichiers est dans [[Backend]] / [[Frontend]] ; cette note donne le **pourquoi** de chaque palier.

## M0 — Scaffold
Monorepo, `docker-compose`, FastAPI `/api/health`, Vite+React+TS+**Tailwind v4**, MapLibre dark qui rend l'Europe. (+ fix sizing carte `100dvh`.)

## M1 — Référentiel zones/frontières
`entsoe-py` `Area`/`NEIGHBOURS` → `data/zones.json` + `data/interconnectors.json` (fusion starter `PLAN.md` §6) + `data/zones.geojson` + centroïdes. Endpoints `/api/zones(.geojson)`, `/api/interconnectors`. **EIC générés, jamais hardcodés** ([[Conventions et pièges]]).

## M2 — Energy-Charts + snapshot live
`sources/energy_charts.py`, normalisation, `/api/snapshot/live`. **Réalité ≠ plan initial** : rate limit ~1 req/7.5 s → sweep **15–25 min**, **refresh 60 min**, **persistance disque** + cold-start servi du cache. Flux **pays-niveau**, prix **zone-niveau** ([[Sources de données]]).

## M3 — Carte live (hero) ⭐
Zones colorées par prix + **arcs animés** + toggle commercial/physique + tooltips. `AnimatedArcLayer` = **shader « comet » maison** sur horloge murale (**pas** `TripsLayer`) ; échelle prix maison ([[Frontend]]).

## M4 — Historique 48 h + scrubber (SANS DuckDB)
Refactor `_fetch_*` → **séries** (live = dernier point) ; lookback élargi à 48 h (**même nb d'appels**) ; séries persistées (JSON) ; **`/api/history`** (un GET) ; `TimeScrubber` **rAF + step**. DuckDB volontairement reporté ([[Décisions]]).

## M5 — Métriques (en mémoire) & panneaux
`domain/metrics.py` calculé **en mémoire** (~192 frames, agrégations triviales, pas de DB). 4 panneaux (ECharts wrapper maison) :
- **Congestion** — spreads zone-level (incl. splits intra-pays) + rente où attribuable + convergence 48 h.
- **Sankey** — flux nets **bipartite** exporteur→importateur (acyclique, `in−out` = position nette).
- **Explorer** — frontières cherchables triées par flux + détail commercial/physique + overlay spread.
- **Zone** — prix 48 h en palier + position nette + échanges voisins (client-side).

**Différé à M6** : mix de production (saturerait Energy-Charts), NTC/utilisation + duration curve (ENTSO-E).

Voir aussi : [[Jalons]] · [[Jalon M6]] · [[Modèle de domaine]]
