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

export interface ZoneFeatureProps {
  key: string;
  name: string;
  country: string;
}

export type ZonesGeoJSON = GeoJSON.FeatureCollection<
  GeoJSON.Geometry,
  ZoneFeatureProps
>;
