---
tags: [concept, store, analytics, fluxeu]
status: stable
updated: 2026-06-14
---

# 🦆 DuckDB (store analytique durable)

Substrat d'**accumulation long-historique + SQL**, introduit en **M6** (pas avant :
surdimensionné pour ~48 frames horaires — voir [[Décisions]]). Code : `backend/app/store/duckdb_store.py`.
Fichier : `data/fluxeu.duckdb` (+ `.wal`) — **gitignored**. Spec : `PLAN.md` §3.1, §4.6.

## Pourquoi ici et pas avant

Le live + scrubber tiennent dans `store/cache.py` (JSON disque, ~48 h). DuckDB **ne paie**
qu'avec le long historique (duration curves, corrélations, agrégats 30 j) qu'apporte le
backfill [[ENTSO-E]]. Le store fonctionne **dès maintenant** sur les données Energy-Charts accumulées.

## Schéma

```sql
prices(zone TEXT, ts TIMESTAMPTZ, eur_mwh DOUBLE, PRIMARY KEY(zone, ts))
flows(from_zone, to_zone, ts TIMESTAMPTZ, commercial_mw, physical_mw, PRIMARY KEY(...))
```
- `TIMESTAMPTZ` stocké en **UTC** (affichage Bruxelles côté front — voir [[Conventions et pièges]]).

## Mécanique

- **Connexion** module-level + `threading.Lock` (handlers sync sur threadpool FastAPI).
- **Upsert idempotent** : `ingest_history()` → `INSERT OR REPLACE` depuis des DataFrames pandas enregistrés. Re-ingestion sûre (vérifié : ré-ingest = no-op).
- **Ingestion** câblée dans `jobs/scheduler.py` : après chaque sweep + **seed au boot** depuis le cache 48 h persisté (gardé par try/except).
- `use_database(path)` → bascule `:memory:` pour les tests.

## Fonctions (→ endpoints [[API]])

| Fonction | Endpoint | Note |
|---|---|---|
| `coverage()` | `/api/analytics/coverage` | lignes, span, zones |
| `price_series(zones, hours)` | `/api/prices` | séries prix |
| `flow_series(from, to, hours)` | `/api/flows` | orientation-aware (négatif si stocké inversé) |
| `duration_curve(zone, hours)` | `/api/analytics/duration` | window-fn `row_number()/count()` |
| `correlation(zones, hours)` | `/api/analytics/correlation` | self-join + `corr()` SQL |
| `export_frame(table, hours, zones)` | `/api/export.csv` | DataFrame → CSV |

Vérifié sur l'historique réel : 7 678 lignes prix, 10 364 flux, 40 zones, prix négatifs préservés (-52,99 €/MWh), matrice de corrélation symétrique.

Le **forward model** (M7) lit aussi `price_series()` → voir [[Jalon M7]].

Voir aussi : [[Backend]] · [[ENTSO-E]] · [[Jalon M6]]
