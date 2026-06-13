# FluxEU ⚡

**Live visualizer of the European electricity market** — day-ahead zone prices on a map, animated cross-border interconnection flows, congestion (price spreads), capacity vs utilisation, generation mix, and historical analytics.

> Nodes = bidding zones colored by price · Edges = interconnectors with animated arcs (width ∝ |MW|, direction = flow) · 48 h time scrubber.

## Status

🌍 **M3 — Live map hero** (current): a dark Europe map with bidding zones **colored by current day-ahead price** (negative prices rendered distinctly, never clipped) and **animated cross-border flow arcs** — arc width ∝ |MW|, the travelling comet shows flow direction — with a **commercial ⇄ physical** toggle, a price legend, and hover tooltips (zone price + country net position, border flow). Built on the M2 Energy-Charts snapshot at `/api/snapshot/live`.

Build roadmap (see [PLAN.md](PLAN.md) §7):

| Milestone | Scope | Status |
|---|---|---|
| M0 | Scaffold (compose, FastAPI, Vite, MapLibre) | ✅ |
| M1 | Zones/borders referential from `entsoe-py` | ✅ |
| M2 | Energy-Charts source (no key) + live snapshot | ✅ |
| M3 | Live map hero (price choropleth + animated flow arcs) | ✅ |
| M4 | DuckDB history + 48 h time scrubber | ⬜ |
| M5 | Metrics & panels (congestion, explorer, dashboards, Sankey) | ⬜ |
| M6 | Analytics + polish + ENTSO-E upgrade | ⬜ |

## Quick start

### Docker (one command, zero config)

```bash
docker compose up --build
```

- Frontend: http://localhost:5173
- API: http://localhost:8000/api/health

### Local dev

```bash
# backend
cd backend
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# frontend (separate terminal)
cd frontend
npm install
npm run dev
```

## Data sources

- **Default (no key)**: [Energy-Charts API](https://api.energy-charts.info/) (Fraunhofer ISE) — prices, cross-border physical flows (`/cbpf`), commercial exchanges (`/cbet`), generation mix.
- **Upgrade (token)**: [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/) via `entsoe-py`. Put the token in `.env` (`ENTSOE_API=...`, see `.env.example`) — **never commit it**. The backend auto-selects the source; check `/api/health`.
- Zone/border referential: `entsoe-py` `mappings.py` (`Area` enum + `NEIGHBOURS`) — EIC codes are never hardcoded from memory.

> **Granularity note (Energy-Charts demo mode):** prices are per **bidding zone** (`/price`), but cross-border flows are only available per **country** (`/cbet`, `/cbpf`). So the live snapshot colors zones by price yet draws flow arcs on a country-level graph. ENTSO-E (M6) provides zone-level flows. Energy-Charts returns cross-border values in **GW** (converted to MW) and prices in EUR/MWh; flows are signed `+` = into the queried country and re-expressed as `+` = `from_zone → to_zone`.

> **Cold start:** Energy-Charts rate-limits the free tier hard (≈1 request / 7.5 s), so a full snapshot build takes ~9 min. The build is paced to stay under that limit (no 429 storms), runs on a background scheduler (every 30 min), and each result is **persisted to disk** (`data/snapshot.cache.json`, gitignored) — so after the first build, a restart serves real (slightly stale) data instantly while it refreshes. Until the very first build lands, `/api/snapshot/live` returns `503` with `Retry-After`, and the map shows a “warming up” badge.

### Key endpoints

| Route | Returns |
|---|---|
| `GET /api/health` | `{status, source, last_refresh, ts}` |
| `GET /api/zones` · `/api/zones.geojson` | bidding-zone metadata + geometries |
| `GET /api/interconnectors` | borders + named DC cables |
| `GET /api/snapshot/live` | `LiveSnapshot` — prices, flow nodes/edges, net positions (UTC) |

## Architecture

```
backend/   FastAPI · entsoe-py + httpx · DuckDB · APScheduler · Pydantic v2
frontend/  React + TS + Vite · deck.gl over MapLibre GL · TanStack Query · Recharts/ECharts · Tailwind
data/      zones.json · interconnectors.json · zones.geojson (generated at M1)
```

Full spec, domain model, API contract, acceptance criteria and pitfalls: **[PLAN.md](PLAN.md)**. Working agreement for Claude Code: **[CLAUDE.md](CLAUDE.md)**.

## Hard conventions

- All timestamps stored **UTC**, displayed Europe/Brussels.
- Flow sign: `+` = `from_zone → to_zone`, everywhere.
- Flow-based borders (Core/Nordic): measured flow only, no fake NTC utilisation ratio.
- Physical flow ≠ commercial exchange — two quantities, labeled distinctly.
- Negative prices rendered distinctly (not clipped in the color ramp).

## License

Data: per-source terms (Energy-Charts CC BY 4.0, ENTSO-E Transparency terms). Code: MIT.
