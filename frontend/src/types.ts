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

export interface ZoneFeatureProps {
  key: string;
  name: string;
  country: string;
}

export type ZonesGeoJSON = GeoJSON.FeatureCollection<
  GeoJSON.Geometry,
  ZoneFeatureProps
>;
