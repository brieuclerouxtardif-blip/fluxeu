# FluxEU ⚡

**Live visualizer of the European electricity market** — day-ahead zone prices on a map, animated cross-border interconnection flows, congestion (price spreads), capacity vs utilisation, generation mix, and historical analytics.

> Nodes = bidding zones colored by price · Edges = interconnectors with animated arcs (width ∝ |MW|, direction = flow) · 48 h time scrubber.

## Status

🚦 **M7 (optional module) — alerts & forward model** (current): a live signal feed and a baseline forward curve, layered on the shipped stack below.

- **Alertes** — `GET /api/alerts`: negative prices, price spikes (absolute **and** statistical z-score vs the zone's own 48 h distribution), congested borders, near-full NTC (inert until ENTSO-E). Header badge + severity-sorted feed.
- **Modélisation** — `GET /api/model/forward`: a seasonal-naive baseline (hour-of-day p10/p50/p90 from the DuckDB history, Europe/Brussels) overlaid on the realized 48 h spot — an explicit placeholder for a real merit-order / forecaster model.

📊 **M6 — analytics + DuckDB + ENTSO-E** (shipped): a durable **DuckDB** store accumulates long history for SQL analytics — multi-zone price compare, **duration curves**, a daltonian-safe **correlation heatmap**, **CSV export** (`/api/prices`, `/api/flows`, `/api/analytics/*`, `/api/export.csv`). The authoritative **ENTSO-E** source is written and wired (auto-selected when a token is present); its live path — real NTC + zone-level flows — activates on token arrival.

📊 **M5 — analytics panels**: four dockable panels derived **in-memory** from the cached snapshot + 48 h history (no extra API calls):

- **Congestion** — zone-level price-spread leaderboard (incl. intra-country splits) + a 48 h market-convergence curve; congestion rent shown only where it is attributable.
- **Flux** — a **bipartite net-flow Sankey** (who exports to whom); modelled export-side → import-side so it is acyclic and per-country `in − out` equals net position.
- **Interconnexions** — searchable border explorer; per-border detail with named DC cables and a 48 h **commercial-vs-physical** flow chart + price-spread overlay.
- **Zone** — per-zone 48 h price curve (stepped), country net position, neighbour exchanges.

Earlier milestones, still live: a **48 h time scrubber** (M4 — one `GET /api/history`, replayed client-side on a `requestAnimationFrame` playhead, prices stepped) over the **hero map** (M3 — bidding zones colored by day-ahead price, animated cross-border flow arcs, commercial ⇄ physical toggle), on the M2 Energy-Charts snapshot.

Build roadmap (see [PLAN.md](PLAN.md) §7):

| Milestone | Scope | Status |
|---|---|---|
| M0 | Scaffold (compose, FastAPI, Vite, MapLibre) | ✅ |
| M1 | Zones/borders referential from `entsoe-py` | ✅ |
| M2 | Energy-Charts source (no key) + live snapshot | ✅ |
| M3 | Live map hero (price choropleth + animated flow arcs) | ✅ |
| M4 | 48 h history + time scrubber (no DuckDB) | ✅ |
| M5 | Metrics & panels — congestion, Sankey, interconnector explorer, zone dashboard | ✅ |
| M6 | Analytics + DuckDB + ENTSO-E upgrade (NTC, zone-level flows) | ✅ · live ENTSO-E path token-gated |
| M7 | (optional) Alerts + forward-model module | ✅ |

> **Project notes:** an Obsidian knowledge vault for the project lives in [`docs/`](docs/) (start at `docs/FluxEU.md`) — architecture, milestones, decisions, and a file map, kept navigable for fast onboarding.

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
| `GET /api/metrics/congestion` | zone-level price spreads (leaderboard / heatmap), descending |
| `GET /api/metrics/convergence` | 48 h price dispersion + share of coupled borders |
| `GET /api/metrics/sankey` | bipartite net-flow graph (exporter → importer) |
| `GET /api/prices` · `/api/flows` | DuckDB time series (zone prices / border flows) |
| `GET /api/analytics/coverage` · `/duration` · `/correlation` | history coverage, price duration curve, zonal correlation matrix |
| `GET /api/export.csv?table=prices\|flows` | CSV download |
| `GET /api/alerts` | `AlertsSnapshot` — negative prices, spikes, congestion, near-full NTC |
| `GET /api/model/forward?zone=&horizon=` | `ForwardCurve` — seasonal-naive forward + realized spot |

## Architecture

```
backend/   FastAPI · entsoe-py + httpx · APScheduler · Pydantic v2 · JSON disk cache + DuckDB analytics store
frontend/  React + TS + Vite · deck.gl over MapLibre GL · ECharts · Tailwind
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
