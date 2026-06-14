---
tags: [concept, data, entsoe, gated, fluxeu]
status: gated
updated: 2026-06-14
---

# 🔑 ENTSO-E (upgrade autoritaire)

Source autoritaire branchée en M6, **gated par un token**. Code : `backend/app/sources/entsoe.py`
(écrit, câblé, testé offline ; chemin **live non vérifié** sans token). Spec : `PLAN.md` §2.2.

## Statut token

- **Demandé le 2026-06-14**, délivré sous **~3 j ouvrés** (email à `transparency@entsoe.eu`, objet `RESTful API access`).
- Token via `.env` → `ENTSOE_API=...`. **NE JAMAIS le committer** (`.gitignore`, voir [[Conventions et pièges]]).
- `registry.py` : si `active_source == "entsoe"` **et** token présent → `EntsoeSource(token)`, sinon **fallback** Energy-Charts (try/except). `/api/health` expose la source active.

## Ce que ça débloque (⏳ à vérifier à réception)

- **NTC réels** → barre d'utilisation (`flow/NTC`) sur frontières NTC.
- **Flux zone→zone** (vs pays-niveau en démo) → arcs par zone, Sankey plus fin.
- Backfill long (≥30 j) pour les analytics [[DuckDB]].

## Client `entsoe-py` (API réelle, introspectée — pas de mémoire)

- Méthodes vérifiées renvoient des `pd.Series` : `query_day_ahead_prices`, `query_crossborder_flows`, `query_scheduled_exchanges`, `query_net_position`, `query_net_transfer_capacity_dayahead`…
- **Référentiel autoritaire** dans `entsoe/mappings.py` : enum **`Area`** (EIC corrects, `Area['FR'].code`) + dict **`NEIGHBOURS`** (adjacences). → **construire le graphe depuis ça, ne pas hardcoder l'EIC.**

## Pont zone-key → Area-name (vérifié, 42 zones, 79 frontières)

Transformation : **trait d'union → underscore** + **split du chiffre final** :
`NO2 → NO_2`, `DE-LU → DE_LU`, `IT-NORD → IT_NORD`. `NEIGHBOURS` (clés underscore)
donne **79 frontières zone-niveau** ∩ zones modélisées.

## Discipline (rappels)

- Fenêtres ≤ 1 an, ≤ 100 TimeSeries/réponse, rate-limit ~400 req/min → paginer + backoff (`entsoe-py` gère le retry).
- Tout en **UTC** (ENTSO-E renvoie UTC). Convention de signe `+ = from→to`. Granularité flux = `bidding_zone`.
- `EntsoeSource` : `_RateLimiter` + `asyncio.to_thread` + sémaphore dans `_call()`.

Voir aussi : [[Sources de données]] · [[DuckDB]] · [[Jalon M6]] · [[Conventions et pièges]]
