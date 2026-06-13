import type {
  Interconnector,
  LiveSnapshot,
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
