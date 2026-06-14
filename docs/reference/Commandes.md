---
tags: [reference, ops, fluxeu]
status: stable
updated: 2026-06-14
---

# 🧰 Commandes

Plateforme : **Windows / PowerShell**. Chemins relatifs à `fluxeu/`.

## Run

```bash
# Tout (zéro config, source démo)
docker compose up --build
# → front http://localhost:5173 · API http://localhost:8000/api/health
```

```powershell
# Backend local (venv déjà créé : backend/.venv)
backend\.venv\Scripts\activate
uvicorn app.main:app --reload --port 8000   # depuis backend/
# (launch.json lance SANS --reload → redémarrer pour recharger le code)

# Frontend local
npm --prefix frontend run dev               # port 5173, proxy /api → :8000
```

## Tests & build

```powershell
# Backend (depuis backend/, venv actif) — état : 53 passés, 1 skipped
pytest -q

# Frontend
npm --prefix frontend run build             # tsc + vite (doit être vert)
```

## Preview (outillage Claude Code)

- Entrée : `fluxeu-frontend` dans `.claude/launch.json`.
- ⚠️ `preview_screenshot` **timeout** sur la carte WebGL → préférer `preview_snapshot` + `preview_eval`. Voir [[Conventions et pièges]].
- Backend sans `--reload` → `preview_stop` puis `preview_start` pour recharger.

## Git

```powershell
git log --oneline -15        # vérité d'avancement
git status --short           # M7 non commité (working tree)
git branch -vv               # main suit origin/main
```

- **Repo** : GitHub public `brieuclerouxtardif-blip/fluxeu`. `main` @ `095af0e` (M6 poussé).
- ⚠️ **Ne jamais committer** : token (`.env`), `data/*.cache.json`, `data/*.duckdb*` (gitignored — [[Conventions et pièges]]).
- **Commit/push seulement sur demande** ; style per-jalon (cf. [[Jalon M7]] à pousser).

## ENTSO-E (à réception du token)

```
# .env (jamais commité)
ENTSOE_API=xxxxxxxx
DATA_SOURCE=entsoe
```
`/api/health` doit alors indiquer `source: entsoe`. Voir [[ENTSO-E]].

Voir aussi : [[Architecture]] · [[Jalons]]
