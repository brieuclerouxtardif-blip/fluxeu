---
tags: [moc, fluxeu, meta]
status: actif
updated: 2026-06-14
---

# 📓 Vault FluxEU

Coffre Obsidian qui **retrace le projet FluxEU** et sert de carte mentale pour
toute session Claude Code. Ce n'est **pas** la spec : la spec et le contrat de
travail restent à la racine du repo.

## Source de vérité (hors vault)

| Fichier | Rôle |
|---|---|
| `PLAN.md` | **Spec unique** — domaine, archi, contrat d'API, jalons, pièges. |
| `CLAUDE.md` | Working agreement (stack figée, règles dures, ordre de build). |
| `README.md` | Vitrine publique du repo (⚠️ figée à M5, voir [[Jalons]]). |
| `git log` | Vérité d'avancement réelle (1 commit ≈ 1 sous-jalon). |

> Le vault **résume et relie** ces sources ; en cas de conflit, **`PLAN.md` gagne**.

## Comment l'utiliser

- Point d'entrée : **[[FluxEU]]** (hub). Tout part de là.
- Navigation par `[[wikilinks]]` ; graphe Obsidian = vue d'ensemble.
- Filtrage par `tags` (`#concept`, `#architecture`, `#milestone`, `#reference`, `#decision`).
- **Convention de chemins** : tout chemin de fichier dans ce vault est **relatif à la racine du repo `fluxeu/`** (ex. `backend/app/main.py`). Le vault lui-même vit dans `docs/`.

## Carte rapide

- 🧭 [[FluxEU]] — hub + état actuel
- 🧱 [[Architecture]] · [[Backend]] · [[Frontend]]
- 📚 [[Modèle de domaine]] · [[Sources de données]] · [[ENTSO-E]] · [[DuckDB]]
- ⚖️ [[Conventions et pièges]] · [[Décisions]]
- 🛣️ [[Jalons]] · [[Socle M0-M5]] · [[Jalon M6]] · [[Jalon M7]]
- 🔌 [[API]] · [[Carte des fichiers]] · [[Commandes]]
