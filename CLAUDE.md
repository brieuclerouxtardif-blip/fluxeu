# FluxEU — Working agreement for Claude Code

## What we're building
A web app visualizing the European electricity market's cross-border interconnections:
live day-ahead prices per bidding zone (colored map), animated flow arcs between zones,
interconnector capacity vs utilisation, congestion (price spreads), generation mix,
and historical analytics. See PLAN.md for the full spec — it is the source of truth.

## Stack (do not deviate without asking)
Backend: FastAPI (py3.11+), entsoe-py + httpx, APScheduler, Pydantic v2. JSON disk cache for live + 48 h history; **DuckDB introduced at M5** (historical analytics), not before — it is overkill for ~48 hourly frames.
Frontend: React + TS + Vite, deck.gl over MapLibre GL, Tailwind. Polling + price color ramp are hand-rolled. Chart/analytics libs (Recharts/ECharts) **added on demand at M5**; TanStack Query only if hand-rolled polling stops being enough.
Run: docker-compose.

## Data sources
- DEFAULT (no key): Energy-Charts API https://api.energy-charts.info/ — /price /cbpf /cbet /public_power
- UPGRADE (token): ENTSO-E https://web-api.tp.entsoe.eu/api via entsoe-py.
  Token via .env ENTSOE_API. NEVER commit it.
- Source of truth for zones/borders: entsoe-py `entsoe/mappings.py` (Area enum + NEIGHBOURS).
  Do NOT hardcode EIC codes from memory; generate data/zones.json + data/interconnectors.json from it,
  merging the starter tables in PLAN.md §6 and reconciling any difference.

## Hard rules
- Store all timestamps in UTC; display in Europe/Brussels with DST handling.
- Flow sign convention: + means from_zone -> to_zone. Keep it consistent everywhere.
- Flow-based borders (Core/Nordic): no fake utilisation ratio; show measured flow.
  Only show utilisation when capacity_regime == "NTC".
- Physical flow != commercial flow: two distinct quantities, two endpoints, label clearly.
- Tag GB interconnectors gb_decoupled (post-Brexit, explicit coupling).
- Negative prices are normal: render them distinctly, don't clip the color ramp.

## Build order (verify each milestone before moving on — see PLAN.md §7)
M0 scaffold -> M1 zones/borders ref -> M2 Energy-Charts snapshot -> M3 live map (hero)
-> M4 48 h history + time scrubber (no DuckDB) -> M5 metrics & panels + DuckDB -> M6 analytics + polish + ENTSO-E (NTC, zone-level flows).

## Definition of done
PLAN.md §10. Tests: pytest (transforms, metrics, sign conventions, Sankey reconciliation),
Vitest smoke on frontend. `docker compose up` must run the whole thing with zero config (demo source).
