---
tags: [moc, milestone, fluxeu]
status: wip
updated: 2026-06-14
---

# 🛣️ Jalons

Build **strictement par jalons** M0→M7 ; ne pas avancer si le DoD du jalon n'est pas vert
(`PLAN.md` §7, DoD global §10). **Vérité d'avancement = `git log`** (les docs peuvent prendre du retard sur le dernier commit).

## Statut

| Jalon | Scope | Statut |
|---|---|---|
| M0 | Scaffold (compose, FastAPI, Vite, MapLibre dark) | ✅ poussé |
| M1 | Référentiel zones/frontières depuis `entsoe-py` | ✅ poussé |
| M2 | Source Energy-Charts (no key) + snapshot live | ✅ poussé |
| M3 | Carte live hero (choroplèthe prix + arcs animés) | ✅ poussé |
| M4 | Historique 48 h + time scrubber (sans DuckDB) | ✅ poussé |
| M5 | Métriques en mémoire + 4 panneaux | ✅ poussé |
| **M6** | Analytics + **DuckDB** + **ENTSO-E** (gated) | ✅ poussé (`095af0e`) ⏳ live token |
| **M7** | Alertes + Modélisation (option §4.7–4.8) | ✅ poussé (`d7225ba`) |

→ [[Socle M0-M5]] · [[Jalon M6]] · [[Jalon M7]]

## Historique git (`main`)

```
8723164  docs: vault Obsidian (docs/) + README à M6/M7
d7225ba  M7 (alerts + forward model): /api/alerts + /api/model/forward
095af0e  M6 (analytics): DuckDB + SQL analytics + CSV + Analytics panel; entsoe câblé
56ebae4  M5 (zone dashboard)
dd2d056  M5 (explorer)
d2764da  M5 (Sankey)
e6dedc5  M5 (congestion)
a8dc106  M4: 48 h history + scrubber
ae9adb9  M3: live map hero
bb4a3e7  M2: Energy-Charts snapshot
5489f64  M1 referential (EIC depuis entsoe-py)
b8bed5d  fix(frontend): map sizing
0b4967a  M0 scaffold
```

## Prochaines étapes

1. **À réception du token** [[ENTSO-E]] : vérifier le chemin live (NTC réels + flux zone→zone end-to-end). Seul vrai reste.
2. Optionnel : vrai modèle merit-order / `peakero-forecaster` ([[Jalon M7]]) ; sandbox scénario ; couche carbone Electricity Maps ; Vitest (non câblé).

Voir aussi : [[FluxEU]] · [[Conventions et pièges]]
