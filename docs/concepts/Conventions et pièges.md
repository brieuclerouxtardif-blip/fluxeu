---
tags: [concept, rules, decision, fluxeu]
status: stable
updated: 2026-06-14
---

# ⚖️ Conventions et pièges

**À lire avant de coder.** Règles dures (`CLAUDE.md`) + pièges (`PLAN.md` §8).
Ces règles **priment** sur tout défaut.

## 🔒 Règles dures (non négociables)

1. **UTC partout** au stockage ; affichage **Europe/Brussels** avec DST. Source d'erreur n°1.
2. **Signe des flux** : `+ = from_zone → to_zone`. Tenu **partout** (back, store, front, Sankey). Positions nettes : `+ = import`.
3. **FBMC ≠ NTC** : pas de ratio d'utilisation factice sur frontière flow-based. Utilisation **seulement** si `capacity_regime == "NTC"`.
4. **Flux physique ≠ commercial** : deux grandeurs, deux endpoints, libellées distinctement.
5. **Prix négatifs** = normaux (renouvelable) : rendus **distinctement**, jamais clippés dans la rampe couleur.
6. **EIC jamais hardcodé de mémoire** → `entsoe-py` `Area`/`NEIGHBOURS` (voir [[ENTSO-E]]).
7. **Token ENTSO-E jamais commité** (`.env` + `.gitignore`). Idem `data/*.duckdb*` et `data/*.cache.json` (gitignored).
8. **Stack figée** sans demander (voir [[Architecture]]).

## ⚠️ Pièges (PLAN §8 — condensé)

- **Timezone/DST** : ENTSO-E = UTC, Energy-Charts = unix sec. Décalages = bug n°1.
- **GB post-Brexit** : tag `gb_decoupled` ; couplage explicite, l'« utilisation NTC » reste valide mais pas la convergence implicite de la plaque.
- **IT/Nordiques** : zones internes multiples → centroïde **du polygone de zone**, pas du pays, sinon arcs/flux internes faux.
- **Cohérence Sankey ↔ positions nettes** : `Σ(in) − Σ(out)` par nœud = position nette. Test dédié (`test_metrics.py`).
- **Perf carte** : filtrer `|MW|` sous un seuil, throttler le live.
- **Scrubber** : playhead en **`requestAnimationFrame`** + refs impératives, **jamais de state React par frame** (sinon MapView reconstruit ses layers). **Prix en palier (step)**, jamais interpolés (constants par MTU) ; seuls les flux se lissent.
- **Rate limit Energy-Charts** : token bucket ~1 req/7.5 s, `429` punitif → sweep sérialisé/pacé + persistance + refresh 60 min. **Jamais** de job de backfill qui re-paie le rate limit (l'historique 48 h sort du même sweep). Voir [[Sources de données]].

## 🧰 Pièges d'outillage (preview — appris)

- `preview_screenshot` **timeout** sur la carte WebGL/deck.gl → utiliser `preview_snapshot` (a11y) + `preview_eval` (DOM).
- `preview_click` (coords) **n'atteint pas** les onClick React des boutons ancrés au bord → `preview_eval` avec `element.click()`.
- Lire l'état React **dans un eval séparé** après le `.click()` (React flush après la tâche JS).
- Uvicorn lancé **sans `--reload`** (launch.json) → `preview_stop` + `preview_start` pour recharger le backend.

Voir aussi : [[Modèle de domaine]] · [[Décisions]] · [[Commandes]]
