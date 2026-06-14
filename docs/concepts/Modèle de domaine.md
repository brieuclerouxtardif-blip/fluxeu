---
tags: [concept, domain, fluxeu]
status: stable
updated: 2026-06-14
---

# 📚 Modèle de domaine

Le vocabulaire métier exact. À connaître pour **ne pas faire d'erreur de domaine**.
Spec complète : `PLAN.md` §1. Modèles Pydantic : `backend/app/models.py`. Miroir TS : `frontend/src/types.ts`.

## Bidding zone (BZ) = unité atomique

Le marché raisonne en **zones de dépôt**, pas en pays.
- IT ≈ 7 zones (NORD, CNOR, CSUD, SUD, CALA, SICI, SARD) · Nordiques splittés (NO1–5, SE1–4, DK1/DK2) · **DE-LU fusionnés**.
- Chaque BZ : code **EIC** (`10YFR-RTE------C`), TSO, **centroïde** (ancrage des arcs), géométrie (polygone).
- ⚠️ zone ≠ frontière administrative pour la géométrie (IT/Nordiques). Centroïde **du polygone de zone**, pas du pays.
- Source de vérité des zones/EIC : `entsoe-py` → voir [[ENTSO-E]]. **Jamais hardcodé de mémoire.**

## Prix & convergence (couplage day-ahead SDAC / EUPHEMIA)

Le couplage calcule **simultanément** prix de zone et flux pour maximiser le bien-être.
- Frontière **non saturée** → prix **convergent** (spread ≈ 0).
- Frontière **saturée** → **price spread** ≠ 0, exportateur moins cher que l'importateur. **Le spread est le signal de congestion n°1.**
- MTU horaire → bascule **15 min** en cours UE → granularité paramétrable.

## Capacité : deux régimes (`capacity_regime`)

- **NTC/ATC** — capacité MW par sens, frontière par frontière. Mappable sur une arête. Liaisons DC, plusieurs frontières. → barre d'utilisation OK.
- **Flow-Based (FBMC)** — régions **Core** (CWE+CEE) et **Nordic**. Pas de NTC par frontière (domaine PTDF/RAM). → **afficher le flux mesuré, jamais un ratio flux/NTC inventé**. Voir [[Conventions et pièges]] piège #2.

## Trois grandeurs de flux à ne pas confondre

- **Flux physique** (mesuré, Kirchhoff, transit possible) — Energy-Charts `/cbpf`, ENTSO-E `A11`/`A26`.
- **Échange commercial / programmé** (résultat d'allocation marché) — `/cbet`, `A09`.
- **Position nette** par zone = somme algébrique des échanges (`+` = import).
- Carte : **commercial net** par défaut, toggle vers **physique**.

## Métriques dérivées (différenciantes)

`price spread` · `rente de congestion` (`spread × flux`) · `indice de convergence`
(`std` des prix zonaux / % heures convergées) · `taux d'utilisation` (NTC seul) ·
`duration curve` · `net position`. Implémentées dans `backend/app/domain/metrics.py` (M5)
et `store/duckdb_store.py` (M6, SQL) — voir [[Backend]], [[DuckDB]].

## Modèles Pydantic clés (`models.py`)

`Zone` · `FlowNode` (graphe **pays** en démo) · `FlowEdge` (`commercial_mw`/`physical_mw`/`ntc_mw`, signés) ·
`LiveSnapshot` (carte) · `HistoryFrame`/`SnapshotHistory` (scrubber) · `BorderMetric` ·
+ M6 (`PriceSeriesResponse`, `DurationCurve`, `CorrelationMatrix`, `Coverage`…) + M7 (`AlertsSnapshot`, `ForwardCurve`).

> **Granularité assumée (démo Energy-Charts)** : prix au **niveau zone**, flux au **niveau pays** (ISO-2) → deux graphes distincts, documentés par le champ `granularity`. Le **zone→zone** est débloqué par [[ENTSO-E]] (M6).

Voir aussi : [[Conventions et pièges]] · [[Sources de données]]
