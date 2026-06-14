---
tags: [reference, decision, fluxeu]
status: stable
updated: 2026-06-14
---

# 🧭 Décisions (ADR condensé)

Décisions d'archi **durables** (issues d'un grill), à ne pas re-litiger sans raison neuve.
Le « pourquoi » derrière le code. Voir aussi [[Conventions et pièges]].

## Sources & ingestion

- **Energy-Charts par défaut, ENTSO-E en upgrade** — enlève le mur des ~3 j d'attente token : l'app tourne dès J0, la source autoritaire vient ensuite ([[Sources de données]]).
- **Rate limit Energy-Charts pilote l'archi** (~1 req/7.5 s) → sweep **sérialisé + pacé**, **refresh 60 min** (pas 5–15), **persistance disque**, cold-start servi du cache. C'est une limite de source, pas un réglage.
- **Historique 48 h extrait du même sweep** (1 appel = toute la fenêtre) → **0 appel en plus**, **jamais** de job de backfill séparé.
- **`live = dernier frame de la série`** (`live_from_history()`), un seul passage alimente carte + scrubber.

## Stockage

- **DuckDB différé à M6** — inutile pour ~48 frames horaires ; ne paie qu'avec le long historique ENTSO-E (duration curves, corrélations 30 j). Avant : cache JSON disque suffit ([[DuckDB]]).
- **Mix de production différé à M6** — un `/public_power` par pays saturerait le quota du snapshot live. Chargé à la demande, pas dans le snapshot.

## Flux & granularité

- **Flux pays-niveau, prix zone-niveau en démo** — Energy-Charts n'expose les flux qu'au pays. Deux graphes distincts, **assumés** via le champ `granularity`. Le zone→zone + NTC sont **gated ENTSO-E**.
- **Pas de ratio d'utilisation sur frontières flow-based** — FBMC n'a pas de NTC par frontière ; afficher le flux mesuré ([[Modèle de domaine]]).

## Front

- **ECharts ajouté à M5** (wrapper maison, pas de lib react-binding) quand les panneaux l'ont exigé — pas avant.
- **Polling + rampe couleur maison** (pas de TanStack Query / lib couleur tant que le besoin n'est pas concret).
- **`AnimatedArcLayer` shader maison**, pas `TripsLayer` — seule voie propre pour des arcs directionnels animés performants ; c'est *le* différenciant visuel.
- **Scrubber rAF + prix en step** — pas de state React par frame (re-render storm) ; interpoler un prix day-ahead inventerait des prix inexistants ([[Conventions et pièges]]).

## Référentiel

- **`entsoe-py` `Area`/`NEIGHBOURS` = source de vérité** des zones/EIC/adjacences — élimine le risque n°1 (codes faux). **Jamais de hardcode mémoire** ([[ENTSO-E]]).

Voir aussi : [[Architecture]] · [[Jalons]]
