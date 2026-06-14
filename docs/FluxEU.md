---
tags: [moc, fluxeu]
status: wip
updated: 2026-06-14
repo: brieuclerouxtardif-blip/fluxeu
---

# ⚡ FluxEU — hub

Visualiseur du **marché européen de l'électricité** : carte des **prix day-ahead**
par bidding zone (choroplèthe MapLibre dark), **arcs de flux** d'interconnexion
animés (deck.gl, shader « comet » maison), scrubber 48 h, congestion/spreads,
Sankey, analytics DuckDB, alertes + forward model. Monorepo **FastAPI + React/TS**.

Démarre **sans clé** (Energy-Charts), monte en puissance avec **ENTSO-E** (token).

## ▶️ Pour Claude Code — lire dans cet ordre

1. `PLAN.md` (spec, racine repo) + `CLAUDE.md` (règles) — **sources de vérité**.
2. [[Conventions et pièges]] — les 5 règles dures + les 13 pièges. **À lire avant de coder.**
3. [[Architecture]] → [[Backend]] / [[Frontend]] selon la zone touchée.
4. [[Carte des fichiers]] — « où est quoi » (chaque fichier → 1 ligne).
5. Le [[Jalons|jalon]] concerné pour le contexte de la feature.

> ⚠️ Avant tout : `git log --oneline` pour l'état réel d'avancement — **la source de vérité** (les docs peuvent prendre du retard sur le dernier commit).

## 📍 État actuel (2026-06-14)

| | |
|---|---|
| **Branche** | `main` @ `8723164` (à jour avec `origin/main`) |
| **Poussé** | M0 → **M7** ✅ + vault `docs/` |
| **Reste (token requis)** | chemin live ENTSO-E (NTC réels + flux zone→zone) — voir [[ENTSO-E]] |
| **Tests** | pytest **53 passés, 1 skipped** ; build front `tsc`+`vite` vert |
| **Token ENTSO-E** | demandé le 2026-06-14, ~3 j ouvrés d'attente |

→ Détail et prochaines étapes : [[Jalons]].

## 🗺️ Carte du vault

**Concepts** — [[Modèle de domaine]] · [[Sources de données]] · [[ENTSO-E]] · [[DuckDB]] · [[Conventions et pièges]]
**Architecture** — [[Architecture]] · [[Backend]] · [[Frontend]]
**Jalons** — [[Jalons]] · [[Socle M0-M5]] · [[Jalon M6]] · [[Jalon M7]]
**Référence** — [[API]] · [[Carte des fichiers]] · [[Décisions]] · [[Commandes]]

## 🧬 Famille de projets

Projet vitrine pour la **prospection agrégateurs** (cf. mémoire), même famille que
`interco-globe` (globe 3D des interconnexions) et `bess-arbitrage-fr` (backtest
arbitrage batterie) ; complémentaire de `peakero-forecaster` (le vrai moteur de
prix, candidat à brancher dans le [[Jalon M7|module Modélisation]]).
