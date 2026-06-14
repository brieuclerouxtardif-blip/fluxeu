// Mirror of backend/app/models.py — keep strictly in sync.

export type CapacityRegime = "NTC" | "FLOW_BASED";

export interface Zone {
  code: string; // EIC
  key: string; // "FR", "IT-NORD", "SE3"...
  name: string;
  country: string;
  centroid: [number, number]; // [lon, lat]
  tso: string[];
  capacity_regime: CapacityRegime;
  region: string | null;
  has_geometry: boolean;
}

export interface Cable {
  name: string;
  mw: number | null;
  tech: string | null;
  year: string | null;
  note?: string | null;
  commissioned: boolean;
}

export interface Interconnector {
  from_zone: string;
  to_zone: string;
  capacity_regime: CapacityRegime;
  gb_decoupled: boolean;
  cables: Cable[];
}

// --- live snapshot (M2) ---
// Prices are per bidding zone; flows are per country (Energy-Charts demo mode).

export interface FlowNode {
  code: string; // ISO-2 country code
  name: string;
  centroid: [number, number]; // [lon, lat]
  zones: string[]; // member zone keys
}

export interface FlowEdge {
  from_zone: string; // FlowNode code
  to_zone: string;
  ts: string; // UTC ISO-8601
  commercial_mw: number | null; // signed: + = from_zone -> to_zone
  physical_mw: number | null;
  ntc_mw: number | null; // null when FLOW_BASED
  capacity_regime: CapacityRegime;
}

export interface LiveSnapshot {
  ts: string; // UTC ISO-8601 — build time
  source: string;
  data_ts: string | null; // UTC ISO-8601 — underlying market data time
  granularity: { prices: string; flows: string };
  prices: Record<string, number>; // zone key -> eur_mwh
  nodes: FlowNode[];
  edges: FlowEdge[];
  net_positions: Record<string, number>; // FlowNode code -> MW (+ = import)
}

// --- history / scrubber (M4) ---
// 48 h of frames from the same sweep as the live snapshot. Prices step per MTU.

export interface HistoryFrame {
  ts: string; // UTC ISO-8601 — market time of this frame
  prices: Record<string, number>; // zone key -> eur_mwh (stepped)
  net_positions: Record<string, number>; // FlowNode code -> MW (+ = import)
  edges: FlowEdge[];
}

export interface SnapshotHistory {
  ts: string; // UTC ISO-8601 — build time
  source: string;
  granularity: { prices: string; flows: string };
  nodes: FlowNode[]; // static across frames
  start: string; // UTC ISO-8601
  end: string; // UTC ISO-8601
  frames: HistoryFrame[]; // ascending by ts
}

// --- metrics (M5) ---
// Spreads are zone-level (incl. intra-country splits); congestion rent is only
// filled where a border is the unique link of its country pair (else null).

export interface BorderMetric {
  from_zone: string; // zone key
  to_zone: string; // zone key
  spread_eur_mwh: number;
  price_from: number | null;
  price_to: number | null;
  internal: boolean; // both zones in the same country
  congestion_income_eur_h: number | null; // €/h, null unless unambiguous
  capacity_regime: CapacityRegime;
  gb_decoupled: boolean;
  utilisation: number | null; // NTC only — gated ENTSO-E (M6)
}

export interface CongestionSnapshot {
  ts: string;
  data_ts: string | null;
  borders: BorderMetric[]; // descending by spread
}

export interface ConvergencePoint {
  ts: string;
  price_std: number; // dispersion of zonal prices, €/MWh
  converged_pct: number; // share of priced borders below threshold, 0..100
}

export interface ConvergenceSeries {
  start: string;
  end: string;
  threshold_eur_mwh: number;
  mean_converged_pct: number;
  latest_std: number | null;
  points: ConvergencePoint[]; // ascending by ts
}

// Net-flow Sankey (M5) — bipartite: export-side node -> import-side node.

export interface SankeyNode {
  id: string; // "x_FR" (export) / "m_DE" (import)
  country: string; // ISO-2
  side: "export" | "import";
}

export interface SankeyLink {
  source: string; // SankeyNode id
  target: string;
  value: number; // MW, commercial net
}

export interface SankeySnapshot {
  ts: string;
  data_ts: string | null;
  nodes: SankeyNode[];
  links: SankeyLink[];
  total_mw: number;
}

// --- analytics (M6) ---
// Served from the durable DuckDB store (accumulates every sweep), so these span
// past the 48 h scrubber window. All timestamps UTC ISO-8601.

export interface SeriesPoint {
  ts: string;
  value: number;
}

export interface ZoneSeries {
  zone: string;
  points: SeriesPoint[]; // ascending by ts
}

export interface PriceSeriesResponse {
  start: string;
  end: string;
  hours: number;
  zones: ZoneSeries[];
}

export interface FlowSeriesPoint {
  ts: string;
  commercial_mw: number | null; // signed: + = from_zone -> to_zone
  physical_mw: number | null;
}

export interface FlowSeriesResponse {
  from_zone: string;
  to_zone: string;
  start: string;
  end: string;
  hours: number;
  points: FlowSeriesPoint[];
}

export interface DurationPoint {
  pct: number; // 0..100, share of the window at or above eur_mwh
  eur_mwh: number;
}

export interface DurationCurve {
  zone: string;
  hours: number;
  n: number;
  points: DurationPoint[]; // descending by price
}

export interface CorrelationMatrix {
  zones: string[]; // present zones, request order
  matrix: (number | null)[][]; // row i / col j = corr(zones[i], zones[j])
  hours: number;
  n_timestamps: number;
}

export interface Coverage {
  price_rows: number;
  flow_rows: number;
  start: string | null;
  end: string | null;
  zones: string[];
  source: string;
}

export interface ZoneFeatureProps {
  key: string;
  name: string;
  country: string;
}

export type ZonesGeoJSON = GeoJSON.FeatureCollection<
  GeoJSON.Geometry,
  ZoneFeatureProps
>;
