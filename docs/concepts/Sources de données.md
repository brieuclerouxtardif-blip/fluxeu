---
tags: [concept, data, fluxeu]
status: stable
updated: 2026-06-14
---

# 🔌 Sources de données

Pattern **registry** : `backend/app/sources/registry.py` sélectionne la source active.
Interface commune `DataSource` (Protocol) dans `backend/app/sources/base.py` :
`fetch_snapshot()` → `LiveSnapshot`, `fetch_history()` → `SnapshotHistory`.
Les deux sources produisent **le même contrat**. Spec : `PLAN.md` §2.

## 1. Energy-Charts — défaut, **sans clé** (Fraunhofer ISE)

`backend/app/sources/energy_charts.py` · base `https://api.energy-charts.info/`
- `/price?bzn=` (prix zone) · `/cbpf?country=` (flux physique) · `/cbet?country=` (commercial) · `/public_power?country=` (mix).
- Timestamps en **unix sec**. Flux en **GW** → convertis en MW. Prix €/MWh.

> **⚠️ Rate limit = contrainte n°1.** Token bucket **~1 req / 7.5 s**, `429` punitif escaladant. Un snapshot complet (~74 appels) prend **15–25 min** — limite de source, pas un réglage. Conséquences (voir [[Décisions]]) :
> - sweep **sérialisé** (concurrence 1) et **pacé** ;
> - **refresh 60 min**, résultats **persistés** (`data/snapshot.cache.json`, `data/history.cache.json`, gitignored) ;
> - cold-start sert le cache **instantané** puis rafraîchit ;
> - **historique 48 h extrait du même sweep** (1 appel = toute la fenêtre) → **0 appel en plus**. Ne jamais ajouter de job de backfill qui re-paie le rate limit.

## 2. ENTSO-E — source autoritaire (**upgrade, token**)

`backend/app/sources/entsoe.py` · client `entsoe-py` · voir la note dédiée **[[ENTSO-E]]**.
Débloque **NTC réels** + **flux zone→zone** (utilisation, arcs par zone). Activée auto si token présent (`/api/health` indique la source).

## 3. Electricity Maps — optionnel (intensité carbone)

Free tier 1 zone. À brancher **seulement** pour une couche « carbone » du dashboard zone. Non bloquant, non implémenté.

## Référentiel géographique

- `data/zones.json` (EIC, nom, pays, centroïde, TSO, régime) + `data/zones.geojson` (géométries) + `data/interconnectors.json` (frontières + câbles DC) — **générés en M1** depuis `entsoe-py`, fusionnés avec le starter `PLAN.md` §6. Voir [[Socle M0-M5]].

Voir aussi : [[Modèle de domaine]] · [[Architecture]] · [[Conventions et pièges]]
