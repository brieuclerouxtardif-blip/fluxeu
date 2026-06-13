# FluxEU ⚡

**Live visualizer of the European electricity market** — day-ahead zone prices on a map, animated cross-border interconnection flows, congestion (price spreads), capacity vs utilisation, generation mix, and historical analytics.

> Nodes = bidding zones colored by price · Edges = interconnectors with animated arcs (width ∝ |MW|, direction = flow) · 48 h time scrubber.

## Status

🕛 **M4 — 48 h time scrubber** (current): on top of the live map hero, a bottom **time scrubber** replays the last 48 h of prices and flows. The whole window comes from a single `GET /api/history` (same Energy-Charts sweep as the live snapshot — **zero extra API calls**) and is replayed client-side: the playhead runs on a `requestAnimationFrame` loop with play/pause + speed, **prices step per market interval** (never interpolated), and "return to live" snaps back to the latest frame.

The hero map itself (M3): a dark Europe map with bidding zones **colored by current day-ahead price** (negative prices rendered distinctly, never clipped) and **animated cross-border flow arcs** — arc width ∝ |MW|, the travelling comet shows flow direction — with a **commercial ⇄ physical** toggle, a price legend, and hover tooltips. Built on the M2 Energy-Charts snapshot at `/api/snapshot/live`.

Build roadmap (see [PLAN.md](PLAN.md) §7):

| Milestone | Scope | Status |
|---|---|---|
| M0 | Scaffold (compose, FastAPI, Vite, MapLibre) | ✅ |
| M1 | Zones/borders referential from `entsoe-py` | ✅ |
| M2 | Energy-Charts source (no key) + live snapshot | ✅ |
| M3 | Live map hero (price choropleth + animated flow arcs) | ✅ |
| M4 | 48 h history + time scrubber (no DuckDB) | ✅ |
| M5 | Metrics & panels + DuckDB (congestion, explorer, dashboards, Sankey) | ⬜ |
| M6 | Analytics + polish + ENTSO-E upgrade (NTC, zone-level flows) | ⬜ |

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

> **Cold start:** Energy-Charts rate-limits the free tier hard (≈1 request / 7.5 s, with a punitive escalating hold on `429`), so a full snapshot build takes **~15–25 min** — a source limit, not a tuning bug. The build is serialized and paced to stay under that limit (no 429 storms), runs on a background scheduler (**every 60 min**), and each result is **persisted to disk** (`data/snapshot.cache.json` + `data/history.cache.json`, gitignored) — so after the first build, a restart serves real (slightly stale) data instantly while it refreshes. The **48 h history comes from the same sweep** (one call per series returns the whole window), so the scrubber costs **no extra API calls**. Until the very first build lands, `/api/snapshot/live` and `/api/history` return `503` with `Retry-After`, and the map shows a “warming up” badge.

### Key endpoints

| Route | Returns |
|---|---|
| `GET /api/health` | `{status, source, last_refresh, ts}` |
| `GET /api/zones` · `/api/zones.geojson` | bidding-zone metadata + geometries |
| `GET /api/interconnectors` | borders + named DC cables |
| `GET /api/snapshot/live` | `LiveSnapshot` — prices, flow nodes/edges, net positions (UTC) |
| `GET /api/history` | `SnapshotHistory` — 48 h of frames (prices + edges + net positions) for the scrubber, one GET |

## Architecture

```
backend/   FastAPI · entsoe-py + httpx · APScheduler · Pydantic v2 · JSON disk cache (DuckDB at M5)
frontend/  React + TS + Vite · deck.gl over MapLibre GL · Tailwind (Recharts/ECharts added at M5)
data/      zones.json · interconnectors.json · zones.geojson (generated at M1)
           snapshot.cache.json · history.cache.json (persisted at runtime, gitignored)
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
