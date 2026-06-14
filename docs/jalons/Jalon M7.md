---
tags: [milestone, fluxeu, optional]
status: wip
updated: 2026-06-14
commit: non commité (working tree)
---

# 🚨 M7 — Alertes & Modélisation (option)

Module optionnel `PLAN.md` §4.7 (modélisation) + §4.8 (alertes). **Construit, vérifié live,
mais NON commité** (working tree). Pousser = action sortante → **à confirmer** (l'autorisation M6 ne couvre pas M7). Voir [[Jalons]].

## Alertes / signaux (§4.8) ✅

- `domain/alerts.py` → `compute_alerts(data_ts, prices, edges, history)` → `AlertsSnapshot`. Endpoint `/api/alerts` (async, 503 pendant le warming).
- Détection : **prix négatifs**, **pics** (seuils absolus **et** z-score vs distribution 48 h propre à la zone), **congestion** (réutilise `border_spreads` de [[Backend|metrics.py]]), **capacité quasi-pleine NTC** (inerte sans token — jamais fabriquée).
- Seuils : `NEG_CRIT=-50`, `SPIKE_WARN=150`, `SPIKE_CRIT=300`, `SPIKE_Z=3.0`, `SPREAD_WARN=40`, `SPREAD_CRIT=80`, `UTIL_WARN=0.95`. Tri par rang de sévérité puis `|valeur|`.
- Front : **badge d'en-tête** (compte crit+warn, couleur = pire sévérité) + `AlertsPanel.tsx` (feed trié).

## Modélisation forward (§4.7) ✅

- `domain/model.py` → `forward_curve(zone, horizon_hours)`. Endpoint `/api/model/forward?zone=&horizon=` (sync, `MAX_HORIZON=168`).
- Baseline **seasonal-naive** : profil **horaire** p10/p50/p90 en **heure de Bruxelles** depuis l'historique [[DuckDB]] (`price_series`) + spot **réalisé 48 h**. `METHOD="seasonal_naive_hod"`.
- Front : `ModelPanel.tsx` — bande p10–p90 + p50 pointillé **vs** réalisé (teal). **Placeholder explicite** du vrai modèle merit-order / `peakero-forecaster` (même contrat d'overlay).
- Détail sympa vérifié : capte le creux solaire — p50 **nuit +18,6** vs **midi −12,6** €/MWh (négatif).

## Vérif

pytest **53 passés, 1 skipped** ; build front vert. Live : badge « ⚠ 12 alertes » (3 crit + 9 warn), feed 12 items triés (FR–IT-NORD 89, HU–SK 84…), ModelPanel graphe rendu + `/api/model/forward?zone=FR` appelé, 0 erreur console.

## Fichiers (non commités)

`backend/app/domain/alerts.py` · `domain/model.py` · `routers/alerts.py` · `routers/model.py` · `tests/test_alerts.py` · `tests/test_model.py` · `frontend/src/panels/AlertsPanel.tsx` · `panels/ModelPanel.tsx` (+ modifs `main.py`, `models.py`, `App.tsx`, `api/client.ts`, `types.ts`, `PLAN.md`).

## Reste

Brancher le simulateur réel ; sandbox de scénario (§4.7) ; couche carbone Electricity Maps (optionnelle).

Voir aussi : [[Jalon M6]] · [[Jalons]] · [[Modèle de domaine]]
