import type {
  CongestionSnapshot,
  ConvergenceSeries,
  CorrelationMatrix,
  Coverage,
  DurationCurve,
  Interconnector,
  LiveSnapshot,
  PriceSeriesResponse,
  SankeySnapshot,
  SnapshotHistory,
  Zone,
  ZonesGeoJSON,
} from "../types";

export interface Health {
  status: string;
  source: string;
  last_refresh: string | null;
  ts: string;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

export const fetchHealth = () => get<Health>("/api/health");
export const fetchZones = () => get<Zone[]>("/api/zones");
export const fetchInterconnectors = () =>
  get<Interconnector[]>("/api/interconnectors");
export const fetchZonesGeoJSON = () => get<ZonesGeoJSON>("/api/zones.geojson");
export const fetchLiveSnapshot = () =>
  get<LiveSnapshot>("/api/snapshot/live");
export const fetchHistory = () => get<SnapshotHistory>("/api/history");
export const fetchCongestion = () =>
  get<CongestionSnapshot>("/api/metrics/congestion");
export const fetchConvergence = () =>
  get<ConvergenceSeries>("/api/metrics/convergence");
export const fetchSankey = () => get<SankeySnapshot>("/api/metrics/sankey");

// --- analytics (M6) — durable DuckDB store ---
export const fetchCoverage = () => get<Coverage>("/api/analytics/coverage");
export const fetchPriceSeries = (zones: string[], hours: number) =>
  get<PriceSeriesResponse>(
    `/api/prices?zones=${encodeURIComponent(zones.join(","))}&hours=${hours}`,
  );
export const fetchDuration = (zone: string, hours: number) =>
  get<DurationCurve>(
    `/api/analytics/duration?zone=${encodeURIComponent(zone)}&hours=${hours}`,
  );
export const fetchCorrelation = (zones: string[], hours: number) =>
  get<CorrelationMatrix>(
    `/api/analytics/correlation?zones=${encodeURIComponent(zones.join(","))}&hours=${hours}`,
  );
export const exportCsvUrl = (
  table: "prices" | "flows",
  hours: number,
  zones?: string[],
): string => {
  const q = new URLSearchParams({ table, hours: String(hours) });
  if (zones && zones.length) q.set("zones", zones.join(","));
  return `/api/export.csv?${q.toString()}`;
};
